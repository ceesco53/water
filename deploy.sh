#!/usr/bin/env bash
set -euo pipefail

GITHUB_USER="ceesco53"
IMAGE="ghcr.io/${GITHUB_USER}/water"
TAG="${1:-latest}"
NAMESPACE="water"

# ── GitHub token (keychain → env → fail) ─────────────────────────────────────
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  GITHUB_TOKEN="$(git credential-osxkeychain get <<< $'host=github.com\nprotocol=https\n' 2>/dev/null | grep '^password=' | cut -d= -f2)" || true
fi
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "ERROR: GITHUB_TOKEN not set and not found in keychain."
  echo "  export GITHUB_TOKEN=<your token>  and re-run."
  exit 1
fi

echo "→ Logging in to ghcr.io"
echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_USER" --password-stdin

echo ""
echo "→ Building $IMAGE:$TAG (linux/amd64)"
docker buildx build \
  --platform linux/amd64 \
  -t "$IMAGE:$TAG" \
  -t "$IMAGE:latest" \
  --push \
  .

echo ""
echo "→ Applying k8s manifests"
kubectl apply -f k8s/namespace.yaml

# Ensure ghcr pull secret exists in namespace
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username="$GITHUB_USER" \
  --docker-password="$GITHUB_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -n "$NAMESPACE" -f -

kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml

echo ""
echo "→ Rolling restart"
kubectl rollout restart deployment/water -n "$NAMESPACE"
kubectl rollout status deployment/water -n "$NAMESPACE"

echo ""
echo "✓ Deployed — https://water.ingress.realmclick.com"
