#!/usr/bin/env python3
"""Acceptance check for the Istio scenarios: field checks plus a server-side dry-run against the kind cluster."""
import os
import subprocess
import sys

import yaml

errors = []
HERE = os.path.dirname(os.path.abspath(__file__))
SCENARIO_SH = os.path.join(HERE, "03-scenario.sh")
D = os.path.join(HERE, "scenarios") + "/"


def load(name):
    try:
        return [d for d in yaml.safe_load_all(open(D + name)) if d]
    except Exception as e:
        errors.append(f"{name}: cannot read/parse: {e}")
        return []


def dig(d, *keys):
    for k in keys:
        if isinstance(k, int):
            d = d[k] if isinstance(d, list) and len(d) > k else None
        else:
            d = d.get(k) if isinstance(d, dict) else None
        if d is None:
            return None
    return d


def eq(label, got, want):
    if got != want:
        errors.append(f"{label}: expected {want!r}, got {got!r}")


def single(name, kind, api):
    docs = load(name)
    eq(f"{name} document count", len(docs), 1)
    d = docs[0] if docs else {}
    eq(f"{name} kind", d.get("kind"), kind)
    eq(f"{name} apiVersion", d.get("apiVersion"), api)
    eq(f"{name} namespace", dig(d, "metadata", "namespace"), "boutique")
    return d


d = single("fault.yaml", "VirtualService", "networking.istio.io/v1")
eq("fault name", dig(d, "metadata", "name"), "currency-fault")
eq("fault hosts", dig(d, "spec", "hosts"), ["currencyservice"])
eq("fault delay percent", dig(d, "spec", "http", 0, "fault", "delay", "percentage", "value"), 50)
eq("fault delay", dig(d, "spec", "http", 0, "fault", "delay", "fixedDelay"), "2s")
eq("fault route host", dig(d, "spec", "http", 0, "route", 0, "destination", "host"), "currencyservice")
eq("fault route port", dig(d, "spec", "http", 0, "route", 0, "destination", "port", "number"), 7000)

d = single("retry.yaml", "VirtualService", "networking.istio.io/v1")
eq("retry name", dig(d, "metadata", "name"), "productcatalog-retry")
eq("retry hosts", dig(d, "spec", "hosts"), ["productcatalogservice"])
eq("retry attempts", dig(d, "spec", "http", 0, "retries", "attempts"), 3)
eq("retry perTryTimeout", dig(d, "spec", "http", 0, "retries", "perTryTimeout"), "2s")
eq("retry retryOn", dig(d, "spec", "http", 0, "retries", "retryOn"), "5xx,reset,connect-failure,unavailable")
eq("retry timeout", dig(d, "spec", "http", 0, "timeout"), "6s")
eq("retry route host", dig(d, "spec", "http", 0, "route", 0, "destination", "host"), "productcatalogservice")
eq("retry route port", dig(d, "spec", "http", 0, "route", 0, "destination", "port", "number"), 3550)

d = single("authz-l4.yaml", "AuthorizationPolicy", "security.istio.io/v1")
eq("authz-l4 name", dig(d, "metadata", "name"), "redis-from-cart-only")
eq("authz-l4 selector", dig(d, "spec", "selector", "matchLabels"), {"app": "redis-cart"})
eq("authz-l4 action", dig(d, "spec", "action"), "ALLOW")
eq("authz-l4 principals", dig(d, "spec", "rules", 0, "from", 0, "source", "principals"),
   ["cluster.local/ns/boutique/sa/cartservice"])

d = single("authz-l7.yaml", "AuthorizationPolicy", "security.istio.io/v1")
eq("authz-l7 name", dig(d, "metadata", "name"), "emptycart-checkout-only")
eq("authz-l7 targetRefs", dig(d, "spec", "targetRefs"), [{"group": "", "kind": "Service", "name": "cartservice"}])
eq("authz-l7 action", dig(d, "spec", "action"), "DENY")
eq("authz-l7 notPrincipals", dig(d, "spec", "rules", 0, "from", 0, "source", "notPrincipals"),
   ["cluster.local/ns/boutique/sa/checkoutservice"])
