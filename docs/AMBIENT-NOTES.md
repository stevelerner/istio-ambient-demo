# Istio ambient: notes

Short, accurate, and tied to what the demo shows. Verify version details against [istio.io](https://istio.io/latest/docs/ambient/) and [ambientmesh.io](https://ambientmesh.io/) as versions move.

## Glossary
Basics (mesh, sidecar, ztunnel, waypoint, L4/L7, mTLS) are in the [README glossary](../README.md#glossary). Terms used in these notes:

- **Ambient mode:** Istio without sidecars. A per-node ztunnel handles L4; an optional waypoint handles L7.
- **ztunnel:** the per-node agent (written in Rust, not Envoy) that does mTLS, identity, L4 policy and TCP metrics.
- **Waypoint:** an optional Envoy proxy for a namespace or service, giving L7 routing, retries, policy, traces and HTTP metrics.
- **HBONE:** the tunnel ambient uses between nodes: HTTP/2 CONNECT carrying the traffic inside mTLS, on port 15008.
- **SPIFFE ID:** a workload's identity, a URL-style name such as `spiffe://cluster.local/ns/boutique/sa/frontend`, put in the certificate used for mTLS.
- **CNI (`istio-cni`):** a node plugin that redirects a pod's traffic to ztunnel, so no sidecar or app change is needed.
- **Namespace:** a Kubernetes grouping of workloads. Labelling one `istio.io/dataplane-mode=ambient` puts it in the mesh.
- **Gateway API:** the Kubernetes standard for ingress and routing. A **Gateway** is an entry point; an **HTTPRoute** says where requests go. Waypoints are also Gateways (`gatewayClassName: istio-waypoint`).
- **AuthorizationPolicy:** the Istio rule that allows or denies calls, for example "only checkout may call EmptyCart". **PeerAuthentication** sets whether mTLS is required.
- **Telemetry:** metrics, traces and logs. ztunnel gives metrics only; a waypoint adds traces.
- **Denied call:** a request blocked by policy. It shows as HTTP 403, or as gRPC status 7 (permission denied) on an HTTP 200, or as a waypoint's own reply with no destination.
- **Blast radius / noisy neighbour:** how much breaks if a shared component fails, and one workload's load slowing the others. Both matter more for a per-node ztunnel than for per-pod sidecars.

## The 60-second answer
Ambient is Istio without sidecars. The mesh is split in two layers you adopt separately:
- **L4, secure overlay:** a **ztunnel** per node (a Rust agent, not Envoy) gives mTLS, workload identity (SPIFFE), L4 authz and TCP telemetry. Traffic between pods is tunnelled over **HBONE** (HTTP/2 CONNECT with mTLS, port 15008). `istio-cni` redirects pod traffic to ztunnel.
- **L7, optional:** a **waypoint** proxy (Envoy), deployed per namespace or per service through the Kubernetes Gateway API (`gatewayClassName: istio-waypoint`), gives HTTP routing, retries, timeouts, fault injection, L7 authz and HTTP telemetry. Opt in with `istio.io/use-waypoint`.
- Join the mesh with a label: `istio.io/dataplane-mode=ambient` on a namespace. No restart, no injection.

## Why ambient
- No sidecar per pod: less CPU/memory, no app restarts to upgrade the mesh, no sidecar/app startup ordering bugs, apps and the mesh upgrade independently.
- Incremental: get mTLS for everything first, pay for L7 only where you need it.
- Same Istio APIs (`AuthorizationPolicy`, `PeerAuthentication`, Gateway API routes).

## Trade-offs to be honest about
- L7 features need a waypoint, an extra hop and a thing to operate.
- ztunnel is shared per node (blast radius, noisy neighbours), unlike per-pod sidecars.
- Newer than sidecars: check feature parity and the CNI/kernel requirements for the target platform.
- L4 telemetry only without a waypoint: **no traces**. (This is exactly what the TinyOlly demo shows.)

## Demo mapping
| Talking point | Where it shows in the demo |
|---|---|
| mTLS for free | ztunnel TCP metrics with `connection_security_policy=mutual_tls`; posture bar in TinyOlly |
| L4 vs L7 layering | Spans and L7 detail appear only after the `waypoint` scenario |
| Policy you can verify | `authz` + `probe` scenarios: a red denied edge, `find_denied` in MCP |
| Enforced mTLS | `outsider` then `strict` scenarios: a plaintext call from outside the mesh works, then is refused |
| Pay for L7 only where needed | `waypoint-svc <service>`: one service gets request metrics and traces, the rest stay L4 |
| Safe rollouts | `canary` scenario: 90/10 split between v1 and a slower v2, visible per version in TinyOlly |
| Resilience | `fault` and `retry` scenarios |
| Ingress | Istio Gateway API (`ingress.yaml`) in front of the shop on port 5001 |
