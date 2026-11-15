# Task: mcp-metric-labels

## Goal
Make the MCP `query_metric` tool usable for Istio metrics: add a `labels` filter and a `group_by` aggregation over metric attributes.

## Read
docker/apps/tinyolly-mcp/tests/test_server.py
docker/apps/tinyolly-mcp/server.py

## May change
docker/apps/tinyolly-mcp/server.py

## Constraints
- Do not edit tests. Change only `query_metric` (and a helper next to it if needed); keep existing behaviour and parameters unchanged when the new ones are not used.
- New param `labels: dict[str, str] | None = None`: each pair is sent to `/api/metrics/query` as `attribute.<key>=<value>`.
- New param `group_by: str | None = None`: when set, skip the per-series output and group the returned series by `series["attributes"].get(group_by)` (a missing label groups under `None`). Per series use its datapoints with non-None values: `last` = final value, `delta` = last minus first value. Per group: `{"value": <label value>, "series_count": n, "last_sum": sum of lasts, "delta_sum": sum of deltas}`, rounded with `round(x, 6)`.
- Output when grouping: `{"name", "type", "unit", "group_by", "series_total": <number of series returned by the API>, "groups_total": <number of groups>, "groups": [...]}`. Sort groups by `delta_sum` descending, with the `None` group always last; keep only the first `max_series` groups (existing clamp `max(1, min(max_series, 50))`). No `series` key.
- Update the docstring to mention both params.

## Shape
Build groups with a plain dict keyed by the label value; no new classes or modules.

## Done when
cd docker/apps/tinyolly-mcp && .venv/bin/python -m pytest tests -q 2>&1 | tail -1 | grep -qE "^[0-9]+ passed"
