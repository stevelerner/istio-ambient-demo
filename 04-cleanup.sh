#!/bin/bash
# Remove the demo: shop, waypoint, collector, Istio. Leaves the kind cluster and TinyOlly alone.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib/kubectx.sh" && require_kind_context

kubectl delete namespace boutique --ignore-not-found
kubectl delete -f "$DIR/mesh-metrics.yaml" --ignore-not-found
for r in ztunnel istio-cni istiod istio-base; do helm uninstall "$r" -n istio-system 2>/dev/null; done
kubectl delete namespace istio-system --ignore-not-found
kubectl delete pod outsider -n outside --ignore-not-found --now >/dev/null 2>&1 || true
kubectl delete namespace outside --ignore-not-found --wait=false
# TinyOlly keeps the demo's telemetry (edges, denied counts); clear it so the next run starts clean
curl -s -m 20 -X POST "${TINYOLLY_URL:-http://localhost:5005}/admin/reset" >/dev/null \
  || echo "Could not reach TinyOlly; clear its data in the UI instead." >&2
echo "Istio demo removed."
