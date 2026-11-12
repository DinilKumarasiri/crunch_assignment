import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000/api"

last_headers = {}

def call(method, path, token=None, body=None):
    global last_headers
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as res:
            status, raw, headers = res.status, res.read(), res.headers
    except urllib.error.HTTPError as err:
        status, raw, headers = err.code, err.read(), err.headers
    last_headers = dict(headers)

    try:
        return status, json.loads(raw or b"null")
    except json.JSONDecodeError:
        print(f"\n!! {method} {path} returned HTTP {status} with a non-JSON body:")
        print(raw[:800].decode(errors="replace"))
        raise SystemExit(1)


def login(username, password="password123"):
    status, body = call("POST", "/auth/login/", body={"username": username, "password": password})
    if status != 200:
        raise SystemExit(f"Login failed for {username}: {status} {body}")
    return body["access"]


def check(label, ok):
    print(f"{'PASS' if ok else 'FAIL'} | {label}")