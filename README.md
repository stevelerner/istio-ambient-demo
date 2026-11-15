# Istio ambient + TinyOlly demo

See Istio's sidecar-less "ambient" service mesh working on a Mac: encrypted traffic, policy enforcement and request-level detail, drawn live in [TinyOlly](https://github.com/tinyolly/tinyolly).

## Glossary
- **Ambient mode:** the newer Istio model with no sidecars. Proxies run per node or per namespace instead.
- **Authorization policy:** a rule like "only checkout may call EmptyCart".
- **Istio:** the most popular open-source service mesh. Runs on Kubernetes.
- **Kubernetes:** the system that runs and manages containerized apps. A **pod** is one running instance of a service. A **node** is one machine (or VM) in the cluster.
- **L4 vs L7:** L4 is the connection level (who connects to whom, bytes). L7 is the request level (HTTP/gRPC paths, headers, status codes).
- **mTLS (mutual TLS):** both sides prove their identity and the traffic is encrypted. "Mutual" means the server checks the client too.
- **OpenTelemetry (OTel):** the open standard for emitting telemetry.
- **Proxy:** a small program that sits between two services and handles their traffic. **Envoy** is the proxy Istio uses.
- **Retries, timeouts, fault injection:** automatically re-try failed calls, cap how long calls can take, and deliberately inject errors or delays to test resilience.
- **Service mesh:** a layer that handles how services talk to each other (security, routing, retries, metrics) so app code doesn't have to.
- **Sidecar:** the old Istio model, where an Envoy proxy runs inside every pod next to the app.
- **Telemetry:** metrics, traces and logs that show what the system is doing. A **trace** is the recorded path of one request across services.
- **TinyOlly:** a lightweight observability tool that receives OTel data and draws the service map.
- **Waypoint:** an optional Envoy proxy you add for a namespace or service when you need smarter, request-level features.
- **Zero trust:** don't trust traffic just because it's inside your network. Verify identity and permissions on every call.
- **ztunnel:** ambient's small per-node proxy. It encrypts traffic and identifies workloads, but only at the connection level.

## Why ambient exists
- **Problem with sidecars:** every pod carries its own proxy. That costs CPU and memory, adds delay, and makes upgrades awkward because pods must restart. It's also intrusive for app teams.
- **Goal:** keep the mesh benefits (encryption, identity, policy, visibility) with much less overhead.
- **How:**
  - **Cheap secure base:** ztunnel gives every workload mTLS and connection-level policy.
  - **Pay for L7 only where needed:** waypoints add request-level routing, retries and policy for the namespaces that need them.

## What a company gets from a mesh
- **Zero trust:** encrypted, identity-based traffic between services, with rules like "only checkout may call EmptyCart".
- **Resilience:** retries, timeouts and fault injection without changing app code.
- **Uniform visibility:** the same telemetry for every service, whatever language it's written in.

## Why this demo
Ambient is easy to describe but hard to see, because ztunnel is invisible. TinyOlly makes it visible:
- **Topology:** the map is built from ztunnel metrics alone.
- **Security:** mTLS coverage and plaintext gaps show up on the map.
- **Policy:** a denied call appears as a red edge.
- **Opt-in L7:** adding a waypoint makes traces and request-level detail appear.

## Prerequisites
- Mac with Colima, kind, kubectl, helm, Docker.
- A checkout of the TinyOlly repo (the demo targets its kind cluster `tinyolly`). It needs the platform changes that draw the mesh map (metric-derived edges, roles, posture). Build the shared `python-base` image before the UI image, with `DOCKER_CONTEXT=colima-tinyolly`: `docker build -t tinyolly/python-base:latest -f docker/dockerfiles/Dockerfile.tinyolly-python-base docker/`, then `k8s/04-rebuild+deploy-ui.sh`.

