# Task: mcp-trace-mesh

## Goal
Add an MCP tool `get_trace_mesh(trace_id)` that explains the service-mesh part of a trace: time spent in proxies (waypoint, gateway), retry attempts, and decoded Envoy response flags.

## Read
docker/apps/tinyolly-mcp/tests/test_server.py
docker/apps/tinyolly-mcp/server.py

## May change
docker/apps/tinyolly-mcp/server.py

## Constraints
- Do not edit tests. Add one `@mcp.tool()` function in the traces section, next to `get_trace`, reusing the existing `_fetch_trace(trace_id)`, `_attrs(span, full=True)`, `_ms(span)` and `_out` helpers. Look at how `get_trace` handles a missing trace and do the same.
- A proxy span is one whose attributes have `component == "proxy"`. Other spans are app spans.
- One hop per proxy span: `{"proxy": <serviceName>, "url": attrs.get("http.url"), "status": attrs.get("http.status_code"), "proxy_ms": _ms(span), "app_service": serviceName of the longest direct child app span (child = parentSpanId equals this span's spanId, and not a proxy span) or None, "app_ms": that child's _ms or None, "mesh_ms": max(0, proxy_ms - app_ms) when there is an app child, otherwise proxy_ms, "attempts": number of proxy spans in the trace with the same parentSpanId AND the same http.url (this one included), "flags": [{"code", "meaning"}] }`. Round the ms values with `round(x, 2)`.
- `flags` comes from `attrs.get("response_flags")`: a comma-separated string; ignore empty and `"-"`; each code maps to a meaning with this table, unknown codes use `"unknown flag"`: UH no healthy upstream, UF upstream connection failure, UC upstream connection termination, UT upstream request timeout, NR no route configured, URX retry limit exceeded, DC downstream connection termination, RL rate limited, UAEX unauthorized by external authorization, UR upstream remote reset, LR local reset, DI delay injected, FI fault injected, IH invalid header, SI stream idle timeout.
- Output: `{"trace_id", "proxy_spans": n, "total_mesh_ms": round(sum of mesh_ms, 2), "retries": [{"url", "attempts"}] for each distinct url whose hops have attempts > 1 (one entry per url), "hops": the hops sorted by mesh_ms descending, capped at 30}`. When there are no proxy spans return the same shape with empty lists, 0 values and `"note": "no proxy spans in this trace (no waypoint/gateway tracing enabled)"`.
- Docstring: one or two sentences saying when to use it ("why was this request slow in the mesh / were there retries").

## Shape
One loop over spans to build lookups (by spanId, children by parent), a second to build hops; a module-level dict for the flag table; no new modules or classes.

## Done when
cd docker/apps/tinyolly-mcp && .venv/bin/python -m pytest tests -q 2>&1 | tail -1 | grep -qE "^[0-9]+ passed"
