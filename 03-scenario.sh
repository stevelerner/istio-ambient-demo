#!/bin/bash
# Apply an Istio ambient scenario (waypoint, waypoint-svc, fault, retry, flaky, timeout, canary, authz, strict) or reset them.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib/kubectx.sh" && require_kind_context

need_waypoint() {
  if ! kubectl get gateway waypoint -n boutique >/dev/null 2>&1; then
    echo "Waypoint 'waypoint' not found in namespace boutique. Run ./03-scenario.sh waypoint first." >&2
    exit 1
  fi
}

# The Go services keep long-lived gRPC connections, and a connection keeps the path it was opened on. After a waypoint is
# attached, restart the callers so their new connections go through it (otherwise the waypoint sees no traffic).
reconnect() {
  # Delete (not roll) the pods: a rolling restart needs spare CPU for the replacement pod, which a small kind node lacks.
  kubectl delete pod -n boutique -l 'app in (frontend,checkoutservice,recommendationservice)' --wait=true >/dev/null
  for d in frontend checkoutservice recommendationservice; do
    kubectl rollout status -n boutique deploy/$d --timeout=180s >/dev/null
  done
}

# Record a change marker in TinyOlly so an agent (MCP what_changed) can line up cause and effect. Best effort.
mark() {
  curl -s -m 5 -X POST "${TINYOLLY_URL:-http://localhost:5005}/api/events" -H 'Content-Type: application/json' \
    -d "{\"title\": \"scenario: $1\", \"source\": \"istio-ambient-demo\", \"kind\": \"scenario\", \"attributes\": {\"scenario\": \"$1\"}}" >/dev/null 2>&1 || true
}

