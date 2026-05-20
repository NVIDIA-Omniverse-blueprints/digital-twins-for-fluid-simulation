#!/bin/bash
set -e

# Set HOME environment variable for git-lfs (user data runs as root)
export HOME=/root

# Log all output
exec > >(tee /var/log/user-data.log)
exec 2>&1

echo "Starting user data script at $(date)"

# Configure SSM to use ubuntu user by default
mkdir -p /etc/systemd/system/snap.amazon-ssm-agent.amazon-ssm-agent.service.d
cat > /etc/systemd/system/snap.amazon-ssm-agent.amazon-ssm-agent.service.d/override.conf << 'EOF'
[Service]
Environment="SSM_RUN_AS_USER=ubuntu"
EOF
systemctl daemon-reload
systemctl restart snap.amazon-ssm-agent.amazon-ssm-agent.service || systemctl restart amazon-ssm-agent || true

# Wait for unattended-upgrades (or any other apt user) to release the dpkg
# lock before invoking apt ourselves. Without this, first-boot races abort
# the script at the first `apt-get` call (set -e is on).
wait_for_apt() {
    local timeout=600
    local waited=0
    while fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock >/dev/null 2>&1; do
        if [ "$waited" -ge "$timeout" ]; then
            echo "ERROR: Timed out after ${timeout}s waiting for apt/dpkg lock"
            exit 1
        fi
        echo "Waiting for apt/dpkg lock to be released... (${waited}s)"
        sleep 5
        waited=$((waited + 5))
    done
}

# Update system
echo "Updating system packages..."
wait_for_apt
apt-get update
wait_for_apt
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

# Install required packages including gnupg for GPG operations
echo "Installing required packages..."
wait_for_apt
apt-get install -y build-essential git git-lfs curl unzip gnupg ca-certificates

# Install Docker
echo "Installing Docker..."
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
usermod -aG docker ubuntu
rm -f get-docker.sh

# Install NVIDIA Container Toolkit
echo "Installing NVIDIA Container Toolkit..."
# Ensure keyring directory exists
mkdir -p /usr/share/keyrings

# Download and install GPG key with --batch --yes to avoid TTY requirement
if ! curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --batch --yes --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg; then
    echo "ERROR: Failed to install NVIDIA Container Toolkit GPG key"
    exit 1
fi

# Add NVIDIA Container Toolkit repository
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

wait_for_apt
apt-get update
wait_for_apt
apt-get install -y nvidia-container-toolkit

# Configure Docker for NVIDIA runtime
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker

# Install AWS CLI v2
echo "Installing AWS CLI v2..."
curl -fsSL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o awscliv2.zip
unzip -q awscliv2.zip
./aws/install --update  # Use --update flag to handle pre-existing installation
rm -rf aws awscliv2.zip

# Get NGC API Key from Secrets Manager
echo "Retrieving NGC API Key from Secrets Manager..."
# NOTE: The following variables need to be replaced with actual values:
# - NGC_SECRET_NAME: The name of the secret in AWS Secrets Manager
# - AWS_REGION: The AWS region where the secret is stored
if ! NGC_API_KEY=$(aws secretsmanager get-secret-value --secret-id ${NGC_SECRET_NAME} --query SecretString --output text --region ${AWS_REGION}); then
    echo "ERROR: Failed to retrieve NGC API Key from Secrets Manager"
    exit 1
fi

if [ -z "$NGC_API_KEY" ]; then
    echo "ERROR: NGC_API_KEY is empty"
    exit 1
fi

echo "NGC API Key retrieved successfully"

# Set NGC API Key as environment variable for ubuntu user
echo "export NGC_API_KEY='$NGC_API_KEY'" >> /home/ubuntu/.bashrc

# Get NIM IP from SSM if using external NIM
NIM_TRITON_IP_ADDRESS="${NIM_TRITON_IP_ADDRESS}"
NIM_TRITON_HTTP_PORT="8080"

