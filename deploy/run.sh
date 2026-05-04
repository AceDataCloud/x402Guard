#!/usr/bin/env bash
#
# Deploy x402guard to a Kubernetes cluster.
#
# Substitutes `__BUILD__` in the manifests with the GITHUB_RUN_ID
# (or `local` if running by hand) and applies them in dependency order.
#
# Required secrets must already exist:
#   $ kubectl -n x402guard create secret generic x402guard-secrets \
#       --from-literal=APP_SECRET_KEY=... \
#       --from-literal=DATABASE_URL=postgresql+asyncpg://... \
#       --from-literal=CONNECTION_VAULT_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')

set -euo pipefail

BUILD="${GITHUB_RUN_ID:-local}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/production" && pwd)"
NS=x402guard

echo "==> Applying namespace"
kubectl apply -f "$DIR/namespace.yaml"

echo "==> Applying configmap"
kubectl apply -f "$DIR/configmap.yaml"

if ! kubectl -n "$NS" get secret x402guard-secrets >/dev/null 2>&1; then
  echo "ERROR: Secret x402guard-secrets is missing in namespace $NS." >&2
  echo "Create it with the snippet at the top of this script before running deploy." >&2
  exit 1
fi

for f in api.yaml web.yaml ingress.yaml; do
  echo "==> Applying $f (build=$BUILD)"
  sed "s|__BUILD__|$BUILD|g" "$DIR/$f" | kubectl apply -f -
done

echo "==> Waiting for rollouts"
kubectl -n "$NS" rollout status deploy/api  --timeout=180s
kubectl -n "$NS" rollout status deploy/web  --timeout=180s

echo "==> Done. Probing https://x402guard.acedata.cloud/health"
curl --max-time 10 -fsS https://x402guard.acedata.cloud/health || \
  echo "(probe failed — check ingress + DNS)"
