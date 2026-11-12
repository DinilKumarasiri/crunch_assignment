"""Run: docker compose exec backend python scripts/try_register.py"""
import random
from datetime import date, timedelta

import apiclient
from apiclient import call, check, login

manager = login("acme_manager")
globex_manager = login("globex_manager")
eric = login("acme_emp1")
emma = login("acme_emp2")

base = random.randint(6000, 9000)
day = lambda n: (date.today() + timedelta(days=base + n)).isoformat()


def submit(token, n, start, minutes):
    status, body = call("POST", "/my/break-requests/", token,
                        body={"date": day(n), "start_time": start, "duration_minutes": minutes})
    assert status == 201, (status, body)
    return body["id"]


def queries():
    return f"[{apiclient.last_headers.get('X-Query-Count')} queries, " \
           f"{apiclient.last_headers.get('X-Response-Time-Ms')}ms]"


# Day 0: Eric 10:00-10:30, Emma 10:15-10:45  |  Day 1: Eric 09:00-09:20, Emma 14:00-14:40
approved = [submit(eric, 0, "10:00", 30), submit(emma, 0, "10:15", 30),
            submit(eric, 1, "09:00", 20), submit(emma, 1, "14:00", 40)]
call("POST", "/break-requests/bulk-review/", manager, body={"ids": approved, "action": "approve"})
pending = submit(emma, 2, "10:00", 15)  # stays PENDING: must NOT show up anywhere below

rng = f"date_from={day(0)}&date_to={day(2)}"

print("\n--- Register (keyset pagination) ---")
seen, path, pages = [], f"/register/?{rng}&page_size=3", 0
while path:
    status, page = call("GET", path, manager)
    pages += 1
    seen += page["results"]
    path = page["next"][len(apiclient.BASE):] if page["next"] else None
check(f"Walked {pages} pages via 'next' links {queries()}", pages == 2)
check(f"Register has exactly the 4 approved breaks", sorted(r["id"] for r in seen) == sorted(approved))
starts = [r["start_at"] for r in seen]
check("Newest first", starts == sorted(starts, reverse=True))
check("No 'count' field (keyset pagination skips COUNT)", "count" not in page)

print("\n--- Summary ---")
status, s = call("GET", f"/register/summary/?{rng}", manager)
check(f"Totals {s} {queries()}",
      s == {"total_breaks": 4, "total_minutes": 120, "total_hours": 2.0, "unique_employees": 2})
status, s = call("GET", f"/register/summary/?{rng}&search=emma", manager)
check(f"Totals respect search: {s}", s["total_breaks"] == 2 and s["total_minutes"] == 70)

print("\n--- On break at a moment ---")
for time_, expected in [("10:20", 2), ("10:30", 1), ("10:50", 0)]:
    status, body = call("GET", f"/register/on-break/?at={day(0)}T{time_}", manager)
    names = [b["employee_name"] for b in body["breaks"]]
    check(f"At {time_}: {body['count']} on break {names} {queries()}", body["count"] == expected)

print("\n--- Daily stats ---")
status, body = call("GET", f"/register/daily-stats/?{rng}", manager)
summary = [(d["date"], d["breaks"], d["total_minutes"], d["unique_employees"]) for d in body["days"]]
check(f"Daily rows {summary} {queries()}",
      summary == [(day(0), 2, 60, 2), (day(1), 2, 60, 2), (day(2), 0, 0, 0)])

status, body = call("GET", "/register/daily-stats/?date_from=2020-01-01&date_to=2026-01-01", manager)
check(f"Range over 366 days rejected (got {status}: {body})", status == 400)

print("\n--- Security ---")
status, _ = call("GET", "/register/", eric)
check(f"Employee cannot open the register (got {status})", status == 403)
status, s = call("GET", f"/register/summary/?{rng}", globex_manager)
check(f"Other org sees none of Acme's breaks: {s}", s["total_breaks"] == 0)