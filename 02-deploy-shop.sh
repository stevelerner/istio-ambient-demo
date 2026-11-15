#!/bin/bash
# Deploy Online Boutique into the ambient-enabled 'boutique' namespace (L4 only: no waypoint yet).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib/kubectx.sh" && require_kind_context
source "$DIR/versions.env"

kubectl create namespace boutique --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl label namespace boutique istio.io/dataplane-mode=ambient --overwrite
kubectl apply -n boutique -f "https://raw.githubusercontent.com/GoogleCloudPlatform/microservices-demo/${BOUTIQUE_VERSION}/release/kubernetes-manifests.yaml"
for d in cartservice currencyservice; do kubectl set resources -n boutique deploy/$d --limits=memory=256Mi; done  # default 128Mi OOMs under load
# The kind node has 4 CPUs and the default requests (about 1.7 CPU for the shop) leave no room for a waypoint, the canary pod or
# a rolling restart, so pods would stay Pending. Requests only affect scheduling, not real usage.
kubectl set resources -n boutique deploy --all --requests=cpu=50m
kubectl rollout status -n boutique deploy/frontend --timeout=300s
kubectl apply -f "$(dirname "$0")/ingress.yaml"
# Istio auto-creates the Service; pin NodePort 30001 (kind maps host :5001 -> 30001)
for _ in $(seq 30); do kubectl get svc -n boutique shop-ingress-istio >/dev/null 2>&1 && break; sleep 2; done
kubectl patch svc -n boutique shop-ingress-istio --type=json -p '[{"op":"replace","path":"/spec/ports/1/nodePort","value":30001}]'
echo "Shop is running with ztunnel (mTLS, TCP metrics). Add L7 with: ./03-scenario.sh waypoint"
