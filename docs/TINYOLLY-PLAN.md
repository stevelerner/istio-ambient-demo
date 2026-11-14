# Plan: make TinyOlly observe meshes, gateways and proxies

Date: 2026-11-14. Status: draft, nothing built. Companion to `PLAN.md` (the demo). The demo is the proof; this is the product work.

## Pitch
Most observability tools handle app spans well and fall apart on proxies: duplicate nodes, double-counted rates, empty maps when there are no traces, and no way to tell mesh time from app time. TinyOlly will model **proxies, gateways and mesh layers as first-class things**, driven by OTel conventions and a small rules file, so it works for Istio ambient and sidecar, kgateway, agentgateway, Envoy Gateway, Linkerd and NGINX ingress, not just one product.

## Why tools struggle (and what TinyOlly does about it)
| Problem | Today in TinyOlly (read from the code) | Fix |
|---|---|---|
| A proxied hop emits CLIENT and SERVER spans, in the proxy and in the app | `get_service_catalog` counts **every span** per `service.name`, so rate and error rate double count | F1: kind-aware RED |
| Proxy spans carry their own `service.name` (`frontend.default`, `waypoint`, `ztunnel`) | One node each; the map shows two nodes per real service | F2, F3: roles and logical identity |
| Edges ignore span kind, `peer.service`, `server.address`; no error count; `req_rate = count/60` is hard-coded | `get_service_graph` builds edges only from parent/child spans with different `service.name`, plus db/messaging | F4: edge model |
| L4-only layers (ztunnel) emit **metrics, no traces** | Map is built only from spans, so it is empty while metrics are full | F5: topology from metrics |
| "Is mTLS on? What was denied?" lives in metric labels and Envoy response flags | Not surfaced | F6, F7 |
| Mesh latency is invisible | Waterfall shows proxy spans as ordinary services | F6: mesh overhead |
| Retries, canaries, ingress routes | No grouping by version, route or attempt | F6, F8, F9 |
| LLM, MCP and agent traffic through a gateway | AI Agents tab exists but is not tied to the map or to gateway policy | F10 |

## Features
Order is by value and dependency. Code areas are where the change lands.

**F1. Kind-aware RED (correctness, benefits everyone).** Count SERVER (and CONSUMER) spans for rate/errors/latency; fall back to all spans for services with no server spans. Compute rate from the real time window, not `span_count/300`. `kind` is already stored per span. Area: `storage_sqlite.get_service_catalog`.

**F2. Role detection.** Classify nodes as `service | gateway | proxy | waypoint | ztunnel | external | llm | mcp`. From attributes and names via a rules file with built-in presets (istio, envoy, kgateway, agentgateway): `istio.*`, `component=proxy`, `upstream_cluster`, `gen_ai.*`, `mcp.*`, k8s labels. New node shapes and badges in the map; same shapes in the MCP charts. Area: graph builder, `serviceMapUtils.js`, `render.py`.

**F3. Logical identity.** Optionally merge proxy and app identities into one service using `k8s.workload.name` / canonical-service labels or rewrite rules (strip `.namespace`). UI toggle: **Merged** (clean map) vs **Layered** (app and proxy nodes, shows mesh). Merging must not lose the proxy spans; they stay in traces. Area: graph builder, catalog, UI toggle.

**F4. Better edges.** Use CLIENT to SERVER by kind and `peer.service` / `server.address`; collapse A to proxy to B into A to B with a proxy badge; add `error_count`, real `req_rate`, protocol (HTTP, gRPC, TCP) and an mTLS flag. (The MCP service-map chart already reads `error_count`; today nothing supplies it.) Area: `get_service_graph`.

**F5. Topology from metrics.** Teach the graph about known mesh metrics (`istio_tcp_*`, `istio_requests_total`, labels `source_workload`, `destination_workload`, `connection_security_policy`, `response_code`, `response_flags`). Add metric-derived edges tagged `source: metrics`, merged with trace edges, so an ambient namespace with only ztunnel still shows a map. Adapter is a config mapping, not Istio code in the core. Area: new `mesh_adapters` module in `tinyolly-common`, graph builder.