## Run it
```bash
# in the tinyolly repo
./scripts/colima-up.sh && ./scripts/kind-up.sh
k8s/02-deploy-tinyolly.sh

# in this repo
./01-deploy-istio.sh        # Istio ambient (Helm) + the mesh-metrics collector
./02-deploy-shop.sh         # Online Boutique in the mesh, ingress on :5001
./05-enable-tracing.sh      # app traces into TinyOlly
./03-scenario.sh waypoint   # add L7; also: fault | retry | authz | probe | reset
./04-cleanup.sh
```
Open http://localhost:5005 → **APM Service Map**, and http://localhost:5001 (the shop). Versions are pinned in `versions.env`. `check_scenarios.py` validates the scenario manifests (needs PyYAML and the kind cluster).

## Demo flow (~5 min)
1. **Mesh, no sidecars:** "ztunnel does L4 mTLS for every pod." Show the map, built purely from ztunnel metrics.
2. **Security posture:** point at the bar ("mTLS 92.5% · 3 plaintext"). Green edges are mTLS; orange dashed edges are plaintext, the zero-trust gap.
3. **Add L7 only where needed:** `./03-scenario.sh waypoint`. The waypoint node appears and traces stitch through (ingress → frontend → waypoint → services).
4. **Policy enforcement:** `./03-scenario.sh authz`, then `./03-scenario.sh probe` (about 2 minutes). A red edge appears from `intruder` to `cartservice` and the bar shows "1 denied", because only checkout may call `EmptyCart`.
5. **Resilience (optional):** `fault` or `retry` shows errors and retries as latency and error rates on edges.
6. **Toggle:** untick "Merge proxy and app nodes" for the layered mesh view.

Run `./03-scenario.sh reset` between rehearsals.

## Metrics guide
A collector (`mesh-metrics.yaml`) scrapes every ztunnel and waypoint pod every 15 seconds and sends the Istio metrics to TinyOlly over OTLP. TinyOlly draws the map and the mTLS / denied posture from them.

Metric types:
- **Counter:** a number that only goes up (resets on restart), such as total requests. Look at its rate of change, not the raw value.
- **Gauge:** a value that goes up and down, such as connections open right now. Read it as it is.
- **Histogram:** counts of observations in buckets (for example how many requests took under 10 ms, under 50 ms), which lets you compute percentiles like p95.

| Metric | Type | From | What it tells you |
|---|---|---|---|
| `istio_tcp_connections_opened_total` / `_closed_total` / `_failed_total` | counter | ztunnel, waypoint | Who connected to whom. The base of the map, available with no waypoint |
| `istio_tcp_sent_bytes_total` / `istio_tcp_received_bytes_total` | counter | ztunnel, waypoint | Bytes each way |
| `istio_tcp_sockets_open` | gauge | ztunnel | Connections open right now |
| `istio_requests_total` | counter | waypoint | HTTP/gRPC requests by response code (errors, denials). Needs a waypoint |
| `istio_request_duration_milliseconds` | histogram | waypoint | Request latency (p50 / p95 / p99) |
| `istio_request_bytes` / `istio_response_bytes` | histogram | waypoint | Request and response sizes |

Labels to look at:
- **Who:** `source_workload`, `destination_workload` (and `_canonical_service`, namespaces).
- **Encrypted?** `connection_security_policy`: `mutual_tls` means mTLS, anything else is plaintext.
- **Outcome:** `response_code` (HTTP status), `grpc_response_status` (`7` = permission denied) and `response_flags` (Envoy's reason code).

| Question | Look at |
|---|---|
| Who talks to whom? | TCP connections by source and destination workload |
| Is everything encrypted? | `connection_security_policy` (TinyOlly's posture bar shows the percentage) |
| What is being denied? | `istio_requests_total` with `response_code=403` or `grpc_response_status=7` (red edges) |
| Is a service slow? | `istio_request_duration_milliseconds` p95 by destination |
| Did a scenario change anything? | Compare p95 and error rate before and after `./03-scenario.sh` |

Without a waypoint you only get the TCP metrics. Add one with `./03-scenario.sh waypoint` to get request rates, errors and latency. Details and caveats: [docs/METRICS.md](docs/METRICS.md).

## Docs
`docs/PLAN.md` (demo plan and spike findings), `docs/TINYOLLY-PLAN.md` (the product changes), `docs/AMBIENT-NOTES.md` (ambient notes), `docs/METRICS.md` (mesh metrics guide), `docs/DELEGATION.md` and `docs/tasks/` (Qwen delegation specs).
