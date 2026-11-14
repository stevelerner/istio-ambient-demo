# Task: f7-posture

## Goal
Add a mesh posture summary (mTLS coverage, plaintext edges, denied edges) computed from the merged service graph, exposed as `storage.get_mesh_posture()` and a `GET /api/mesh-posture` route.

## Read
docker/apps/tinyolly-common/tests/test_mesh_posture.py
docker/apps/tinyolly-common/tinyolly_common/mesh_adapters.py
docker/apps/tinyolly-common/tinyolly_common/storage_sqlite.py
docker/apps/tinyolly-ui/app/routers/services.py

## May change
docker/apps/tinyolly-common/tinyolly_common/mesh_adapters.py
docker/apps/tinyolly-common/tinyolly_common/storage_sqlite.py
docker/apps/tinyolly-ui/app/routers/services.py

## Constraints
- Do not edit tests.
- `metric_edges`: each edge also gets `denied`, the sum of counts of series whose `response_code == "403"` (same pattern as `errors`).
- `get_service_graph`: edges built from metrics also carry `denied_count` (= edge `denied`); trace-only edges get `denied_count: 0`. `merge_graph` combines parallel edges' `denied_count` with max.
- `mesh_adapters.posture(graph)` returns: `total_edges`, `mtls_edges` (mtls is True), `plaintext_edges` (mtls is False), `unknown_edges` (mtls None), `mtls_pct` (mtls_edges / (mtls_edges + plaintext_edges) * 100 rounded to 1 decimal; 0.0 when there are none), `plaintext` (list of `{"source","target","value"}` for plaintext edges), `denied` (list of `{"source","target","count"}` for edges with `denied_count` > 0).
- `StorageSQLite.get_mesh_posture()` returns `posture(await self.get_service_graph())`.
- Route `GET /mesh-posture` in the existing services router, same style as `/service-map` (operation_id `get_mesh_posture`).

## Shape
Plain dict code next to the existing functions. No new classes, no config.

## Done when
cd docker/apps/tinyolly-common && ../../../.venv-tests/tinyolly-common/bin/python -m pytest tests -q 2>&1 | tail -1 | grep -qE "^[0-9]+ passed"
