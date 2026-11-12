"""Manual smoke test for auth, roles and tenant isolation.
Run: docker compose exec backend python scripts/try_auth.py
"""
import json
import urllib.error
import urllib.request

BASE = "http://localhost:8000/api"


def call(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as res:
            status, raw = res.status, res.read()
    except urllib.error.HTTPError as err:
        status, raw = err.code, err.read()

    try:
        return status, json.loads(raw or b"null")
    except json.JSONDecodeError:
        print(f"\n!! {method} {path} returned HTTP {status} with a non-JSON body:")
        print(raw[:800].decode(errors="replace"))
        raise SystemExit(1)


def login(username, password="password123"):
    return call("POST", "/auth/login/", body={"username": username, "password": password})


def check(label, ok):
    print(f"{'PASS' if ok else 'FAIL'} | {label}")


# 1. No token → 401
status, _ = call("GET", "/auth/me/")
check(f"No token is rejected (got {status})", status == 401)

# 2. Wrong password → 401
status, _ = login("acme_manager", "wrong")
check(f"Wrong password is rejected (got {status})", status == 401)

# 3. Manager logs in and sees own profile
status, body = login("acme_manager")
manager_token = body["access"]
check(f"Manager can log in (got {status}, role={body['user']['role']})", status == 200)

status, me = call("GET", "/auth/me/", manager_token)
check(f"/me returns own org (org={me['organisation_name']})", me["organisation_name"] == "Acme Ltd")

# 4. Tenant isolation: Acme manager sees ONLY Acme users
status, page = call("GET", "/users/", manager_token)
usernames = [u["username"] for u in page["results"]]
check(f"Manager sees only own org users: {usernames}",
      all(name.startswith("acme_") for name in usernames))

# 5. Role check: employee cannot use the manager endpoint → 403
_, body = login("acme_emp1")
employee_token = body["access"]
status, body = call("GET", "/users/", employee_token)
check(f"Employee blocked from manager endpoint (got {status}: {body.get('detail')})", status == 403)

# 6. Tampered token → 401
tampered = manager_token[:-2] + ("aa" if not manager_token.endswith("aa") else "bb")
status, _ = call("GET", "/auth/me/", tampered)
check(f"Tampered token is rejected (got {status})", status == 401)

