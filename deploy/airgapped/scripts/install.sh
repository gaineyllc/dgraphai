#!/usr/bin/env bash
# dgraph.ai Air-Gapped Installation Script
# Loads all images, installs Helm charts, validates deployment.
# Run on a machine with kubectl + helm configured to target your cluster.
set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NAMESPACE="${NAMESPACE:-dgraphai}"
RELEASE="${RELEASE:-dgraphai}"
REGISTRY="${REGISTRY:-registry.internal:5000}"
VALUES="${VALUES:-$BUNDLE_DIR/values-airgapped.yaml}"

log()  { echo "[$(date -u '+%H:%M:%S')] $*"; }
fail() { echo "[ERROR] $*" >&2; exit 1; }

# ── 1. Verify bundle integrity ─────────────────────────────────────────────────
log "Verifying bundle signature..."
if ! "$BUNDLE_DIR/scripts/verify-bundle.sh"; then
  fail "Bundle signature verification failed. The bundle may be tampered."
fi
log "✓ Bundle integrity verified"

# ── 2. Load container images ───────────────────────────────────────────────────
log "Loading container images into local registry..."
for tarfile in "$BUNDLE_DIR"/images/*.tar; do
  name=$(basename "$tarfile" .tar)
  log "  Loading $name..."
  docker load -i "$tarfile"
  # Re-tag for local registry
  original_tag=$(docker inspect --format='{{index .RepoTags 0}}' $(docker load -qi "$tarfile" | awk '{print $NF}'))
  docker tag "$original_tag" "$REGISTRY/$original_tag"
  docker push "$REGISTRY/$original_tag"
done
log "✓ All images loaded"

# ── 3. Create namespace ────────────────────────────────────────────────────────
kubectl get namespace "$NAMESPACE" &>/dev/null || kubectl create namespace "$NAMESPACE"
log "✓ Namespace $NAMESPACE ready"

# ── 4. Load Ollama models ──────────────────────────────────────────────────────
log "Preparing Ollama model volume..."
kubectl create configmap dgraphai-models-config \
  --from-file="$BUNDLE_DIR/models/" \
  --namespace "$NAMESPACE" \
  --dry-run=client -o yaml | kubectl apply -f -
log "✓ Models configmap created"

# ── 5. Apply license secret ────────────────────────────────────────────────────
if [ -f "$BUNDLE_DIR/license.dglicense" ]; then
  kubectl create secret generic dgraphai-license \
    --from-file=license.dglicense="$BUNDLE_DIR/license.dglicense" \
    --namespace "$NAMESPACE" \
    --dry-run=client -o yaml | kubectl apply -f -
  log "✓ License secret applied"
else
  log "⚠ No license.dglicense found — trial mode will be used"
fi

# ── 6. Install Helm chart ──────────────────────────────────────────────────────
log "Installing dgraphai Helm chart..."
helm install "$RELEASE" "$BUNDLE_DIR/charts/dgraphai-"*.tgz \
  --namespace "$NAMESPACE" \
  --values "$VALUES" \
  --set "image.repository=$REGISTRY/dgraphai/dgraphai" \
  --set "global.imageRegistry=$REGISTRY" \
  --timeout 10m \
  --wait

log "✓ Helm chart installed"

# ── 7. Run database migrations ────────────────────────────────────────────────
log "Running database migrations..."
kubectl run dgraphai-migrate \
  --image="$REGISTRY/dgraphai/dgraphai:latest" \
  --rm -it --restart=Never \
  --namespace "$NAMESPACE" \
  --env="DATABASE_URL=$(kubectl get secret dgraphai-db-secret -n $NAMESPACE -o jsonpath='{.data.url}' | base64 -d)" \
  -- sh -c "uv run alembic upgrade head"
log "✓ Migrations complete"

# ── 8. Wait for readiness ──────────────────────────────────────────────────────
log "Waiting for deployment to be ready..."
kubectl rollout status deployment/dgraphai-api \
  --namespace "$NAMESPACE" \
  --timeout 5m

# ── 9. Verify health ──────────────────────────────────────────────────────────
API_POD=$(kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/name=dgraphai -o jsonpath='{.items[0].metadata.name}')
HEALTH=$(kubectl exec "$API_POD" -n "$NAMESPACE" -- curl -s http://localhost:8000/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'])")

if [ "$HEALTH" != "ok" ] && [ "$HEALTH" != "degraded" ]; then
  fail "Health check failed: $HEALTH"
fi

log "✓ Installation complete!"
log ""
log "Access dgraph.ai:"
INGRESS_IP=$(kubectl get ingress -n "$NAMESPACE" -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}')
log "  URL: https://$INGRESS_IP"
log "  Or configure DNS to point to: $INGRESS_IP"
log ""
log "Default admin account must be created:"
log "  kubectl exec -n $NAMESPACE deploy/dgraphai-api -- \\
    python -m src.dgraphai.cli create-admin --email admin@company.com"
