"""Run: docker compose exec backend python scripts/try_scale.py"""
from datetime import date, timedelta

import apiclient
from apiclient import call, login

manager = login("gen_o01_m1")
employee = login("gen_o01_e00001")
yesterday = (date.today() - timedelta(days=1)).isoformat()

endpoints = [
    (employee, "/my/break-requests/"),
    (manager, "/break-requests/?status=PENDING"),
    (manager, "/break-requests/?status=PENDING&page=40"),
    (manager, "/break-requests/?search=silva"),
    (manager, "/break-requests/?ordering=-duration_minutes"),
    (manager, "/register/"),
    (manager, "/register/summary/"),
    (manager, f"/register/on-break/?at={yesterday}T10:30"),
    (manager, "/register/daily-stats/"),
]

print(f"{'status':<7}{'time':>10}{'queries':>9}  endpoint")
for token, path in endpoints:
    status, body = call("GET", path, token)
    h = apiclient.last_headers
    print(f"{status:<7}{h['X-Response-Time-Ms']:>8}ms{h['X-Query-Count']:>9}  {path}")

    