if [[ "$NIM_TRITON_IP_ADDRESS" == "RETRIEVE_FROM_SSM" ]]; then

    NIM_TRITON_IP_ADDRESS=$(aws ssm get-parameter --name "/omniverse-cae/nim-ip" --query Parameter.Value --output text --region ${AWS_REGION})

    if [ -z "$NIM_TRITON_IP_ADDRESS" ] || [ "$NIM_TRITON_IP_ADDRESS" == "None" ]; then
        echo "ERROR: Could not retrieve NIM IP from SSM"
        exit 1
    fi

    echo "Retrieved NIM IP: $NIM_TRITON_IP_ADDRESS"
fi
export NIM_TRITON_IP_ADDRESS=$NIM_TRITON_IP_ADDRESS


# Docker login to NGC
echo "Logging into NVIDIA NGC registry..."
if ! echo "$NGC_API_KEY" | docker login nvcr.io --username '$oauthtoken' --password-stdin; then
    echo "ERROR: Failed to login to NGC registry"
    exit 1
fi

# Download source code from S3
echo "Downloading repo from s3://${REPO_S3_BUCKET}/${REPO_S3_PREFIX}/ ..."
cd /home/ubuntu
if [ -d "digital-twins-for-fluid-simulation" ]; then
    rm -rf digital-twins-for-fluid-simulation
fi
mkdir digital-twins-for-fluid-simulation
aws s3 sync "s3://${REPO_S3_BUCKET}/${REPO_S3_PREFIX}/" /home/ubuntu/digital-twins-for-fluid-simulation/
# S3 strips Unix execute bits — restore them for all shell scripts
find /home/ubuntu/digital-twins-for-fluid-simulation -name "*.sh" -exec chmod +x {} \;
cd /home/ubuntu/digital-twins-for-fluid-simulation

# Create .env file with all required variables
echo "Creating .env file..."
cat > .env << ENV_EOF
# NGC API Key
NGC_API_KEY=${NGC_API_KEY}

# NIM Configuration (will be updated on relaunch)
NIM_TRITON_IP_ADDRESS=$NIM_TRITON_IP_ADDRESS
NIM_TRITON_HTTP_PORT=${NIM_TRITON_HTTP_PORT}

# Application Configuration
COMPOSE_PROFILES=standard
USD_URL=/home/ubuntu/usd/world_rtwt_minimal.usda
STL_PATH_FORMAT=/data/low_res/detailed_car_{}/aero_suv_low.stl
WEB_HOST_PORT=80
CUDA_DEVICE_KIT=0
${CUDA_DEVICE_AERONIM_ENV}
# STREAMSDK_SENDER_TIMEOUT=100000
KIT_APP=omni.rtwt.webrtc.kit

# Omniverse credentials (optional)
OMNI_USER=
OMNI_PASS=
ENV_EOF

echo "Docker compose configuration complete"


# Build only the services required for this deployment mode.
echo "Building Docker containers..."
docker compose build --no-cache ${COMPOSE_SERVICES}

# Change ownership to ubuntu user
chown -R ubuntu:ubuntu /home/ubuntu/digital-twins-for-fluid-simulation

# Start only the services required for this deployment mode.
echo "Starting Docker containers..."
docker compose up -d ${COMPOSE_UP_OPTIONS} ${COMPOSE_SERVICES}

# Create helper script for manual relaunch with updated NIM IP
cat > /home/ubuntu/relaunch-containers.sh << 'RELAUNCH_EOF'
#!/bin/bash
# Helper script to relaunch containers with updated NIM IP
# Usage:
#   ./relaunch-containers.sh              # Uses deployment default NIM endpoint
#   ./relaunch-containers.sh [NIM_IP]     # Uses provided NIM IP
#   ./relaunch-containers.sh [NIM_IP] [NIM_PORT]  # Uses provided NIM IP and port

cd /home/ubuntu/digital-twins-for-fluid-simulation

# If no IP provided, use the deployment default.
if [ -z "$1" ]; then
    DEFAULT_NIM_TRITON_IP_ADDRESS="${DEFAULT_NIM_TRITON_IP_ADDRESS}"
    if [ "$DEFAULT_NIM_TRITON_IP_ADDRESS" = "RETRIEVE_FROM_SSM" ]; then
        NIM_TRITON_IP_ADDRESS=$(aws ssm get-parameter --name "/omniverse-cae/nim-ip" --query Parameter.Value --output text --region ${AWS_REGION})

        if [ -z "$NIM_TRITON_IP_ADDRESS" ] || [ "$NIM_TRITON_IP_ADDRESS" == "None" ]; then
            echo "ERROR: Could not retrieve NIM IP from SSM"
            exit 1
        fi

        echo "Retrieved NIM IP from SSM: $NIM_TRITON_IP_ADDRESS"
    else
        NIM_TRITON_IP_ADDRESS="$DEFAULT_NIM_TRITON_IP_ADDRESS"
        echo "Using default NIM IP: $NIM_TRITON_IP_ADDRESS"
    fi
