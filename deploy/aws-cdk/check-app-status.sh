#!/bin/bash
# Check application status on deployed instances

set -e

echo "=========================================="
echo "Application Status Checker"
echo "=========================================="
echo ""

# Parse command line arguments — AWS_REGION and AWS_PROFILE are inherited from
# the environment if not overridden by flags.
AWS_PROFILE="${AWS_PROFILE:-}"

while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--profile)
            AWS_PROFILE="$2"
            shift 2
            ;;
        -r|--region)
            AWS_REGION="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -p, --profile PROFILE    AWS profile to use (defaults to \$AWS_PROFILE)"
            echo "  -r, --region REGION      AWS region (defaults to \$AWS_REGION, required)"
            echo "  -h, --help               Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [ -z "$AWS_REGION" ]; then
    echo "Error: AWS_REGION is not set. Export it or pass -r <region>."
    exit 1
fi

# Build AWS CLI arguments
AWS_OPTS=""
if [ -n "$AWS_PROFILE" ]; then
    AWS_OPTS="--profile $AWS_PROFILE"
fi

# Verify credentials are available (profile, env vars, instance role, etc.)
if ! aws $AWS_OPTS sts get-caller-identity --output text > /dev/null 2>&1; then
    echo "Error: no valid AWS credentials found. Set AWS_PROFILE / AWS_ACCESS_KEY_ID, or pass -p <profile>."
    exit 1
fi

AWS_OPTS="$AWS_OPTS --region $AWS_REGION"
echo "Using region: $AWS_REGION"
echo ""

# Function to check instance status
# Args: STACK_NAME INSTANCE_NAME [INSTANCE_ID_OUTPUT_KEY]
check_instance() {
    local STACK_NAME=$1
    local INSTANCE_NAME=$2
    local INSTANCE_ID_KEY=${3:-InstanceId}

    echo "=========================================="
    echo "Checking $INSTANCE_NAME"
    echo "=========================================="

    # Get instance ID
    INSTANCE_ID=$(aws $AWS_OPTS cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --query "Stacks[0].Outputs[?OutputKey=='$INSTANCE_ID_KEY'].OutputValue" \
        --output text 2>/dev/null)

    if [ -z "$INSTANCE_ID" ] || [ "$INSTANCE_ID" == "None" ]; then
        echo "❌ Instance not found in stack $STACK_NAME"
        return 1
    fi

    echo "Instance ID: $INSTANCE_ID"

    # Get instance state
    INSTANCE_STATE=$(aws $AWS_OPTS ec2 describe-instances \
        --instance-ids $INSTANCE_ID \
        --query "Reservations[0].Instances[0].State.Name" \
        --output text 2>/dev/null)

    echo "Instance State: $INSTANCE_STATE"

    if [ "$INSTANCE_STATE" != "running" ]; then
        echo "❌ Instance is not running"
        return 1
    fi

    echo "✓ Instance is running"
    echo ""

    # Check docker containers via SSM
    echo "Checking Docker containers..."

    DOCKER_STATUS=$(aws $AWS_OPTS ssm send-command \
        --instance-ids "$INSTANCE_ID" \
        --document-name "AWS-RunShellScript" \
        --parameters 'commands=["docker ps --format \"table {{.Names}}\t{{.Status}}\t{{.State}}\""]' \
        --output json 2>/dev/null)

    if [ $? -ne 0 ]; then
        echo "❌ Failed to execute command via SSM"
        echo "   Make sure Systems Manager is installed and instance has IAM role"
        return 1
    fi

    COMMAND_ID=$(echo "$DOCKER_STATUS" | jq -r '.Command.CommandId')

    # Wait for command to complete
    echo "Waiting for command to complete..."
    sleep 3

    # Get command output
    COMMAND_OUTPUT=$(aws $AWS_OPTS ssm get-command-invocation \
        --command-id "$COMMAND_ID" \
        --instance-id "$INSTANCE_ID" \
        --output json 2>/dev/null)

    STATUS=$(echo "$COMMAND_OUTPUT" | jq -r '.Status')
    OUTPUT=$(echo "$COMMAND_OUTPUT" | jq -r '.StandardOutputContent')

    if [ "$STATUS" == "Success" ]; then
        echo "$OUTPUT"

        # Count running containers
        RUNNING_COUNT=$(echo "$OUTPUT" | grep -c "Up" || echo "0")

        if [ "$RUNNING_COUNT" -gt 0 ]; then
            echo ""
            echo "✓ $RUNNING_COUNT container(s) running"
        else
            echo ""
            echo "❌ No containers running"

            # Try to get more info
            echo ""
            echo "Checking logs..."
            LOG_CMD=$(aws $AWS_OPTS ssm send-command \
                --instance-ids "$INSTANCE_ID" \
                --document-name "AWS-RunShellScript" \
                --parameters 'commands=["tail -50 /var/log/user-data.log 2>/dev/null || echo \"Log not available\""]' \
                --output json 2>/dev/null)

            LOG_COMMAND_ID=$(echo "$LOG_CMD" | jq -r '.Command.CommandId')
            sleep 2

            LOG_OUTPUT=$(aws $AWS_OPTS ssm get-command-invocation \
                --command-id "$LOG_COMMAND_ID" \
                --instance-id "$INSTANCE_ID" \
                --query 'StandardOutputContent' \
                --output text 2>/dev/null)

            echo "Last 50 lines of user-data log:"
            echo "$LOG_OUTPUT"
        fi
    else
        echo "❌ Command failed: $STATUS"
        ERROR=$(echo "$COMMAND_OUTPUT" | jq -r '.StandardErrorContent')
        echo "Error: $ERROR"
    fi

    echo ""
}

# Check Omniverse instance
check_instance "OmniverseCAEComputeStack" "Omniverse Instance"

# Check if NIM stack exists (split deployment)
NIM_STACK_EXISTS=$(aws $AWS_OPTS cloudformation describe-stacks \
    --stack-name OmniverseCAENimStack 2>&1 | grep -c "OmniverseCAENimStack" || echo "0")

if [ "$NIM_STACK_EXISTS" -gt 0 ]; then
    echo ""
    check_instance "OmniverseCAENimStack" "NIM Instance" "NimInstanceId"
fi

# Retrieve Omniverse public IP for application URL
OV_PUBLIC_IP=$(aws $AWS_OPTS cloudformation describe-stacks \
    --stack-name OmniverseCAEComputeStack \
    --query "Stacks[0].Outputs[?OutputKey=='InstancePublicIP'].OutputValue" \
    --output text 2>/dev/null)

echo ""
echo "=========================================="
echo "Status check complete"
echo "=========================================="
echo ""
if [ ! -z "$OV_PUBLIC_IP" ] && [ "$OV_PUBLIC_IP" != "None" ]; then
    echo "Application URL:  http://$OV_PUBLIC_IP"
    echo ""
fi
echo "To connect to instances via SSM:"
echo "  aws ssm start-session --target <InstanceID> $AWS_OPTS"


echo ""
echo "To view container logs:"
echo "  docker compose logs -f"
echo ""
