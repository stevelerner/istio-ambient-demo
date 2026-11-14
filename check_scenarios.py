#!/usr/bin/env python3
"""Acceptance check for the Istio scenarios: field checks plus a server-side dry-run against the kind cluster."""
import subprocess, sys
import yaml

errors = []
import os
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenarios") + "/"


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

sh = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "03-scenario.sh")).read()
if subprocess.run(["bash", "-n", os.path.join(os.path.dirname(os.path.abspath(__file__)), "03-scenario.sh")]).returncode:
    errors.append("03-scenario.sh has a syntax error")
for word in ["waypoint", "fault", "retry", "authz", "reset", "require_kind_context", "kubectl apply", "kubectl delete"]:
    if word not in sh:
        errors.append(f"03-scenario.sh does not mention {word!r}")
out = subprocess.run(["bash", os.path.join(os.path.dirname(os.path.abspath(__file__)), "03-scenario.sh")], capture_output=True, text=True)
if out.returncode == 0 or "waypoint" not in out.stdout + out.stderr:
    errors.append("running 03-scenario.sh with no argument must print usage naming the scenarios and exit non-zero")

for f in ["fault", "retry", "authz-l4", "authz-l7"]:
    r = subprocess.run(["kubectl", "apply", "--dry-run=server", "-f", D + f + ".yaml"], capture_output=True, text=True)
    if r.returncode:
        errors.append(f"{f}.yaml rejected by the cluster: {r.stderr.strip()[:200]}")

if errors:
    print("FAILED:\n  " + "\n  ".join(errors))
    sys.exit(1)
print("ok")