eq("authz-l7 paths", dig(d, "spec", "rules", 0, "to", 0, "operation", "paths"), ["/hipstershop.CartService/EmptyCart"])

d = single("timeout.yaml", "HTTPRoute", "gateway.networking.k8s.io/v1")
eq("timeout name", dig(d, "metadata", "name"), "productcatalog-canary")   # same object as canary.yaml: applying it upgrades the canary
eq("timeout parent", dig(d, "spec", "parentRefs", 0, "name"), "productcatalogservice")
eq("timeout weights", [(b["name"], b["weight"]) for b in dig(d, "spec", "rules", 0, "backendRefs") or []],
   [("productcatalogservice-v1", 90), ("productcatalogservice-v2", 10)])
eq("timeout request timeout", dig(d, "spec", "rules", 0, "timeouts", "request"), "200ms")

docs = load("canary.yaml")
kinds = [(x.get("kind"), dig(x, "metadata", "name")) for x in docs]
eq("canary documents", kinds, [("Deployment", "productcatalogservice-v2"), ("Service", "productcatalogservice-v1"),
                               ("Service", "productcatalogservice-v2"), ("HTTPRoute", "productcatalog-canary")])
route = docs[-1] if docs else {}
eq("canary parent", dig(route, "spec", "parentRefs", 0, "name"), "productcatalogservice")
eq("canary weights", [(b["name"], b["weight"]) for b in dig(route, "spec", "rules", 0, "backendRefs") or []],
   [("productcatalogservice-v1", 90), ("productcatalogservice-v2", 10)])
eq("canary v2 labels", dig(docs[0], "spec", "template", "metadata", "labels"), {"app": "productcatalogservice", "version": "v2"}) if docs else None

d = single("strict-mtls.yaml", "PeerAuthentication", "security.istio.io/v1")
eq("strict-mtls name", dig(d, "metadata", "name"), "strict-mtls")
eq("strict-mtls mode", dig(d, "spec", "mtls", "mode"), "STRICT")

d = single("flaky.yaml", "Deployment", "apps/v1")
eq("flaky name", dig(d, "metadata", "name"), "productcatalogservice-flaky")
eq("flaky pod labels", dig(d, "spec", "template", "metadata", "labels"), {"app": "productcatalogservice", "version": "flaky"})
eq("flaky selector", dig(d, "spec", "selector", "matchLabels"), {"app": "productcatalogservice", "version": "flaky"})
eq("flaky has no ports", dig(d, "spec", "template", "spec", "containers", 0, "ports"), None)

sh = open(SCENARIO_SH).read()
if subprocess.run(["bash", "-n", SCENARIO_SH]).returncode:
    errors.append("03-scenario.sh has a syntax error")
for word in ["waypoint", "waypoint-svc", "fault", "retry", "canary", "timeout", "flaky", "outsider", "strict", "authz", "reset", "require_kind_context", "kubectl apply", "kubectl delete"]:
    if word not in sh:
        errors.append(f"03-scenario.sh does not mention {word!r}")
out = subprocess.run(["bash", SCENARIO_SH], capture_output=True, text=True)
if out.returncode == 0 or "waypoint" not in out.stdout + out.stderr:
    errors.append("running 03-scenario.sh with no argument must print usage naming the scenarios and exit non-zero")

for f in ["fault", "retry", "flaky", "authz-l4", "authz-l7", "canary", "timeout", "strict-mtls"]:
    r = subprocess.run(["kubectl", "apply", "--dry-run=server", "-f", D + f + ".yaml"], capture_output=True, text=True)
    if r.returncode:
        errors.append(f"{f}.yaml rejected by the cluster: {r.stderr.strip()[:200]}")

if errors:
    print("FAILED:\n  " + "\n  ".join(errors))
    sys.exit(1)
print("ok")
