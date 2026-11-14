# Task: f3-merge-roles

## Goal
Add node roles (F2) and a Merged vs Layered view (F3) to the service graph: pure helpers in `mesh_adapters.py`, wired into `get_service_graph(limit, merge=True)` and the `/service-map` route as `?merge=true|false`.

## Read
docker/apps/tinyolly-common/tests/test_graph_merge.py
docker/apps/tinyolly-common/tests/test_graph_metric_edges.py
docker/apps/tinyolly-common/tinyolly_common/mesh_adapters.py
docker/apps/tinyolly-common/tinyolly_common/storage_sqlite.py
docker/apps/tinyolly-ui/app/routers/services.py

## May change
docker/apps/tinyolly-common/tinyolly_common/mesh_adapters.py
docker/apps/tinyolly-common/tinyolly_common/storage_sqlite.py
docker/apps/tinyolly-ui/app/routers/services.py

## Constraints
- Do not edit tests. Add to `mesh_adapters.py`: `canonical_name(name, namespaces)` (strip one trailing `.<ns>` only when `<ns>` is in `namespaces`), `node_role(name)` (`waypoint` if name starts with "waypoint"; `gateway` if it ends with "-istio" or contains "ingress" or "gateway"; `ztunnel` if it starts with "ztunnel"; else `service`), `metric_namespaces(series)` (set of non-empty `source_workload_namespace` and `destination_workload_namespace` values), and `merge_graph(graph, namespaces)`.
- `merge_graph` returns a new graph: rename nodes with `canonical_name`, combine nodes that collide (keep the one whose `metrics.span_count` is larger, default 0), set `role` on every node, rename edge endpoints, combine edges with the same (source, target) by taking the one with the larger `value` as the base, then set `p95`, `error_count` and `req_rate` to the max over the combined edges, `source_kind` to "traces+metrics" if the combined edges include both a trace kind ("traces" or "traces+metrics") and a metrics kind, otherwise the base kind, and `mtls` to the first non-None value (base first), else None. Drop edges whose source equals target. With empty `namespaces` nothing is renamed but roles are still added.
- In `get_service_graph`: add `merge: bool = True`, include it in the cache key (bump to `service_graph_cache_v4`), collect namespaces with `metric_namespaces` from the metric series already fetched, and apply `merge_graph(result, namespaces if merge else set())` before caching and returning. Also make sure the metrics-only path (no traces) goes through it.
- Router: add `merge: bool = Query(default=True, ...)` and pass it through.

## Shape
Plain functions with dicts; reuse the series already fetched in `get_service_graph`. No classes, no config files.

## Done when
cd docker/apps/tinyolly-common && ../../../.venv-tests/tinyolly-common/bin/python -m pytest tests -q 2>&1 | tail -1 | grep -qE "^[0-9]+ passed"
