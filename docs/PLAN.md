# Plan: Istio ambient demo for TinyOlly ("how to visualize a service mesh")

Date: 2026-11-14. Status: draft for review, nothing built. Decision (owner): ambient mode, no Envoy sidecars.

## Goal
**Two deliverables:** the demo (this file) and the TinyOlly changes that let it observe meshes, gateways and proxies (`TINYOLLY-PLAN.md`). The second is the real differentiator.

One-command demo on a Mac: kind on Colima, Istio ambient, a shopping app, an OTel collector, TinyOlly as the only UI. The story: what the mesh gives you **with no sidecars and no app changes** (L4 metrics, mTLS), then what turns on when you add a **waypoint** (L7 traces, logs, metrics, traffic policy), with scripted scenarios whose effects show up in TinyOlly.

## Ambient in one paragraph (drives the whole design)
- **ztunnel** (a Rust node agent, not Envoy) handles L4: mTLS, TCP routing, L4 authz. It emits **TCP metrics and logs, but no traces**.
- **waypoint** (an Envoy proxy, installed per namespace or service) handles L7: HTTP metrics, **traces**, access logs, retries, canary, fault injection, L7 authz. Envoy only appears here, and only if you opt in.
- So without a waypoint TinyOlly sees connection counts and bytes between services; with one it sees requests, spans and logs. That contrast is the demo.


## Stack change from the earlier draft
Ingress was planned as kgateway; the demo instead uses Istio's own Gateway API implementation (`ingress.yaml`, `GatewayClass istio`, NodePort 30001 mapped to host :5001), which needs no extra install. Its Envoy emits traces/metrics/logs to the collector too, so the map gets an ingress node.

## Conventions copied from your other demos (TinyOlly repo)
Numbered scripts, `kubectx.sh` guard so nothing touches a non-kind cluster, versions pinned in `versions.env`, a docs page with one copyable block, a README section, local-only test script (no CI). (`/code/stevelerner` is only the GitHub profile README, so there was no demo layout to copy there.)

## Decisions (recommended; push back on any)
| Topic | Choice | Why |
|---|---|---|
| Runtime | kind cluster `tinyolly` on Colima profile `tinyolly`; start with `COLIMA_MEMORY=6`, raise to 8 if tight | Existing setup and guard. Shop on :5001, TinyOlly on :5005 via the existing kind port map. Not alongside `k8s-demo`. |
| Istio | 1.32.0 (latest release, 2026-11-09), Helm: `base`, `istiod` (ambient profile), `istio-cni`, `ztunnel`; kgateway separately | Helm is already a prerequisite; no `istioctl`. Pin chart versions in `versions.env`. |
| Mode | Ambient. Sidecar mode only as a stretch comparison | Owner choice. |
| App | Google Online Boutique v0.10.7 (11 services, polyglot, built-in load generator) | The standard mesh shopping demo; lighter than Astronomy Shop. |
| Ingress | kgateway (Helm, Gateway API), Service NodePort 30001 (host :5001) | reuses the kind port map. Check kgateway can route to ambient services. |
| Collector | TinyOlly's collector (OTLP in, OpAMP-managed) plus a small `mesh-metrics` collector that scrapes ztunnel and waypoint and forwards OTLP | Keeps the OpAMP-managed collector untouched; no RBAC changes there. |

## Telemetry design
- **Metrics (always on):** `mesh-metrics` collector with a Prometheus receiver, pod discovery on `:15020/stats/prometheus` for ztunnel (DaemonSet) and waypoints. ztunnel gives `istio_tcp_connections_opened_total`, `istio_tcp_sent_bytes_total` and friends, labelled by source/destination workload and `connection_security_policy`. A waypoint adds `istio_requests_total` and duration histograms. Keep that set; drop the rest to respect TinyOlly's cardinality limit (1000 metric names).
- **Traces (waypoint only):** `meshConfig.extensionProviders` OpenTelemetry provider to `otel-collector:4317`, enabled with a `Telemetry` resource on the waypoint, 100% sampling (demo only).
- **Access logs (waypoint; ztunnel optional):** `envoyOtelAls` provider from the waypoint to the collector, trace-correlated if the record carries trace/span IDs (verify). ztunnel only logs to stdout; ship it with a `filelog` receiver in `mesh-metrics` if worth it.
- **Service map from L4 metrics:** TinyOlly's map is built from spans. With no waypoint there are no spans, so the map would be empty while metrics are full. Options: (a) accept it and say so in the docs (the contrast is the point); (b) have `mesh-metrics` turn ztunnel TCP metrics into edges using the `servicegraph`-style connector or a small TinyOlly addition. Decide in the spike.

## Scenarios (`03-scenario.sh`)
| Name | Mesh feature | Needs | What you see in TinyOlly |
|---|---|---|---|
| (baseline) | Namespace labelled `istio.io/dataplane-mode=ambient` | ztunnel | TCP metrics and mTLS between all services, no spans |
| `waypoint` | Deploy a waypoint, label the namespace to use it | waypoint | Spans, access logs and HTTP metrics appear |
| `canary` | HTTPRoute 90/10 to `productcatalog` v1/v2 (v2 slower) | waypoint | Edge split on the map, p95 per version |
| `fault` | Delay/abort on `currency` | waypoint | Error rate and latency in catalog and map, red spans |
| `retry` | Retries, timeout, outlier detection | waypoint | Repeated attempt spans, `response_flags` in logs |
| `authz` | L4 policy by service account (ztunnel), then L7 policy (waypoint) | both | L4 deny shows as dropped connections; L7 deny as 403s with `RBAC` in logs |
| `reset` | Remove all of the above | | Baseline |