**F6. Mesh view in the trace.** For proxied hops show app to proxy to proxy to app, compute **mesh time** (client span duration minus server span duration, minus network), mark retry attempts, and decode response flags (`UH`, `UF`, `NR`, `RBAC`, ...) in plain language. Area: `traces.js`, `traceMap.js`, small API addition.

**F7. mTLS and policy posture.** A panel and API: % of edges with mutual TLS, plaintext edges, denied edges (RBAC flags or 403). This is the POC proof for zero trust. Area: new endpoint under `routers/`, new UI card on the map page.

**F8. Ingress view.** Traffic entering via a gateway by host and route: RED per route, 4xx/5xx by flag. Area: catalog variant keyed by route attributes.

**F9. Version and canary split.** Group edges and RED by `version` / `destination_version`; show traffic split and p95 per version. Area: graph builder, UI filter.

**F10. AI traffic through the gateway.** Add LLM and MCP-server nodes, per-tool allow/deny counts, token use per caller identity, and edges from agents through agentgateway to providers, linked from the AI Agents tab. Uses `gen_ai.*` attributes. Area: graph builder, `aiAgents.js`.

**F11. Collector preset `istio-mesh`.** OpAMP-delivered preset (fits the existing preset system): OTTL to tag `mesh.role`, normalise `service.name`, drop noisy labels, plus the `mesh-metrics` scrape config. Area: `otelcol-configs/templates/`, `docs/collector-presets.md`.

**F12. MCP and docs.** `get_service_map` returns node roles and edge provenance; charts get the new shapes; an MCP-only skill `tinyolly-mesh-investigation`; `docs/istio.md` and a docs page on the rules file. No local skills (MCP only).

## Phases (each lands with tests, usable on its own)
- **T0 Data audit** (during the demo spike): capture real OTLP from ambient waypoint, ztunnel metrics, kgateway and agentgateway into `tests/fixtures/`. Decide rules from facts: which attributes exist, how names look, whether log records carry trace IDs.
- **T1 Correctness: F1, F4 (errors, rates).** Useful immediately for any app.
- **T2 Identity and roles: F2, F3.** Fixes duplicate nodes, adds shapes and the Merged/Layered toggle.
- **T3 Metrics topology and posture: F5, F7.** Map works with no waypoint; mTLS coverage and denies visible.
- **T4 Trace and routing views: F6, F8, F9.**
- **T5 AI path: F10.**
- **T6 Presets, MCP, docs: F11, F12.**

## Testing (local only, no CI; functionality, no security tests)
- Unit tests in `tinyolly-common` and the UI with golden OTLP fixtures from T0 (kind-aware RED, merge rules, edge building, metric adapters).
- Frontend `node --test` for new shape and badge logic (`serviceMapUtils.js`).
- MCP tests for the new fields and chart shapes.
- `scripts/test-istio.sh`: runs against the live kind demo and asserts the success criteria below; wired into `scripts/test-all.sh --stack`.

## Success criteria
- Online Boutique shows its 11 services plus ingress, no duplicate proxy nodes in Merged mode.
- A service's rate matches the load generator rate within a few percent (no double counting).
- With ambient and no waypoint the map still shows edges (from metrics); after the `waypoint` scenario traces and spans appear and the map keeps the same nodes.
- mTLS coverage reads 100%; the `authz` scenario shows the denied edge; the `canary` scenario shows the traffic split and p95 per version.
- The waterfall shows mesh time for a proxied hop.

## Risks
- **Graph builder cost:** it decodes spans per request (cached); new logic must stay within the cache and the 30-minute retention.
- **Cardinality:** Istio metrics have many labels; keep an allow-list and respect the 1000 metric-name limit.
- **Overfitting to Istio:** keep Istio-specific knowledge in adapters and rules files, with generic OTel attributes as the default path.
- **UI churn:** add the Merged/Layered toggle and node shapes without breaking the current map; keep `serviceMapUtils.js` pure and tested.
- **Unknown attributes:** rules depend on what ambient, kgateway and agentgateway really emit; T0 decides, not assumptions.
