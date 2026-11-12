"""Run: docker compose exec backend python scripts/try_capacity.py"""
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from apiclient import call, check, login

manager = login("acme_manager")
emps = [login(f"acme_emp{i}") for i in range(1, 7)]

base = random.randint(9000, 12000)
day = lambda n: (date.today() + timedelta(days=base + n)).isoformat()


def set_policy(capacity, requires_approval):
    _, current = call("GET", "/policy/", manager)
    status, _ = call("PUT", "/policy/", manager, body={
        "min_duration_minutes": 5, "max_duration_minutes": 60, "max_daily_minutes": 90,
        "max_requests_per_day": 3, "min_advance_notice_minutes": 30,
        "max_concurrent_breaks": capacity, "requires_approval": requires_approval,
        "version": current["version"],
    })
    assert status == 200


def submit(token, n, start, minutes):
    return call("POST", "/my/break-requests/", token,
                body={"date": day(n), "start_time": start, "duration_minutes": minutes})


def submit_id(token, n, start, minutes):
    status, body = submit(token, n, start, minutes)
    assert status == 201, (status, body)
    return body["id"]


def on_break(n, time_):
    return call("GET", f"/register/on-break/?at={day(n)}T{time_}", manager)[1]["count"]


def parallel(fns):
    with ThreadPoolExecutor(max_workers=len(fns)) as pool:
        return list(pool.map(lambda f: f(), fns))


set_policy(capacity=2, requires_approval=True)

print("\n--- Bulk approve respects capacity ---")
ids = [submit_id(e, 0, "10:00", 30) for e in emps]      # 6 employees, same slot
status, result = call("POST", "/break-requests/bulk-review/", manager,
                      body={"ids": ids, "action": "approve"})
reasons = {s["reason"] for s in result["skipped"]}
check(f"6 requested, capacity 2 -> processed {len(result['processed'])}, "
      f"skipped {len(result['skipped'])} {reasons}",
      len(result["processed"]) == 2 and reasons == {"capacity_reached"})
check(f"On break at 10:15 = {on_break(0, '10:15')}", on_break(0, "10:15") == 2)

later = submit_id(emps[2], 0, "10:30", 15)              # starts exactly when the others end
status, _ = call("POST", f"/break-requests/{later}/approve/", manager, body={})
check(f"Back-to-back slot 10:30 approved (half-open ranges) (got {status})", status == 200)

print("\n--- Peak overlap, not total overlap ---")
x = submit_id(emps[0], 1, "09:00", 10)                  # 09:00-09:10
y = submit_id(emps[1], 1, "09:20", 10)                  # 09:20-09:30
call("POST", "/break-requests/bulk-review/", manager, body={"ids": [x, y], "action": "approve"})
z = submit_id(emps[2], 1, "09:00", 30)                  # 09:00-09:30 overlaps both, peak only 1
status, _ = call("POST", f"/break-requests/{z}/approve/", manager, body={})
check(f"Z overlaps 2 breaks but peak is 1 -> approved (got {status})", status == 200)
w = submit_id(emps[3], 1, "09:05", 10)                  # 09:05-09:15 -> X and Z already there
status, body = call("POST", f"/break-requests/{w}/approve/", manager, body={})
check(f"W would make 3 at 09:05 -> rejected (got {status}: {body.get('detail')})", status == 409)

print("\n--- Race: 6 managers approve 6 different requests at once ---")
ids = [submit_id(e, 2, "11:00", 15) for e in emps]
codes = sorted(parallel([
    (lambda pk=pk: call("POST", f"/break-requests/{pk}/approve/", manager, body={})[0])
    for pk in ids
]))
check(f"Exactly 2 approvals win: {codes}", codes.count(200) == 2 and codes.count(409) == 4)
check(f"On break at 11:05 = {on_break(2, '11:05')}", on_break(2, "11:05") == 2)

print("\n--- Race: auto-approval, 6 employees submit the same slot at once ---")
set_policy(capacity=2, requires_approval=False)
results = parallel([(lambda e=e: submit(e, 3, "12:00", 15)) for e in emps])
codes = sorted(s for s, _ in results)
approved = [b for s, b in results if s == 201 and b["status"] == "APPROVED"]
check(f"Exactly 2 auto-approved: {codes}", len(approved) == 2 and codes.count(409) == 4)
check(f"On break at 12:05 = {on_break(3, '12:05')}", on_break(3, "12:05") == 2)

set_policy(capacity=5, requires_approval=True)  # restore a normal policy