# Istio ambient: notes

Short, accurate, and tied to what the demo shows. Verify version details against [istio.io](https://istio.io/latest/docs/ambient/) and [ambientmesh.io](https://ambientmesh.io/) before the call.

## The 60-second answer
Ambient is Istio without sidecars. The mesh is split in two layers you adopt separately:
- **L4, secure overlay:** a **ztunnel** per node (a Rust agent, not Envoy) gives mTLS, workload identity (SPIFFE), L4 authz and TCP telemetry. Traffic between pods is tunnelled over **HBONE** (HTTP/2 CONNECT with mTLS, port 15008). `istio-cni` redirects pod traffic to ztunnel.
- **L7, optional:** a **waypoint** proxy (Envoy), deployed per namespace or per service through the Kubernetes Gateway API (`gatewayClassName: istio-waypoint`), gives HTTP routing, retries, timeouts, fault injection, L7 authz and HTTP telemetry. Opt in with `istio.io/use-waypoint`.
- Join the mesh with a label: `istio.io/dataplane-mode=ambient` on a namespace. No restart, no injection.

## Why customers care
- No sidecar per pod: less CPU/memory, no app restarts to upgrade the mesh, no sidecar/app startup ordering bugs, apps and the mesh upgrade independently.
- Incremental: get mTLS for everything first, pay for L7 only where you need it.
- Same Istio APIs (`AuthorizationPolicy`, `PeerAuthentication`, Gateway API routes).

## Trade-offs to be honest about
- L7 features need a waypoint, an extra hop and a thing to operate.
- ztunnel is shared per node (blast radius, noisy neighbours), unlike per-pod sidecars.
- Newer than sidecars: check feature parity and the CNI/kernel requirements for the target platform.
- L4 telemetry only without a waypoint: **no traces**. (This is exactly what the TinyOlly demo shows.)

## Questions to ask a customer (discovery)
- Sidecars today? What hurts: resource cost, upgrades, startup issues, ownership between app and platform teams?
- Is mTLS between all services a requirement (compliance, zero trust)? Who has to prove it?
- How many clusters, regions, clouds? Any need for cross-cluster failover?
- Which workloads need L7 policy, and which only need encryption?
- What do they use for ingress today (NGINX, cloud LB, Kong)? Any plan for Gateway API?
- How is observability done today, and what would they need to see to trust the mesh?

## Demo mapping
| Talking point | Where it shows in the demo |
|---|---|
| mTLS for free | ztunnel TCP metrics with `connection_security_policy=mutual_tls` |
| L4 vs L7 layering | Spans and map appear only after the `waypoint` scenario |
| Policy you can verify | `authz` scenario: denied connections / 403s in logs |
| Safe rollouts | `canary` scenario with p95 per version |
| Resilience | `fault` and `retry` scenarios |
| Ingress | kgateway in front of the shop |
