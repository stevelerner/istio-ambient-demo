#!/usr/bin/env python3
"""End-to-end check of the demo walkthrough (Steps 1-8) against a running kind cluster with TinyOlly.

Runs the scenario scripts, then asserts what TinyOlly shows through its API and MCP server. It takes
about 25 minutes and ends with `reset`. Env: TINYOLLY_URL (default http://localhost:5005),
MCP_URL (default http://localhost:8765/mcp), DOCKER_CONTEXT (default colima-tinyolly).
"""

import collections
import json
import os
import subprocess
import time
import urllib.request

D = os.path.dirname(os.path.abspath(__file__))
B = os.environ.get("TINYOLLY_URL", "http://localhost:5005")
MCP_URL = os.environ.get("MCP_URL", "http://localhost:8765/mcp")
env = dict(os.environ, DOCKER_CONTEXT=os.environ.get("DOCKER_CONTEXT", "colima-tinyolly"))
res = []

_H = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
_sid = None


def _post(body, sid=None):
    h = dict(_H)
    if sid:
        h["mcp-session-id"] = sid
    r = urllib.request.urlopen(urllib.request.Request(MCP_URL, json.dumps(body).encode(), h), timeout=60)
    data = [ln[5:].strip() for ln in r.read().decode().splitlines() if ln.startswith("data:")]
    return r.headers.get("mcp-session-id"), (json.loads(data[0]) if data else None)


def _session():
    global _sid
    if _sid is None:
        _sid, _ = _post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test-demo", "version": "1"},
                },
            }
        )
        _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, _sid)
    return _sid


def mcp(tool, args=None):
    _, r = _post(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool, "arguments": args or {}}},
        _session(),
    )
    texts = [c["text"] for c in (r.get("result") or {}).get("content", []) if c["type"] == "text"]
    if r.get("error"):
        texts.append(str(r["error"]))
    return "\n".join(texts)


def mcp_tools():
    _, r = _post({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, _session())
    return [t["name"] for t in r["result"]["tools"]]


def log(*a):
    print(*a, flush=True)


def sh(cmd, timeout=600):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=D, env=env, timeout=timeout)
    return (p.stdout + p.stderr).strip()


def get(u):
    return json.load(urllib.request.urlopen(B + u, timeout=30))


def wait(cond, secs=240, every=5):
    end = time.time() + secs
    while time.time() < end:
        try:
            if cond():
                return True
        except Exception:
            pass
        time.sleep(every)
    return False


def check(name, ok, detail=""):
    res.append((name, ok))
    log(("PASS " if ok else "FAIL ") + name + (" :: " + str(detail) if detail else ""))


def deltas(metric, win=45, **flt):
    end = time.time()
    q = "&".join(f"attribute.{k}={v}" for k, v in flt.items())
    d = get(f"/api/metrics/query?name={metric}&start={end - win}&end={end}" + ("&" + q if q else ""))
    return d["series"]


def req_by_dest(win=45):
    c = collections.Counter()
    for s in deltas("istio_requests_total", win):
        p = [x["value"] for x in s["datapoints"] if x.get("value") is not None]
        if len(p) > 1 and p[-1] > p[0]:
            c[s["attributes"].get("destination_canonical_service")] += p[-1] - p[0]
    return c


def avg_ms(svc, win=60):
    sm = ct = 0
    for s in deltas("istio_request_duration_milliseconds", win, destination_canonical_service=svc):
        dp = [x for x in s["datapoints"] if x.get("histogram")]
        if len(dp) > 1:
            sm += dp[-1]["histogram"]["sum"] - dp[0]["histogram"]["sum"]
            ct += dp[-1]["histogram"]["count"] - dp[0]["histogram"]["count"]
    return sm / ct if ct else None


def flags(svc, win=60):
    c = collections.Counter()
    for s in deltas("istio_requests_total", win, destination_canonical_service=svc):
        p = [x["value"] for x in s["datapoints"] if x.get("value") is not None]
        if len(p) > 1 and p[-1] > p[0]:
            c[s["attributes"].get("response_flags")] += p[-1] - p[0]
    return c


def posture():
    return get("/api/mesh-posture")



def filled(n=18):
    return len(get("/api/service-map?limit=2000&merge=true")["edges"]) >= n


