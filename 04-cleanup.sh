#!/bin/bash
# Remove the demo: shop, waypoint, collector, Istio. Leaves the kind cluster and TinyOlly alone.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib/kubectx.sh" && require_kind_context

kubectl delete namespace boutique --ignore-not-found
kubectl delete -f "$DIR/mesh-metrics.yaml" --ignore-not-found
for r in ztunnel istio-cni istiod istio-base; do helm uninstall "$r" -n istio-system 2>/dev/null; done
kubectl delete namespace istio-system --ignore-not-found
echo "Istio demo removed."
