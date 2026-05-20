#!/bin/bash
set -e

# Set HOME for root — user data runs without a login shell so $HOME is unset
export HOME=/root

# Log all output
exec > >(tee /var/log/user-data.log)
exec 2>&1

echo "Starting NIM instance user data script at $(date)"

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
mkdir -p /usr/share/keyrings

if ! curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --batch --yes --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg; then
    echo "ERROR: Failed to install NVIDIA Container Toolkit GPG key"
    exit 1
fi

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

# Add NGC_API_KEY to system environment
echo "NGC_API_KEY=${NGC_API_KEY}" >> /etc/environment

# Docker login to NGC
echo "Logging into NVIDIA NGC registry..."
if ! echo "$NGC_API_KEY" | docker login nvcr.io --username '$oauthtoken' --password-stdin; then
    echo "ERROR: Failed to login to NGC registry"
    exit 1
fi

# Download source code from S3 (same bucket as compute instance)
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

# Create .env — NIM instance has one GPU so CUDA_DEVICE_AERONIM=0
cat > .env << ENV_EOF
NGC_API_KEY=${NGC_API_KEY}
NVIDIA_API_KEY=${NGC_API_KEY}
COMPOSE_PROFILES=standard
CUDA_DEVICE_AERONIM=0
ENV_EOF

# Change ownership to ubuntu user
chown -R ubuntu:ubuntu /home/ubuntu/digital-twins-for-fluid-simulation

# Build the custom aeronim image and start the service
echo "Building aeronim image..."
docker compose build aeronim

echo "Starting aeronim container..."
docker compose up -d aeronim

# Create helper script for manual relaunch
cat > /home/ubuntu/relaunch-nim.sh << 'RELAUNCH_EOF'
#!/bin/bash
cd /home/ubuntu/digital-twins-for-fluid-simulation
echo "Restarting aeronim container..."
docker compose down aeronim
docker compose up -d aeronim
echo "Done."
docker ps | grep aeronim
RELAUNCH_EOF

chmod +x /home/ubuntu/relaunch-nim.sh
chown ubuntu:ubuntu /home/ubuntu/relaunch-nim.sh

echo "Created /home/ubuntu/relaunch-nim.sh for manual container management"

# Create systemd service for automatic startup
echo "Creating systemd service..."
cat > /etc/systemd/system/nim.service << EOFSERVICE
[Unit]
Description=NIM Inference Service
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/ubuntu/digital-twins-for-fluid-simulation
EnvironmentFile=/etc/environment
ExecStart=/usr/bin/docker compose up -d aeronim
ExecStop=/usr/bin/docker compose down aeronim
User=ubuntu
Group=ubuntu

[Install]
WantedBy=multi-user.target
EOFSERVICE

# Enable the service
systemctl daemon-reload
systemctl enable nim.service

# Wait for NIM to be ready and log status
echo "Waiting for NIM to initialize..."
sleep 30

echo "NIM container status:"
docker ps

echo "NIM logs:"
docker logs aeronim --tail 50

# Signal completion
echo "NIM instance setup complete at $(date)" | tee /home/ubuntu/setup-complete.txt
chown ubuntu:ubuntu /home/ubuntu/setup-complete.txt

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo "NIM is listening on port 8080"
echo "To manually relaunch NIM:"
echo "  /home/ubuntu/relaunch-nim.sh"
echo "=========================================="
echo ""

echo "User data script completed successfully!"
