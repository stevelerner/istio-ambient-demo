#!/bin/bash
# Install Istio ambient (base, istiod, cni, ztunnel) plus Gateway API CRDs on the local kind cluster.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib/kubectx.sh" && require_kind_context
source "$DIR/versions.env"

kubectl apply --server-side -f "https://github.com/kubernetes-sigs/gateway-api/releases/download/${GATEWAY_API_VERSION}/standard-install.yaml" >/dev/null
helm repo add istio https://istio-release.storage.googleapis.com/charts >/dev/null 2>&1 || true
helm repo update istio >/dev/null

helm upgrade --install istio-base istio/base -n istio-system --create-namespace --version "$ISTIO_VERSION" --wait
helm upgrade --install istiod istio/istiod -n istio-system --version "$ISTIO_VERSION" --wait --timeout 5m \
  --set profile=ambient \
  --set-json 'meshConfig.extensionProviders=[{"name":"tinyolly-otel","opentelemetry":{"service":"tinyolly-otlp-receiver.default.svc.cluster.local","port":4343}},{"name":"tinyolly-otel-als","envoyOtelAls":{"service":"tinyolly-otlp-receiver.default.svc.cluster.local","port":4343}}]'
helm upgrade --install istio-cni istio/cni -n istio-system --version "$ISTIO_VERSION" --set profile=ambient --wait --timeout 5m
helm upgrade --install ztunnel istio/ztunnel -n istio-system --version "$ISTIO_VERSION" --wait --timeout 5m

kubectl apply -f "$DIR/mesh-metrics.yaml"
echo "Istio ambient ${ISTIO_VERSION} installed. Next: ./02-deploy-shop.sh"