## Biggest risks (check in Phase 0)
1. **Ambient on kind inside Colima.** `istio-cni` and ztunnel need to work in the Colima VM's kernel. Documented for kind, but untested on Colima here. Fallback: the `tinyolly` Colima profile with a different kernel/VM type, or sidecar mode.
2. **Trace stitching.** The waypoint only joins traces if apps forward trace headers, and Online Boutique is partly instrumented. Fallback: set OTel env vars on every service, or use Astronomy Shop's Helm chart (fully instrumented, heavier).
3. **Waypoint naming.** One waypoint per namespace means spans carry the waypoint's `service.name`, not each service's, so the map may show one "waypoint" node in the middle. Per-service waypoints or an OTTL preset to rewrite names may be needed.
4. **Empty map without waypoint** (see telemetry design).
5. **Memory.** Estimate ~3 GB total (istiod, CNI, ztunnel, one waypoint, shop ~1.5 GB, TinyOlly ~0.8 GB). Not measured.
6. **Image arch:** confirm all Boutique images run on arm64.

## Phases (each ends with something you can look at)
Run the TinyOlly work (`TINYOLLY-PLAN.md`, T0 to T6) alongside these: the spike feeds T0 fixtures, and each demo phase is the proving ground for a TinyOlly phase.
0. **Spike (half day):** kind + ambient Istio + Boutique + TinyOlly core on the Colima VM. See ztunnel metrics, then add a waypoint and see spans and logs. Settle risks 1-4. Output: findings added to this file.
1. **Core demo:** this repo (repo root) with `01-deploy-istio.sh`, `02-deploy-shop.sh`, `04-cleanup.sh`, `mesh-metrics` collector, Telemetry config, `versions.env` pins.
2. **Scenarios:** `03-scenario.sh` with the scenarios above, each verified in the UI.
3. **Docs and polish:** `docs/istio.md` (copyable block, screenshots, "what to look at"), mkdocs nav, README and feature list entry, `scripts/test-istio.sh` (local only, API assertions on metrics, spans after `waypoint`, scenario effects).
4. **Act 2, agentic mesh (core):** reuse TinyOlly's AI agent demo (Ollama) as a shopping assistant in the ambient mesh; route its LLM and MCP tool calls through open-source agentgateway; show identity, a per-tool allow/deny policy and credential brokering, with GenAI spans, tokens and tool calls in TinyOlly's AI Agents tab. Check whether OSS agentgateway can run as an ambient waypoint; otherwise use it as an in-mesh gateway.
5. **Stretch:** sidecar-mode comparison, a collector preset for mesh naming, an MCP investigation skill for mesh issues (served only through the MCP server).

## Decisions
- **Where does the demo live?** Decided: its own repo (`istio-ambient-demo`), not inside TinyOlly. TinyOlly keeps only platform changes.
- **Empty map without a waypoint: accept it or draw edges from ztunnel metrics?** Decided and built: TinyOlly now derives edges from Istio metrics (F5), merges them with trace edges, and shows mTLS, plaintext and denied state.
- **Which shop app?** Online Boutique v0.10.7, unmodified except cartservice memory raised to 256Mi.
- **Ingress?** Istio Gateway API, not kgateway; swapping in another Gateway API implementation is a later option.
- **Canary / version scenarios?** Built: `canary` (90/10 split of `productcatalogservice` v1/v2 with Gateway API weights). Scenarios: `waypoint`, `waypoint-svc`, `canary`, `outsider`, `strict`, `authz`, `probe`, `fault`, `retry` and `reset`.

## Phase 0 findings (2026-11-14, run on a 24 GB Mac, Colima 4 CPU / 6 GiB)
- **Risk 1 (ambient on kind in Colima): works.** Istio 1.30.8 ambient (base, istiod, cni, ztunnel via Helm) came up healthy. Note: the Istio Helm repo's newest stable is **1.30.8**, not 1.32.0; pinned in `versions.env`.
- **Risk 6 (arm64): fine.** All 12 Online Boutique v0.10.7 pods run.
- **Risk 5 (memory): ~2.6 GiB used of 5.8 GiB** with Istio, the shop, TinyOlly core, a waypoint and the collector. 6 GiB is enough.
- **ztunnel metrics are rich:** `istio_tcp_*` carries `source_workload`, `destination_workload`, SPIFFE principals and `connection_security_policy="mutual_tls"`. They arrive in TinyOlly (33 label combos per metric) but attributed to one service, `ztunnel`. **The service map shows no Boutique edges at L4.** This confirms F5 (topology from metrics) is needed.
- **Waypoint spans arrive as a single node `waypoint.boutique`** (risk 3 confirmed), kind CLIENT, name `host:port/*`, no per-service `service.name`. Online Boutique services emit no spans themselves yet, so there are no SERVER spans to stitch (risk 2 open). 43 of 122 sampled waypoint spans have status ERROR with HTTP 200 (gRPC status), which inflates `waypoint.boutique` error rate to ~40%: F1 and F6 matter.
- **Collector:** the core OTLP receiver takes OTLP gRPC directly on `tinyolly-otlp-receiver:4343`, so `mesh-metrics` and the waypoint export there with no OpAMP collector needed.
- **Built so far:** this repo (repo root) has `mesh-metrics.yaml`, `waypoint.yaml`, `versions.env`, `01-deploy-istio.sh`, `02-deploy-shop.sh`, `04-cleanup.sh`.
