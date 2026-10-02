#!/bin/bash
set -e

NAMESPACE="cloud-cost-compass"

echo "=== Vyom Local Setup ==="

echo "Creating Kind cluster..."
kind create cluster --config infra/kind/kind-config.yaml --name cloud-cost-compass

echo "Installing Gateway API CRDs..."
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.1.0/standard-install.yaml

echo "Installing Envoy Gateway..."
kubectl apply -f https://github.com/envoyproxy/gateway/releases/download/v1.1.0/install.yaml

echo "Building Docker images..."
docker build -t cloud-cost-compass/mcp-server:latest -f mcp-server/Dockerfile mcp-server/
docker build -t cloud-cost-compass/app:latest -f app/Dockerfile app/
docker build -t cloud-cost-compass/rag-service:latest -f rag-service/Dockerfile rag-service/

echo "Loading images into Kind..."
kind load docker-image cloud-cost-compass/app:latest --name cloud-cost-compass
kind load docker-image cloud-cost-compass/mcp-server:latest --name cloud-cost-compass
kind load docker-image cloud-cost-compass/rag-service:latest --name cloud-cost-compass
kind load docker-image qdrant/qdrant:v1.7.4 --name cloud-cost-compass
kind load docker-image hashicorp/vault:1.16 --name cloud-cost-compass
kind load docker-image quay.io/keycloak/keycloak:24.0 --name cloud-cost-compass || echo "Keycloak image not pre-loaded, will pull from registry"

echo "Deploying to Kubernetes..."
kubectl apply -f infra/k8s/ -n $NAMESPACE

echo "Waiting for pods..."
kubectl wait --for=condition=ready pod -l app=postgres -n $NAMESPACE --timeout=120s || echo "postgres not ready"
kubectl wait --for=condition=ready pod -l app=vault -n $NAMESPACE --timeout=120s || echo "vault not ready"
kubectl wait --for=condition=ready pod -l app=keycloak -n $NAMESPACE --timeout=120s || echo "keycloak not ready"
kubectl wait --for=condition=ready pod -l app=mcp-server -n $NAMESPACE --timeout=120s || echo "mcp-server not ready"
kubectl wait --for=condition=ready pod -l app=app -n $NAMESPACE --timeout=120s || echo "app not ready"
kubectl wait --for=condition=ready pod -l app=rag-service -n $NAMESPACE --timeout=120s || echo "rag-service not ready"
kubectl wait --for=condition=ready pod -l app=qdrant -n $NAMESPACE --timeout=120s || echo "qdrant not ready"

echo ""
echo "=== Vault Check ==="
VAULT_POD=$(kubectl get pods -n $NAMESPACE -l app=vault -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -z "$VAULT_POD" ]; then
    echo "WARNING: No Vault pod found in namespace $NAMESPACE"
else
    kubectl wait --for=condition=ready pod -n $NAMESPACE --timeout=60s -l app=vault 2>/dev/null || true
    VAULT_STATUS=$(kubectl get pod -n $NAMESPACE $VAULT_POD -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
    echo "Vault pod: $VAULT_POD (phase: $VAULT_STATUS)"
    echo "Vault is running at http://vault:8200 (dev mode, token: vault-root-token)"
fi

echo ""
echo "=== Keycloak Check ==="
KEYCLOAK_POD=$(kubectl get pods -n $NAMESPACE -l app=keycloak -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -z "$KEYCLOAK_POD" ]; then
    echo "WARNING: No Keycloak pod found in namespace $NAMESPACE"
    echo "Keycloak should be running at http://keycloak:8080/realms/cloud-compass"
    echo "If Keycloak is external, ensure it's reachable from the cluster."
else
    kubectl wait --for=condition=ready pod -n $NAMESPACE --timeout=60s -l app=keycloak 2>/dev/null || true
    KEYCLOAK_STATUS=$(kubectl get pod -n $NAMESPACE $KEYCLOAK_POD -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
    echo "Keycloak pod: $KEYCLOAK_POD (phase: $KEYCLOAK_STATUS)"
fi

echo ""
echo "=== Setup Complete ==="
echo "App:       http://localhost:8080  (Refine + shadcn/ui)"
echo "MCP:       http://localhost:8000"
echo "RAG:       http://localhost:8001"
echo "Qdrant:    http://localhost:6334"
echo "Vault:     http://localhost:8200"
echo "Keycloak:  http://localhost:8080  (realm: cloud-compass)"
