#!/bin/bash
# Apply an Istio ambient scenario (waypoint, fault, retry, authz) or reset them.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib/kubectx.sh" && require_kind_context

need_waypoint() {
  if ! kubectl get gateway waypoint -n boutique >/dev/null 2>&1; then
    echo "Waypoint 'waypoint' not found in namespace boutique. Run ./03-scenario.sh waypoint first." >&2
    exit 1
  fi
}

case "${1:-}" in
  waypoint)
    kubectl apply -f "$DIR/waypoint.yaml"
    kubectl label namespace boutique istio.io/use-waypoint=waypoint --overwrite
    ;;
  fault)
    need_waypoint
    kubectl apply -f "$DIR/scenarios/fault.yaml"
    ;;
  retry)
    need_waypoint
    kubectl apply -f "$DIR/scenarios/retry.yaml"
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
  reset)
    kubectl delete pod intruder -n boutique --ignore-not-found --now >/dev/null
    kubectl delete -f "$DIR/scenarios/fault.yaml" --ignore-not-found
    kubectl delete -f "$DIR/scenarios/retry.yaml" --ignore-not-found
    kubectl delete -f "$DIR/scenarios/authz-l4.yaml" --ignore-not-found
    kubectl delete -f "$DIR/scenarios/authz-l7.yaml" --ignore-not-found
    kubectl delete -f "$DIR/waypoint.yaml" --ignore-not-found
    kubectl label namespace boutique istio.io/use-waypoint-
    ;;
  *)
    echo "Usage: ./03-scenario.sh <waypoint|fault|retry|authz|probe|reset>" >&2
    exit 1
    ;;
esac
