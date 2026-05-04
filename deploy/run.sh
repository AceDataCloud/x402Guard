#!/usr/bin/env bash
#
# Apply x402guard production manifests to the AceDataCloud cluster.
#
# Substitutes ${TAG} in the manifests with $BUILD_NUMBER (from CI) or
# `local` (when run by hand) and applies them in dependency order.
#
# Required: a Kubernetes secret in the acedatacloud namespace named
# `x402guard-secrets` containing:
#   APP_SECRET_KEY        — Django/HMAC session signing key
#   DATABASE_URL          — postgresql+asyncpg://user:pass@host:5432/db
#   CONNECTION_VAULT_KEY  — 32-byte hex; AES-256-GCM master key
#                           that wraps each vault's delegation private key
# Bootstrap (run once):
#   kubectl -n acedatacloud create secret generic x402guard-secrets \
#     --from-literal=APP_SECRET_KEY=$(openssl rand -hex 32) \
#     --from-literal=DATABASE_URL=postgresql+asyncpg://... \
#     --from-literal=CONNECTION_VAULT_KEY=$(openssl rand -hex 32)
#
# The TLS wildcard cert (tls-wildcard-acedata-cloud) and image-pull
# secret (docker-registry) are platform-wide — already provisioned.

set -euo pipefail

TAG="${BUILD_NUMBER:-local}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/production" && pwd)"
NS=acedatacloud

if ! kubectl -n "$NS" get secret x402guard-secrets >/dev/null 2>&1; then
  echo "ERROR: secret x402guard-secrets is missing in namespace $NS." >&2
  echo "       Bootstrap the secret using the snippet at the top of this file." >&2
  exit 1
fi

for f in postgres.yaml api.yaml web.yaml ingress.yaml; do
  echo "==> applying $f (tag=$TAG)"
  sed "s|\\\${TAG}|$TAG|g" "$DIR/$f" | kubectl apply -f -
done

echo "==> waiting for rollouts"
kubectl -n "$NS" rollout status statefulset/x402guard-postgres --timeout=180s
kubectl -n "$NS" rollout status deploy/x402guard-api --timeout=180s
kubectl -n "$NS" rollout status deploy/x402guard-web --timeout=180s

echo "==> probing https://x402guard.acedata.cloud/health"
curl --max-time 10 -fsS https://x402guard.acedata.cloud/health \
  || echo "(probe failed — check ingress + DNS + LB upstream registration)"