case "${1:-}" in
  waypoint)
    kubectl apply -f "$DIR/waypoint.yaml"
    kubectl label service --all -n boutique istio.io/use-waypoint- >/dev/null 2>&1 || true
    kubectl label namespace boutique istio.io/use-waypoint=waypoint --overwrite
    reconnect
    ;;
  waypoint-svc)  # L7 for ONE service only (default productcatalogservice); every other service stays L4-only
    svc="${2:-productcatalogservice}"
    kubectl apply -f "$DIR/waypoint.yaml"
    kubectl label namespace boutique istio.io/use-waypoint- >/dev/null 2>&1 || true
    kubectl label service --all -n boutique istio.io/use-waypoint- >/dev/null 2>&1 || true
    kubectl label service "$svc" -n boutique istio.io/use-waypoint=waypoint --overwrite
    reconnect
    echo "Waypoint now serves only: $svc"
    ;;
  fault)
    need_waypoint
    kubectl apply -f "$DIR/scenarios/fault.yaml"
    ;;
  retry)
    need_waypoint
    kubectl apply -f "$DIR/scenarios/retry.yaml"
    ;;
  flaky)
    need_waypoint
    # The canary route sends traffic to the version-labelled v1/v2 Services, which the flaky pod is not in: remove it first.
    kubectl delete -f "$DIR/scenarios/canary.yaml" --ignore-not-found
    kubectl apply -f "$DIR/scenarios/flaky.yaml"
    kubectl rollout status -n boutique deploy/productcatalogservice-flaky --timeout=120s
    ;;
  timeout)  # 200ms request timeout on the canary route cuts off the slow v2 (400ms)
    if ! kubectl get httproute productcatalog-canary -n boutique >/dev/null 2>&1; then
      echo "Run ./03-scenario.sh canary first." >&2
      exit 1
    fi
    kubectl apply -f "$DIR/scenarios/timeout.yaml"
    ;;
  canary)  # 90/10 split between productcatalogservice v1 and a slower v2
    need_waypoint
    kubectl -n boutique patch deployment productcatalogservice --type merge \
      -p '{"spec":{"template":{"metadata":{"labels":{"version":"v1"}}}}}'
    kubectl -n boutique rollout status deployment/productcatalogservice --timeout=120s
    kubectl apply -f "$DIR/scenarios/canary.yaml"
    kubectl -n boutique rollout status deployment/productcatalogservice-v2 --timeout=120s
    ;;
  authz)
    kubectl apply -f "$DIR/scenarios/authz-l4.yaml"
    if kubectl get gateway waypoint -n boutique >/dev/null 2>&1; then
      kubectl apply -f "$DIR/scenarios/authz-l7.yaml"
    else
      echo "L7 authz needs the waypoint; run ./03-scenario.sh waypoint first." >&2
    fi
    ;;
  probe)  # unauthorized EmptyCart calls from an "intruder" workload (denied by the authz scenario)
    kubectl delete pod intruder -n boutique --ignore-not-found --now >/dev/null
    kubectl run intruder -n boutique --image=curlimages/curl --restart=Never --labels=app=intruder \
      --command -- sh -c 'for i in $(seq 120); do curl -s -o /dev/null --http2-prior-knowledge -X POST -H "content-type: application/grpc" http://cartservice:7070/hipstershop.CartService/EmptyCart; sleep 1; done'
    ;;
  outsider)  # a pod OUTSIDE the mesh calling frontend over plaintext (allowed until ./03-scenario.sh strict)
    kubectl wait --for=delete namespace/outside --timeout=90s >/dev/null 2>&1 || true   # a previous run may still be terminating
    kubectl create namespace outside --dry-run=client -o yaml | kubectl apply -f - >/dev/null
    kubectl delete pod outsider -n outside --ignore-not-found --now >/dev/null
    kubectl run outsider -n outside --image=curlimages/curl --restart=Never --labels=app=outsider \
      --command -- sh -c 'while true; do curl -s -o /dev/null -m 3 -w "%{http_code}\n" http://frontend.boutique.svc.cluster.local/ ; sleep 1; done'
    ;;
  strict)  # require mTLS: plaintext from the outsider is now refused
    kubectl apply -f "$DIR/scenarios/strict-mtls.yaml"
    ;;
  fresh)  # clean start for a rehearsal: remove scenarios, zero ztunnel's counters, clear TinyOlly's stored telemetry
    "$0" reset
    kubectl rollout restart daemonset/ztunnel -n istio-system
    kubectl rollout status daemonset/ztunnel -n istio-system --timeout=120s
    curl -s -m 20 -X POST "${TINYOLLY_URL:-http://localhost:5005}/admin/reset" >/dev/null \
      || echo "Could not reach TinyOlly; clear its data in the UI instead." >&2
    ;;
  reset)
    kubectl delete pod intruder -n boutique --ignore-not-found --now >/dev/null
    kubectl delete -f "$DIR/scenarios/fault.yaml" --ignore-not-found
    kubectl delete -f "$DIR/scenarios/retry.yaml" --ignore-not-found
    kubectl delete -f "$DIR/scenarios/flaky.yaml" --ignore-not-found
    kubectl delete -f "$DIR/scenarios/timeout.yaml" --ignore-not-found
    kubectl delete -f "$DIR/scenarios/canary.yaml" --ignore-not-found
    kubectl delete -f "$DIR/scenarios/strict-mtls.yaml" --ignore-not-found
    kubectl delete pod outsider -n outside --ignore-not-found --now >/dev/null 2>&1 || true
    kubectl delete namespace outside --ignore-not-found --wait=false
    kubectl delete -f "$DIR/scenarios/authz-l4.yaml" --ignore-not-found
    kubectl delete -f "$DIR/scenarios/authz-l7.yaml" --ignore-not-found
    kubectl delete -f "$DIR/waypoint.yaml" --ignore-not-found
    kubectl label namespace boutique istio.io/use-waypoint- 2>/dev/null || true
    kubectl label service --all -n boutique istio.io/use-waypoint- >/dev/null 2>&1 || true
    ;;
  *)
    echo "Usage: ./03-scenario.sh <waypoint|waypoint-svc [service]|fault|retry|flaky|timeout|canary|authz|probe|outsider|strict|reset|fresh>" >&2
    exit 1
    ;;
esac
case "${1:-}" in waypoint|waypoint-svc|fault|retry|flaky|timeout|canary|authz|probe|outsider|strict|reset) mark "$1" ;; esac

