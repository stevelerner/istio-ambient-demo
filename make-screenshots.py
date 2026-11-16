#!/usr/bin/env python3
"""Regenerate the README screenshots from a running kind cluster with TinyOlly (about 20 minutes).

Walks the demo (baseline, outsider, strict mTLS, waypoint, authz, fault), waits for TinyOlly to show each
state, and captures the service map (headless Chrome) and the MCP charts. Each shot is written twice to
docs/images: a preview (at most 900 px wide) and docs/images/full/<name>.png (what a click opens).
Ends with `reset`. Needs a TinyOlly checkout next to this repo (or TINYOLLY_DIR) and Chrome.

    ./make-screenshots.py            # all shots
    ./make-screenshots.py --check    # files exist and the README embeds them clickably (no cluster needed)
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

D = os.path.dirname(os.path.abspath(__file__))
TINYOLLY_DIR = os.environ.get("TINYOLLY_DIR", os.path.join(D, "..", "tinyolly"))
UI = os.environ.get("TINYOLLY_URL", "http://localhost:5005")
MCP_URL = os.environ.get("MCP_URL", "http://localhost:8765/mcp")
IMAGES = os.path.join(D, "docs", "images")
ENV = dict(os.environ, DOCKER_CONTEXT=os.environ.get("DOCKER_CONTEXT", "colima-tinyolly"))
SHOTS = ["step1-map", "step3-plaintext", "step3-denied", "step5-waypoint", "step7-authz", "step8-fault-diff"]
EMBED = re.compile(r"\[!\[[^\]]*\]\(docs/images/(?P<n>[\w-]+)\.png\)\]\((?P<full>[^)]*)\)")


def load_helpers():
    path = os.path.join(TINYOLLY_DIR, "scripts", "make-doc-images.py")
    sys.path.insert(0, os.path.join(TINYOLLY_DIR, "scripts"))
    spec = importlib.util.spec_from_file_location("mdi", path)
    mdi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mdi)
    mdi.IMAGES = type(mdi.IMAGES)(IMAGES)  # write into this repo
    mdi.FULL = mdi.IMAGES / "full"
    return mdi


def sh(cmd, timeout=600):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=D, env=ENV, timeout=timeout)
    return (p.stdout + p.stderr).strip()


def get(path):
    return json.load(urllib.request.urlopen(UI + path, timeout=30))


def wait(cond, secs=300, every=5):
    end = time.time() + secs
    while time.time() < end:
        try:
            if cond():
                return True
        except Exception:
            pass
        time.sleep(every)
    return False


def posture():
    return get("/api/mesh-posture")


def check():
    problems = []
    readme = open(os.path.join(D, "README.md")).read()
    for n in SHOTS:
        for p in (os.path.join(IMAGES, f"{n}.png"), os.path.join(IMAGES, "full", f"{n}.png")):
            if not os.path.exists(p):
                problems.append(f"missing {os.path.relpath(p, D)}")
        if f"docs/images/{n}.png" not in readme:
            problems.append(f"README does not embed {n}")
    for m in EMBED.finditer(readme):
        if not m.group("full").endswith(f"docs/images/full/{m.group('n')}.png"):
            problems.append(f"link for {m.group('n')} should open docs/images/full/{m.group('n')}.png")
    for m in re.finditer(r"(?<!\[)!\[[^\]]*\]\(docs/images/", readme):
        problems.append("bare (not clickable) image in README")
    return problems


def main():
    if "--check" in sys.argv:
        problems = check()
        print("\n".join(problems) or f"demo screenshots OK ({len(SHOTS)} shots)")
        return 1 if problems else 0
    mdi = load_helpers()
    from agent_eval.mcp_client import MCPClient
    client = MCPClient(MCP_URL)
    ok = []

    def ui(name):
        time.sleep(25)  # the service map is cached for about 20 s
        mdi.shoot_ui(name, "map", UI)
        ok.append(name)
        print("ok", name, flush=True)

    def chart(name, tool, args):
        mdi.shoot_mcp(name, (tool, args), client)
        ok.append(name)
        print("ok", name, flush=True)

    print(sh("./03-scenario.sh fresh", 900)[-200:], flush=True)
    wait(lambda: len(get("/api/service-map?limit=2000&merge=true")["edges"]) >= 18, 360)
    ui("step1-map")

    sh("./03-scenario.sh outsider")
    wait(lambda: any(e["source"] == "outsider" for e in posture()["plaintext"]), 240)
    ui("step3-plaintext")
    sh("./03-scenario.sh strict")
    wait(lambda: any(e["source"] == "outsider" and e["target"] == "frontend" for e in posture()["denied"]), 240)
    ui("step3-denied")

    print(sh("./03-scenario.sh fresh", 900)[-120:], flush=True)
    wait(lambda: len(get("/api/service-map?limit=2000&merge=true")["edges"]) >= 18, 360)
    sh("./03-scenario.sh waypoint", 900)
    wait(lambda: any(n.get("role") == "waypoint" for n in get("/api/service-map?limit=2000&merge=true")["nodes"]), 300)
    time.sleep(90)  # let request metrics accumulate on the L7 edges
    chart("step5-waypoint", "chart_service_map", {})

    sh("./03-scenario.sh authz")
    sh("./03-scenario.sh probe")
    wait(lambda: any(e["source"] == "intruder" and e["target"] == "cartservice" for e in posture()["denied"]), 300)
    ui("step7-authz")

    sh("./03-scenario.sh fault")
    time.sleep(120)
    chart("step8-fault-diff", "chart_map_diff", {"minutes": 15, "window_seconds": 90})
    sh("./03-scenario.sh reset", 600)
    print("captured:", ok, "missing:", [s for s in SHOTS if s not in ok], flush=True)
    return 0 if len(ok) == len(SHOTS) else 1


if __name__ == "__main__":
    sys.exit(main())
