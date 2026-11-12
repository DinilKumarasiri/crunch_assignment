"""Run: docker compose exec backend python scripts/try_policy.py"""
from apiclient import call, check, login

EDITABLE = [
    "min_duration_minutes", "max_duration_minutes", "max_daily_minutes",
    "max_requests_per_day", "min_advance_notice_minutes",
    "max_concurrent_breaks", "requires_approval",
]

manager = login("acme_manager")
employee = login("acme_emp1")
other_manager = login("globex_manager")

# 1. Employee can READ the policy
status, policy = call("GET", "/policy/", employee)
check(f"Employee can read policy (got {status})", status == 200)

# 2. Employee cannot CHANGE it
status, _ = call("PUT", "/policy/", employee, body=policy)
check(f"Employee cannot update policy (got {status})", status == 403)

# 3. Manager updates with the correct version → saved, version goes up
status, current = call("GET", "/policy/", manager)
payload = {k: current[k] for k in EDITABLE}
payload["max_concurrent_breaks"] = 3
payload["version"] = current["version"]
status, saved = call("PUT", "/policy/", manager, body=payload)
check(f"Manager update saved (got {status}, version {current['version']} -> {saved.get('version')})",
      status == 200 and saved["version"] == current["version"] + 1)

# 4. Same payload again = stale version (the lost-update scenario) → 409
status, body = call("PUT", "/policy/", manager, body=payload)
check(f"Stale version rejected (got {status}: {body.get('detail')})", status == 409)

# 5. Cross-field validation: min > max → 400 with a field error
bad = {**payload, "version": saved["version"], "min_duration_minutes": 90, "max_duration_minutes": 30}
status, body = call("PUT", "/policy/", manager, body=bad)
check(f"min > max rejected (got {status}: {body})", status == 400 and "min_duration_minutes" in body)

# 6. Field validation: out-of-range value → 400
bad = {**payload, "version": saved["version"], "max_requests_per_day": 0}
status, body = call("PUT", "/policy/", manager, body=bad)
check(f"Out-of-range value rejected (got {status}: {body})", status == 400)

# 7. Missing field → 400
bad = {k: v for k, v in payload.items() if k != "max_daily_minutes"}
bad["version"] = saved["version"]
status, body = call("PUT", "/policy/", manager, body=bad)
check(f"Missing field rejected (got {status}: {body})", status == 400)

# 8. Tenant isolation: Globex's policy was NOT changed by Acme's manager
status, globex = call("GET", "/policy/", other_manager)
check(f"Globex policy untouched (max_concurrent={globex['max_concurrent_breaks']}, "
      f"version={globex['version']})", globex["max_concurrent_breaks"] == 5)

      