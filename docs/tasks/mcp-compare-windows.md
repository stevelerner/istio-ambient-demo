# Task: mcp-compare-windows

## Goal
Add an MCP tool `compare_windows` that shows what changed per service between the last N minutes and the N minutes before, based on recent traces.

## Read
docker/apps/tinyolly-mcp/tests/test_server.py
docker/apps/tinyolly-mcp/server.py

## May change
docker/apps/tinyolly-mcp/server.py

## Constraints
- Do not edit tests. Add one `@mcp.tool()` function `compare_windows(minutes: float = 5, service: str | None = None) -> str` in the traces section of `server.py`, using the existing `_api` and `_out` helpers like `search_traces` does.
- Fetch `_api("/api/traces", limit=5000)`. Trace `start_time` is in nanoseconds. With `now_ns = int(time.time() * 1e9)` and `w = minutes * 60e9`: the current window is `now_ns - w < start <= now_ns`, the previous window is `now_ns - 2*w < start <= now_ns - w`. Ignore traces outside both. If `service` is given keep only that `service_name`.
- Per `service_name` and window: `traces` (count), `errors` (count of rows with truthy `has_error`), `p95` of `duration_ms` using nearest rank `sorted_values[min(n - 1, int(n * 0.95))]` (0 when no traces).
- One output row per service with traces in either window: `{"service", "traces_now", "traces_prev", "errors_now", "errors_prev", "p95_now", "p95_prev", "change"}`. `change` is the first that applies: `"new"` (prev traces 0), `"gone"` (now traces 0), `"errors_up"` (errors_now > errors_prev), `"slower"` (p95_prev > 0 and p95_now >= 1.5 * p95_prev), `"errors_down"` (errors_now < errors_prev), else `"steady"`.
- Sort rows: changed services first (in the order new, gone, errors_up, slower, errors_down), `steady` last, ties by `traces_now` descending.
- Return `_out({"window_minutes": minutes, "services": rows})`. Docstring: one or two sentences saying when to use it ("what changed in the last few minutes").

## Shape
Group with plain dicts keyed by service; small local helper for p95; no new modules or classes.

## Done when
cd docker/apps/tinyolly-mcp && .venv/bin/python -m pytest tests -q 2>&1 | tail -1 | grep -qE "^[0-9]+ passed"
