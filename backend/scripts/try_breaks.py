"""Run: docker compose exec backend python scripts/try_breaks.py"""
import random
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from apiclient import call, check, login

manager = login("acme_manager")
emp = login("acme_emp2")
other_emp = login("acme_emp1")

# --- Put the policy into a known state for the test ---------------------------
_, current = call("GET", "/policy/", manager)
status, _ = call("PUT", "/policy/", manager, body={
    "min_duration_minutes": 5, "max_duration_minutes": 60, "max_daily_minutes": 90,
    "max_requests_per_day": 3, "min_advance_notice_minutes": 30,
    "max_concurrent_breaks": 5, "requires_approval": True,
    "version": current["version"],
})
check(f"Test policy applied (got {status})", status == 200)

# Random far-future days so the script can be re-run without old data getting in the way.
base = random.randint(30, 3000)
d1, d2, d3, d4, d5 = [(date.today() + timedelta(days=base + i)).isoformat() for i in range(5)]


def submit(token, day, start, minutes, key=None):
    body = {"date": day, "start_time": start, "duration_minutes": minutes}
    if key:
        body["client_request_id"] = str(key)
    return call("POST", "/my/break-requests/", token, body=body)


def parallel(n, fn):
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(fn, range(n)))


print("\n--- Basic rules ---")
status, first = submit(emp, d1, "10:00", 15)
check(f"Valid request created (got {status}, status={first.get('status')}, "
      f"end_at={first.get('end_at')})", status == 201 and first["status"] == "PENDING")

status, body = submit(emp, d1, "10:10", 15)
check(f"Overlapping request rejected (got {status}: {body.get('detail')})", status == 409)

status, _ = submit(emp, d1, "10:15", 15)
check(f"Back-to-back request allowed (got {status})", status == 201)

status, body = submit(emp, d1, "11:00", 3)
check(f"Too short rejected (got {status}: {body})", status == 400 and "duration_minutes" in body)

status, body = submit(emp, d1, "11:00", 61)
check(f"Too long rejected (got {status}: {body})", status == 400 and "duration_minutes" in body)

soon = datetime.now(ZoneInfo("Asia/Colombo")) + timedelta(minutes=10)
status, body = submit(emp, soon.date().isoformat(), soon.strftime("%H:%M"), 10)
check(f"Too little notice rejected (got {status}: {body})", status == 400 and "start_time" in body)

status, _ = submit(emp, d1, "13:00", 60)          # 3rd request of the day, 90/90 minutes
check(f"3rd request (exactly at daily limit) allowed (got {status})", status == 201)
status, body = submit(emp, d1, "15:00", 5)        # 4th request
check(f"4th request of the day rejected (got {status}: {body})", status == 400)

status, _ = submit(emp, d2, "09:00", 60)
status, body = submit(emp, d2, "14:00", 45)       # 60 + 45 > 90
check(f"Daily minutes allowance enforced (got {status}: {body})", status == 400)

print("\n--- Idempotency ---")
key = uuid.uuid4()
s1, b1 = submit(emp, d2, "16:00", 10, key)
s2, b2 = submit(emp, d2, "16:00", 10, key)
check(f"Same key twice: {s1} then {s2}, same id={b1.get('id') == b2.get('id')}",
      s1 == 201 and s2 == 200 and b1["id"] == b2["id"])

print("\n--- Roles & isolation ---")
status, _ = submit(manager, d1, "18:00", 10)
check(f"Manager cannot use the employee endpoint (got {status})", status == 403)

status, page = call("GET", "/my/break-requests/", other_emp)
other_ids = {r["id"] for r in page["results"]}
check(f"Another employee does not see these requests", first["id"] not in other_ids)

status, page = call("GET", "/my/break-requests/?status=PENDING", emp)
check(f"History with status filter works (got {status}, count={page['count']})",
      status == 200 and all(r["status"] == "PENDING" for r in page["results"]))

print("\n--- Concurrency (real parallel requests) ---")
results = parallel(10, lambda i: submit(emp, d4, "10:00", 15, uuid.uuid4()))
codes = sorted(s for s, _ in results)
check(f"10 parallel requests for the SAME slot -> exactly one created: {codes}",
      codes.count(201) == 1 and codes.count(409) == 9)

dup_key = uuid.uuid4()
results = parallel(5, lambda i: submit(emp, d5, "10:00", 15, dup_key))
codes = sorted(s for s, _ in results)
ids = {b["id"] for _, b in results}
check(f"5 parallel double-clicks (same key) -> one request, rest replayed: {codes}",
      codes.count(201) == 1 and codes.count(200) == 4 and len(ids) == 1)

slots = ["09:00", "10:00", "11:00", "12:00", "13:00"]
results = parallel(5, lambda i: submit(emp, d3, slots[i], 10, uuid.uuid4()))
codes = sorted(s for s, _ in results)
check(f"5 parallel requests, limit 3/day -> exactly 3 created: {codes}",
      codes.count(201) == 3 and codes.count(400) == 2)