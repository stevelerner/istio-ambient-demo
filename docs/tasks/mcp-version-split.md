# Task: mcp-version-split

## Goal
Add an MCP tool `get_version_split(service, minutes)` that shows how a service's traffic splits across versions (canary view) using the Istio `istio_requests_total` metric.

## Read
docker/apps/tinyolly-mcp/tests/test_server.py
docker/apps/tinyolly-mcp/server.py

## May change
docker/apps/tinyolly-mcp/server.py

## Constraints
- Do not edit tests. Add one `@mcp.tool()` function `get_version_split(service: str, minutes: float = 10) -> str` in the metrics section, after `query_metric`, reusing `_api` and `_out` and following how `query_metric` builds `start`/`end` params and reads `d["series"]`.
- Call `_api("/api/metrics/query", name="istio_requests_total", start=end - minutes * 60, end=end, **{"attribute.destination_service_name": service})` with `end = time.time()`.
- For each series: `delta = max(0, last_value - first_value)` over its datapoints with non-None values (0 if none); `version = attributes.get("destination_version")`; `is_error` when `str(attributes.get("response_code", "")).startswith("5")`. Skip series with delta 0.
- Group by version: `requests` (sum of deltas), `errors` (sum of deltas of error series). Treat an empty or missing version as `"unknown"`.
- Output `{"service", "minutes", "total_requests", "versions": [...]}` where each version row is `{"version", "requests", "share_pct": round(requests / total * 100, 1), "errors", "error_rate_pct": round(errors / requests * 100, 1)}`, ordered by `requests` descending. Make request and error counts ints.
- If there are no series or no traffic return `{"service", "minutes", "total_requests": 0, "versions": [], "note": "no istio_requests_total data for this service (is the mesh metrics collector running?)"}`.
- Docstring: one or two sentences ("canary / version traffic split and error rate per version").

## Shape
One dict keyed by version; no helper classes or modules.

## Done when
cd docker/apps/tinyolly-mcp && .venv/bin/python -m pytest tests -q 2>&1 | tail -1 | grep -qE "^[0-9]+ passed"
