# Mesh metrics guide

What the demo collects, where it comes from, and how to read it in TinyOlly.

## How they get to TinyOlly
`mesh-metrics.yaml` runs an OpenTelemetry collector that scrapes the Prometheus endpoint (`:15020`) of every **ztunnel** pod and every **waypoint** pod every 15 seconds. It keeps only `istio_tcp*`, `istio_requests*`, `istio_request_duration*`, `istio_request_bytes*` and `istio_response_bytes*`, and sends them over OTLP to TinyOlly's receiver. The waypoint also sends traces; ztunnel sends metrics only.

## The metrics
| Metric | Type | From | What it tells you |
|---|---|---|---|
| `istio_tcp_connections_opened_total` | counter | ztunnel, waypoint | Connections started between two workloads. The base of the L4 map. |
| `istio_tcp_connections_closed_total` | counter | ztunnel, waypoint | Connections ended. |
| `istio_tcp_connections_failed_total` | counter | ztunnel | Connections that could not be made. |
| `istio_tcp_sent_bytes_total`, `istio_tcp_received_bytes_total` | counter | ztunnel, waypoint | Bytes each way. |
| `istio_tcp_sockets_open` | gauge | ztunnel | Connections open right now. |
| `istio_requests_total` | counter | waypoint | HTTP/gRPC requests, by response code. Needs a waypoint. |
| `istio_request_duration_milliseconds` | histogram | waypoint | Request latency, for p50/p95/p99. |
| `istio_request_bytes`, `istio_response_bytes` | histogram | waypoint | Request and response sizes. |

Without a waypoint you get the TCP metrics only: who talks to whom and how much, but no request rates, errors or latency. That is the L4 vs L7 split from the demo.

## Labels that matter
- **Who:** `source_workload` / `destination_workload`, `source_canonical_service` / `destination_canonical_service`, and their namespaces. TinyOlly uses these to draw edges.
- **Security:** `connection_security_policy` (`mutual_tls` or not) drives the green and orange edges and the mTLS percentage. `source_principal` / `destination_principal` are the SPIFFE identities.
- **Outcome (waypoint):** `response_code` (HTTP status), `grpc_response_status` (gRPC status code; `7` means permission denied) and `response_flags` (Envoy's reason code; `-` means none).
- **Who reported:** `reporter` is `source` or `destination`.

## Questions you can answer
| Question | Metric and filter |
|---|---|
| Who talks to whom? | `istio_tcp_connections_opened_total` by source and destination workload |
| Is everything encrypted? | `connection_security_policy` not `mutual_tls` means plaintext |
| What is being denied? | `istio_requests_total` with `response_code=403` or `grpc_response_status=7` |
| Is a service slow? | `istio_request_duration_milliseconds` p95 by destination |
| Where do errors come from? | `istio_requests_total` with 5xx `response_code`, by source and destination |
| Did a fault or retry change anything? | Compare p95 and error rate before and after the scenario |

In TinyOlly, the map and the posture bar already do the first three for you. The same questions work through the MCP tools: `get_mesh_posture`, `find_denied`, `find_plaintext` and `query_metric` (`labels` and `group_by`).

## Caveats
- Denied detection from metrics is a heuristic: HTTP 403, gRPC status 7, or a waypoint's own reply that has no destination. A trace or log confirms the exact call.
- gRPC errors arrive as HTTP 200 with a non-zero `grpc_response_status`, so check that label, not just `response_code`.
- Only the metrics above are forwarded. Envoy's other stats (`envoy_*`) and ztunnel's internal ones are filtered out to keep volume low.