log("== Steps 1-2")
tools = mcp_tools()
check(
    "0 MCP serves the mesh tools",
    all(t in tools for t in ("get_mesh_posture", "find_denied", "get_version_split", "what_changed", "suggest_authz", "chart_map_diff", "chart_trace_path")),
    len(tools),
)
check(
    "1 map fills from metrics only (no waypoint)",
    wait(lambda: filled(18), 360)
    and not any(n.get("role") == "waypoint" for n in get("/api/service-map?limit=2000&merge=true")["nodes"]),
)
p = posture()
check(
    "2 posture: mTLS>=75%, plaintext only to otlp-receiver",
    p["mtls_pct"] >= 75
    and all(e["target"] == "tinyolly-otlp-receiver" for e in p["plaintext"])
    and len(p["plaintext"]) >= 2,
    (p["mtls_pct"], [(e["source"], e["target"]) for e in p["plaintext"]]),
)
# --- Step 3: enforce mTLS
log("== Step 3")
sh("./03-scenario.sh outsider")
check(
    "3a outsider plaintext edge appears", wait(lambda: any(e["source"] == "outsider" for e in posture()["plaintext"]))
)
time.sleep(10)
out = sh("kubectl --context kind-tinyolly -n outside logs outsider --tail=4")
check("3b outsider gets 200 over plaintext", "200" in out.split(), out.replace("\n", " "))
sh("./03-scenario.sh strict")
check(
    "3c denied edge outsider->frontend",
    wait(lambda: any(e["source"] == "outsider" and e["target"] == "frontend" for e in posture()["denied"])),
)
out = sh("kubectl --context kind-tinyolly -n outside logs outsider --tail=3")
check("3d outsider refused (000)", "000" in out.split(), out.replace("\n", " "))
check("3e find_denied via MCP lists outsider", "outsider" in mcp("find_denied"))
# --- fresh
log("== fresh")
sh("./03-scenario.sh fresh", timeout=400)
check("fresh: map refills", wait(lambda: filled(18), 300))
p = posture()
check(
    "fresh: no denied, no outsider",
    not p["denied"] and not any(e["source"] == "outsider" for e in p["plaintext"]),
    (p["denied"], p["mtls_pct"]),
)
# --- Step 4
log("== Step 4")
sh("./03-scenario.sh waypoint-svc currencyservice", timeout=400)
check(
    "4a waypoint node appears",
    wait(lambda: any(n.get("role") == "waypoint" for n in get("/api/service-map?limit=2000&merge=true")["nodes"]), 240),
)
time.sleep(20)
r = req_by_dest(45)
check("4b L7 metrics only for currencyservice", set(k for k, v in r.items() if v > 0) == {"currencyservice"}, dict(r))
# --- Step 5
log("== Step 5")
sh("./03-scenario.sh waypoint", timeout=400)
check(
    "5a L7 metrics for >=8 services",
    wait(lambda: len([k for k, v in req_by_dest(45).items() if v > 0]) >= 8, 300),
    dict(req_by_dest(45)),
)
check("5b waypoint reports spans", "waypoint" in mcp("list_services"))
# --- Step 6
log("== Step 6")
sh("./03-scenario.sh canary", timeout=400)


def vs():
    d = json.loads(mcp("get_version_split", {"service": "productcatalogservice", "minutes": 1.5}))
    return {v["version"]: v for v in d["versions"]}


check(
    "6a canary split ~90/10",
    wait(lambda: "v2" in vs() and 4 <= vs()["v2"]["share_pct"] <= 18, 240),
    {k: (v["share_pct"], v.get("avg_ms")) for k, v in vs().items()},
)
v = vs()
check(
    "6b v2 avg latency >300ms, v1 <50ms",
    v["v2"]["avg_ms"] > 300 and v["v1"]["avg_ms"] < 50,
    {k: v2.get("avg_ms") for k, v2 in v.items()},
)
# --- Step 7
log("== Step 7")
sh("./03-scenario.sh authz")
sh("./03-scenario.sh probe")
check(
    "7a denied intruder->cartservice",
    wait(lambda: any(e["source"] == "intruder" and e["target"] == "cartservice" for e in posture()["denied"]), 300),
    posture()["denied"],
)
check("7b cart still works", sh("curl -s -m 15 -o /dev/null -w '%{http_code}' http://localhost:5001/cart") == "200")
check("7c suggest_authz drafts a policy for cartservice", "sa/frontend" in mcp("suggest_authz", {"service": "cartservice", "minutes": 60}))
# --- Step 8
log("== Step 8")
b = avg_ms("currencyservice")
sh("./03-scenario.sh fault")
check(
    "8a fault: currencyservice latency up",
    wait(lambda: (avg_ms("currencyservice") or 0) > 500, 180),
    (b, avg_ms("currencyservice")),
)
check("8b fault: DI flag present", "DI" in flags("currencyservice"), dict(flags("currencyservice")))
sh("./03-scenario.sh timeout")
check(
    "8c timeout: UT flag on productcatalog",
    wait(lambda: flags("productcatalogservice").get("UT", 0) > 0, 180),
    dict(flags("productcatalogservice")),
)
check(
    "8d timeout: errors on map",
    wait(  # the service map is cached for about 20 s
        lambda: any(
            e.get("error_count", 0) > 0
            for e in get("/api/service-map?limit=2000&merge=true")["edges"]
            if e["target"] == "productcatalogservice"
        ),
        60,
    ),
)
sh("./03-scenario.sh flaky")
check("8e flaky: UC failures on productcatalog", wait(lambda: flags("productcatalogservice", 45).get("UC", 0) > 5, 180), dict(flags("productcatalogservice", 45)))
check("8e2 get_edge decodes the UC flag", "UC" in mcp("get_edge", {"source": "frontend", "target": "productcatalogservice", "minutes": 1.5}))
check("8e3 what_changed names productcatalogservice", "productcatalogservice" in mcp("what_changed", {"minutes": 20, "window_seconds": 60}))
sh("./03-scenario.sh retry")
check("8f retry removes the failures", wait(lambda: flags("productcatalogservice", 40).get("UC", 0) == 0 and sum(flags("productcatalogservice", 40).values()) > 20, 240), dict(flags("productcatalogservice", 40)))
t = sh("curl -s -m 60 -o /dev/null -w '%{http_code}' http://localhost:5001/")
check("8g shop up", t == "200", t)
# --- reset
log("== reset")
sh("./03-scenario.sh reset", timeout=300)
left = sh(
    "kubectl --context kind-tinyolly -n boutique get virtualservice,httproute,authorizationpolicy,peerauthentication,gateway.gateway.networking.k8s.io -o name"
)
check(
    "reset removes scenarios",
    all(
        x not in left
        for x in (
            "virtualservice",
            "authorizationpolicy",
            "peerauthentication",
            "gateway.gateway.networking.k8s.io/waypoint",
            "productcatalog-canary",
        )
    ),
    left.replace("\n", " "),
)
log("SUMMARY", sum(1 for _, ok in res if ok), "/", len(res), "passed")
log("FAILED:", [n for n, ok in res if not ok])
sys.exit(1 if any(not ok for _, ok in res) else 0)
