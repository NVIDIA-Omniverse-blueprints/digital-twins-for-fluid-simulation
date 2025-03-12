#!/bin/bash

NAMESPACE="rtdt"
IMAGE_PULL_SECRET="ngc-registry-secret"

# Load environment variables from .env file if it exists
if [ -f .env ]; then
  source .env
fi

# Check if NGC_API_KEY is set
if [ -z "$NGC_API_KEY" ]; then
  echo "Error: NGC_API_KEY is not set in .env file"
  echo "Please add your NGC API Key as an environment variable"
  exit 1
fi

# Create namespace if it doesn't exist
echo "Ensuring namespace $NAMESPACE exists..."
microk8s kubectl create namespace $NAMESPACE --dry-run=client -o yaml | microk8s kubectl apply -f -

# Check if the secret already exists - if it does, delete it to ensure it's updated with the latest credentials
if microk8s kubectl get secret $IMAGE_PULL_SECRET -n $NAMESPACE &> /dev/null; then
  echo "Removing existing Docker registry secret $IMAGE_PULL_SECRET..."
  microk8s kubectl delete secret $IMAGE_PULL_SECRET -n $NAMESPACE
fi

# Create the Docker registry secret with proper NGC authentication
echo "Creating Docker registry secret $IMAGE_PULL_SECRET..."
microk8s kubectl create secret docker-registry $IMAGE_PULL_SECRET \
  --docker-server=nvcr.io \
  --docker-username=\$oauthtoken \
  --docker-password="$NGC_API_KEY" \
  -n $NAMESPACE

# Delete the previous deployment if it exists
microk8s kubectl delete deployment rtdt-rtdt -n $NAMESPACE --ignore-not-found=true

# Wait for pods to terminate
microk8s kubectl wait --for=delete pod -l app=rtdt-rtdt -n $NAMESPACE --timeout=60s

# Upgrade or install the helm chart
echo "Deploying Helm chart with NGC_API_KEY..."
microk8s helm3 upgrade --install rtdt ./rtdt-chart \
  --namespace $NAMESPACE \
  --create-namespace \
  --atomic \
  --timeout 10m0s \
  --set aeronim.environment.NGC_API_KEY="$NGC_API_KEY" \
  --set zmq.environment.NIM_TRITON_IP_ADDRESS="$NIM_TRITON_IP_ADDRESS" \
  --set zmq.environment.NIM_TRITON_HTTP_PORT="$NIM_TRITON_HTTP_PORT" \
  --wait

# Check the pods
microk8s kubectl get pods -n $NAMESPACE