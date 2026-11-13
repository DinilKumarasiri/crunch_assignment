"""
Load test for the Break Management API (run via benchmarks/run.sh).

Normal mix:  EmployeeUser + ManagerUser across 50 generated organisations.
Contention:  HotSlotEmployee + HotSlotManager, all in ONE organisation, same slots.
"""
import csv
import random
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import requests
from locust import HttpUser, between, events, task

ORGS = 50
EMPLOYEES_PER_ORG = 2000
MANAGERS_PER_ORG = 2
PASSWORD = "password123"
LAST_NAMES = ["Perera", "Silva", "Smith", "Patel", "Wang", "Garcia"]

HOT_DAY = (date.today() + timedelta(days=7)).isoformat()
HOT_SLOTS = ["10:00", "10:15", "10:30"]  # 30-minute breaks: heavily overlapping

TOKENS = {}
QUERY_COUNTS = defaultdict(list)


# --------------------------------------------------------------------------- setup
def _login(host, username):
    response = requests.post(f"{host}/api/auth/login/",
                             json={"username": username, "password": PASSWORD}, timeout=120)
    response.raise_for_status()
    return response.json()["access"]


@events.init.add_listener
def log_in_user_pool(environment, **kwargs):
    """Log in BEFORE the test clock starts, so slow password hashing isn't measured."""
    host = environment.host
    rng = random.Random(1)
    pools = {
        "employee": [f"gen_o{rng.randint(1, ORGS):02d}_e{rng.randint(1, EMPLOYEES_PER_ORG):05d}"
                     for _ in range(50)],
        "manager": [f"gen_o{org:02d}_m{rng.randint(1, MANAGERS_PER_ORG)}"
                    for org in rng.sample(range(1, ORGS + 1), 10)],
        "hot_employee": [f"gen_o01_e{e:05d}"
                         for e in rng.sample(range(1, EMPLOYEES_PER_ORG + 1), 40)],
        "hot_manager": ["gen_o01_m1", "gen_o01_m2"],
    }
    print("Logging in the user pool (not part of the measurements) ...")
    with ThreadPoolExecutor(max_workers=8) as pool:
        for kind, usernames in pools.items():
            TOKENS[kind] = list(pool.map(lambda u: _login(host, u), usernames))
    print({kind: len(tokens) for kind, tokens in TOKENS.items()})


# --------------------------------------------------------------------------- query counts
@events.request.add_listener
def record_query_count(request_type, name, response=None, **kwargs):
    if response is not None and "X-Query-Count" in response.headers:
        QUERY_COUNTS[f"{request_type} {name}"].append(int(response.headers["X-Query-Count"]))


@events.test_stop.add_listener
def write_query_counts(environment, **kwargs):
    prefix = getattr(environment.parsed_options, "csv_prefix", None)
    if not prefix:
        return
    with open(f"{prefix}_queries.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Samples", "Avg Queries", "Max Queries"])
        for name, values in sorted(QUERY_COUNTS.items()):
            writer.writerow([name, len(values), f"{sum(values) / len(values):.1f}", max(values)])


# --------------------------------------------------------------------------- users
class ApiUser(HttpUser):
    abstract = True                   # not a user type itself, just shared code
    wait_time = between(0.1, 0.5)     # short "think time" between actions
    token_pool = None

    def on_start(self):
        token = random.choice(TOKENS[self.token_pool])
        self.client.headers["Authorization"] = f"Bearer {token}"

    def expect(self, method, url, name, ok_statuses, **kwargs):
        """Request where some 4xx answers are correct business outcomes, not failures."""
        with self.client.request(method, url, name=name, catch_response=True, **kwargs) as r:
            if r.status_code in ok_statuses:
                r.success()
            else:
                r.failure(f"HTTP {r.status_code}: {r.text[:200]}")
            return r


class EmployeeUser(ApiUser):
    weight = 4
    token_pool = "employee"

    @task(5)
    def my_history(self):
        self.client.get("/api/my/break-requests/")

    @task(2)
    def read_policy(self):
        self.client.get("/api/policy/")

    @task(1)
    def submit_break(self):
        minute = random.choice(range(0, 600, 15))
        body = {
            "date": (date.today() + timedelta(days=random.randint(2, 29))).isoformat(),
            "start_time": f"{8 + minute // 60:02d}:{minute % 60:02d}",
            "duration_minutes": random.choice([10, 15, 20, 30]),
            "client_request_id": str(uuid.uuid4()),
        }
        self.expect("POST", "/api/my/break-requests/", "/api/my/break-requests/",
                    {200, 201, 400, 409}, json=body)


class ManagerUser(ApiUser):
    weight = 1
    token_pool = "manager"

    @task(5)
    def queue_first_page(self):
        self.client.get("/api/break-requests/?status=PENDING",
                        name="/api/break-requests/?status=PENDING")

    @task(2)
    def queue_search(self):
        self.client.get(f"/api/break-requests/?search={random.choice(LAST_NAMES)}",
                        name="/api/break-requests/?search=[name]")

    @task(1)
    def queue_deep_page(self):
        self.client.get(f"/api/break-requests/?status=PENDING&page={random.randint(20, 100)}",
                        name="/api/break-requests/?status=PENDING&page=[20-100]")

    @task(2)
    def register(self):
        self.client.get("/api/register/")

    @task(2)
    def summary(self):
        self.client.get("/api/register/summary/")

    @task(1)
    def daily_stats(self):
        self.client.get("/api/register/daily-stats/")

    @task(2)
    def on_break(self):
        day = (date.today() - timedelta(days=random.randint(1, 60))).isoformat()
        self.client.get(f"/api/register/on-break/?at={day}T{random.randint(8, 17):02d}:30",
                        name="/api/register/on-break/?at=[time]")

    @task(1)
    def approve_one(self):
        r = self.client.get("/api/break-requests/?status=PENDING&page_size=20",
                            name="/api/break-requests/?status=PENDING&page_size=20")
        results = r.json().get("results", []) if r.ok else []
        if results:
            pk = random.choice(results)["id"]
            self.expect("POST", f"/api/break-requests/{pk}/approve/",
                        "/api/break-requests/[id]/approve/", {200, 409}, json={})


class HotSlotEmployee(ApiUser):
    """Contention: many employees of ONE organisation want the SAME slots."""

    weight = 4
    token_pool = "hot_employee"

    @task
    def submit_hot_slot(self):
        body = {"date": HOT_DAY, "start_time": random.choice(HOT_SLOTS),
                "duration_minutes": 30, "client_request_id": str(uuid.uuid4())}
        self.expect("POST", "/api/my/break-requests/", "HOT submit same slot",
                    {200, 201, 400, 409}, json=body)


class HotSlotManager(ApiUser):
    """Contention: managers bulk-approve the hot day in parallel."""

    weight = 1
    token_pool = "hot_manager"

    @task
    def bulk_approve_hot_day(self):
        r = self.client.get(
            f"/api/break-requests/?status=PENDING&date_from={HOT_DAY}&date_to={HOT_DAY}&page_size=50",
            name="HOT list pending")
        ids = [item["id"] for item in r.json().get("results", [])] if r.ok else []
        if ids:
            self.expect("POST", "/api/break-requests/bulk-review/", "HOT bulk approve",
                        {200}, json={"ids": ids, "action": "approve"})
                        