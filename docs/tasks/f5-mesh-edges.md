# Task: f5-mesh-edges

## Goal
Add a pure adapter that turns Istio metric series into service-to-service edges, and merge those edges into `get_service_graph` so a mesh with only ztunnel metrics still shows a map. Edges carry `source_kind` (traces | metrics | traces+metrics) and `mtls` (True/False, None for trace-only).

## Read
docker/apps/tinyolly-common/tests/test_mesh_adapters.py
docker/apps/tinyolly-common/tests/test_graph_metric_edges.py
docker/apps/tinyolly-common/tests/test_graph_edges.py
docker/apps/tinyolly-common/tinyolly_common/storage_sqlite.py

## May change
docker/apps/tinyolly-common/tinyolly_common/mesh_adapters.py
docker/apps/tinyolly-common/tinyolly_common/storage_sqlite.py

## Constraints
- Do not edit tests. New file `mesh_adapters.py` exposes `metric_edges(series) -> list[dict]`; `series` is the output of `get_metric_series` (items have `attributes` and `datapoints` with `timestamp`, `value`). Each returned edge: `source`, `target`, `count`, `mtls`, `errors`.
- Name = `source_canonical_service`, falling back to `source_workload` (same for destination). Skip empty or "unknown" names.
- Per series count = last value minus first value (single datapoint: its value; never negative). For one (source, target) pair take the MAX count across series (both reporters and L4/L7 series see the same traffic; never sum). `mtls` is True only if every series for the pair has `connection_security_policy == "mutual_tls"`. `errors` sums counts of series whose `response_code` starts with "5".
- In `get_service_graph`: fetch series for `istio_tcp_connections_opened_total` and `istio_requests_total` via `get_metric_series` and pass the concatenation to `metric_edges`. Existing trace edges get `source_kind: "traces"` and `mtls: None`. If a trace edge exists for the pair, keep its numbers and set `source_kind: "traces+metrics"` and `mtls`. Otherwise add an edge with `value=count`, `p95=0`, `req_rate=0`, `error_count=errors`, `source_kind: "metrics"`. Add missing endpoint nodes as type "service" with empty metrics.
- The early return when there are no traces must not hide metric edges: with no traces, still return metric edges and nodes. The result cache must still work.
- Run only the metric fetch inside the function; keep the adapter free of storage imports.

## Shape
One small pure function in a new module; in `get_service_graph` build a dict of metric edges keyed by (source, target) and merge it just before `graph_nodes`/`graph_edges` are assembled. No new classes, no config files.

## Done when
cd docker/apps/tinyolly-common && ../../../.venv-tests/tinyolly-common/bin/python -m pytest tests -q 2>&1 | tail -1 | grep -qE "^[0-9]+ passed" 
