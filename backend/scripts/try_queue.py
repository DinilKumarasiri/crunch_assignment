"""Run: docker compose exec backend python scripts/try_queue.py"""
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import apiclient
from apiclient import call, check, login

manager = login("acme_manager")
globex_manager = login("globex_manager")
eric = login("acme_emp1")    # Eric Employee
emma = login("acme_emp2")    # Emma Employee

base = random.randint(3000, 6000)
day = lambda n: (date.today() + timedelta(days=base + n)).isoformat()


def submit(token, n, start="10:00", minutes=15):
    status, body = call("POST", "/my/break-requests/", token,
                        body={"date": day(n), "start_time": start, "duration_minutes": minutes})
    assert status == 201, (status, body)
    return body["id"]


# Fresh PENDING requests, one per day so daily limits never interfere.
eric_ids = [submit(eric, n, minutes=10 + n) for n in range(4)]
emma_ids = [submit(emma, n, minutes=20 + n) for n in range(4)]

print("\n--- Listing, filtering, search, sorting ---")
status, page = call("GET", "/break-requests/?status=PENDING", manager)
check(f"Queue lists pending requests (got {status}, count={page['count']}, "
      f"queries={apiclient.last_headers.get('X-Query-Count')}, "
      f"time={apiclient.last_headers.get('X-Response-Time-Ms')}ms)",
      status == 200 and all(r["status"] == "PENDING" for r in page["results"]))

status, page = call("GET", "/break-requests/?search=emma", manager)
names = {r["employee_name"] for r in page["results"]}
check(f"Search 'emma' returns only Emma: {names}", names == {"Emma Employee"})

status, page = call("GET", f"/break-requests/?date_from={day(1)}&date_to={day(2)}", manager)
dates = {r["break_date"] for r in page["results"]}
check(f"Date range filter: {sorted(dates)}", dates and dates <= {day(1), day(2)})

status, page = call("GET", f"/break-requests/?date_from={day(0)}&date_to={day(3)}"
                           f"&ordering=-duration_minutes", manager)
durations = [r["duration_minutes"] for r in page["results"]]
check(f"Sort by duration desc: {durations}", durations == sorted(durations, reverse=True))

print("\n--- No N+1: query count is the same for 2 rows and 8 rows ---")
call("GET", f"/break-requests/?date_from={day(0)}&date_to={day(3)}&page_size=2", manager)
small = apiclient.last_headers.get("X-Query-Count")
call("GET", f"/break-requests/?date_from={day(0)}&date_to={day(3)}&page_size=8", manager)
large = apiclient.last_headers.get("X-Query-Count")
check(f"Queries for page_size=2: {small}, for page_size=8: {large}", small == large)

print("\n--- Permissions & tenant isolation ---")
status, _ = call("GET", "/break-requests/", eric)
check(f"Employee cannot see the queue (got {status})", status == 403)

status, _ = call("POST", f"/break-requests/{eric_ids[0]}/approve/", globex_manager, body={})
check(f"Other org's manager gets 404 (got {status})", status == 404)

print("\n--- Approve / reject ---")
status, item = call("POST", f"/break-requests/{eric_ids[0]}/approve/", manager, body={})
check(f"Approve (got {status}, status={item.get('status')})", status == 200 and item["status"] == "APPROVED")

status, body = call("POST", f"/break-requests/{eric_ids[0]}/approve/", manager, body={})
check(f"Approving twice -> 409 (got {status}: {body.get('detail')})", status == 409)

status, item = call("POST", f"/break-requests/{eric_ids[1]}/reject/", manager,
                    body={"note": "Team meeting at that time"})
check(f"Reject with note (got {status}, note={item.get('review_note')!r})",
      status == 200 and item["status"] == "REJECTED")

print("\n--- Bulk ---")
batch = [eric_ids[2], emma_ids[0], emma_ids[1], eric_ids[0], 999999999]
status, result = call("POST", "/break-requests/bulk-review/", manager,
                      body={"ids": batch, "action": "approve"})
print("         ", result)
check(f"Bulk approve: 3 processed, 2 skipped (got {status})",
      status == 200 and len(result["processed"]) == 3 and len(result["skipped"]) == 2)
check(f"Bulk took {apiclient.last_headers.get('X-Query-Count')} queries", True)

print("\n--- Concurrency: 5 managers approve the same request at once ---")
target = emma_ids[2]
with ThreadPoolExecutor(max_workers=5) as pool:
    codes = sorted(pool.map(
        lambda _: call("POST", f"/break-requests/{target}/approve/", manager, body={})[0],
        range(5)))
check(f"Exactly one approval wins: {codes}", codes.count(200) == 1 and codes.count(409) == 4)