else
    # Use provided IP
    NIM_TRITON_IP_ADDRESS="$1"
    echo "Using provided NIM IP: $NIM_TRITON_IP_ADDRESS"
fi

# Update .env file with NIM IP
echo "Updating NIM IP in .env..."
sed -i "s/^NIM_TRITON_IP_ADDRESS=.*/NIM_TRITON_IP_ADDRESS=$NIM_TRITON_IP_ADDRESS/" .env

# Export for current session
export NIM_TRITON_IP_ADDRESS="$NIM_TRITON_IP_ADDRESS"

# Update NIM port if provided
if [ ! -z "$2" ]; then
    export NIM_TRITON_HTTP_PORT="$2"
    echo "Updating NIM port to: $NIM_TRITON_HTTP_PORT"

    # Update .env file
    sed -i "s/^NIM_TRITON_HTTP_PORT=.*/NIM_TRITON_HTTP_PORT=$2/" .env

    # Update system environment
    sudo sed -i "s/^NIM_TRITON_HTTP_PORT=.*/NIM_TRITON_HTTP_PORT=$2/" /etc/environment
    echo "export NIM_TRITON_HTTP_PORT='$2'" >> /tmp/nim_env_update
    source /tmp/nim_env_update
else
    # Get current port from .env or use default
    NIM_TRITON_HTTP_PORT=$(grep "^NIM_TRITON_HTTP_PORT=" .env | cut -d'=' -f2)
    if [ -z "$NIM_TRITON_HTTP_PORT" ]; then
        NIM_TRITON_HTTP_PORT="8080"
    fi
    echo "Using NIM port: $NIM_TRITON_HTTP_PORT"
fi

echo ""
echo "Current NIM configuration:"
echo "  IP: $NIM_TRITON_IP_ADDRESS"
echo "  Port: $NIM_TRITON_HTTP_PORT"
echo ""

echo "Restarting containers with updated configuration..."
docker compose down
docker compose up -d ${COMPOSE_UP_OPTIONS} ${COMPOSE_SERVICES}

echo ""
echo "Containers relaunched successfully!"
echo "You can check status with: docker compose ps"
RELAUNCH_EOF

chmod +x /home/ubuntu/relaunch-containers.sh
chown ubuntu:ubuntu /home/ubuntu/relaunch-containers.sh

echo "Created /home/ubuntu/relaunch-containers.sh for manual container management"
# Create systemd service for automatic startup
echo "Creating systemd service..."
cat > /etc/systemd/system/omniverse-cae.service << SYSTEMD_EOF
[Unit]
Description=Omniverse CAE Blueprint
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/ubuntu/digital-twins-for-fluid-simulation
EnvironmentFile=/etc/environment
ExecStart=/usr/bin/docker compose up -d ${COMPOSE_UP_OPTIONS} ${COMPOSE_SERVICES}
ExecStop=/usr/bin/docker compose down
User=ubuntu
Group=ubuntu

[Install]
WantedBy=multi-user.target
SYSTEMD_EOF

# Enable and start the service
systemctl daemon-reload
systemctl enable omniverse-cae.service

# Signal completion
echo "Omniverse CAE Blueprint installation complete at $(date)" | tee /home/ubuntu/setup-complete.txt
chown ubuntu:ubuntu /home/ubuntu/setup-complete.txt

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo "NIM Configuration:"
echo "  IP: $NIM_TRITON_IP_ADDRESS"
echo "  Port: ${NIM_TRITON_HTTP_PORT}"
echo ""
echo "To manually relaunch with updated NIM IP:"
echo "  /home/ubuntu/relaunch-containers.sh <NIM_IP> [NIM_PORT]"
echo "=========================================="
echo ""

echo "User data script completed successfully!"
