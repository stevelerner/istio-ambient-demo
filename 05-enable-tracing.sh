#!/bin/bash
# Turn on OTel tracing in the Go Online Boutique services, exporting to TinyOlly.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/lib" && pwd)/kubectx.sh" && require_kind_context
for d in frontend checkoutservice productcatalogservice shippingservice; do
  kubectl set env -n boutique deploy/$d ENABLE_TRACING=1 \
    COLLECTOR_SERVICE_ADDR=tinyolly-otlp-receiver.default.svc.cluster.local:4343 \
    OTEL_SERVICE_NAME=$d
done
kubectl rollout status -n boutique deploy/frontend --timeout=180s
