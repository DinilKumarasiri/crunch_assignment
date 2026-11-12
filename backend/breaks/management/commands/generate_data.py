"""
Generate a large, realistic, constraint-respecting dataset.

    python manage.py generate_data                 # 50 orgs, 100k employees, 100 managers, 1M requests
    python manage.py generate_data --reset         # delete previously generated data first
    python manage.py generate_data --orgs 5 --employees 1000 --managers 10 --requests 10000  # quick test

Every generated user has the password "password123".
Usernames: gen_o01_m1 (manager), gen_o01_e00001 (employee), ...
"""
import random
import time as clock
from collections import defaultdict
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from accounts.models import Organisation, User
from breaks.models import BreakPolicy, BreakRequest

ORG_PREFIX = "Generated Org"
PASSWORD = "password123"

FIRST_NAMES = [
    "Amal", "Nimal", "Kasun", "Dilani", "Sanduni", "Tharindu", "Ishara", "Chamari",
    "James", "Olivia", "Liam", "Emma", "Noah", "Ava", "Lucas", "Mia", "Ethan", "Sofia",
    "Arjun", "Priya", "Ravi", "Anika", "Omar", "Layla", "Chen", "Mei", "Kenji", "Yuki",
]
LAST_NAMES = [
    "Perera", "Silva", "Fernando", "Jayasinghe", "Bandara", "Wickramasinghe", "Dissanayake",
    "Smith", "Johnson", "Brown", "Taylor", "Wilson", "Anderson", "Thomas", "Moore",
    "Patel", "Sharma", "Khan", "Ali", "Wang", "Li", "Tanaka", "Sato", "Garcia", "Lopez",
]
REJECTION_NOTES = ["Team meeting at that time", "Short-staffed", "Customer deadline", ""]
CAPACITY_NOTE = "Too many people on break at that time"

APPROVED = BreakRequest.Status.APPROVED.value
REJECTED = BreakRequest.Status.REJECTED.value
PENDING = BreakRequest.Status.PENDING.value
MANAGER = User.Role.MANAGER.value
EMPLOYEE = User.Role.EMPLOYEE.value

DAY_START = time(8, 0)
WORKDAY_MINUTES = 600                                 # 08:00 - 18:00
BUCKET_MINUTES = 5
START_OFFSETS = list(range(0, WORKDAY_MINUTES - 45 + 1, 15))  # 08:00 ... 17:15
DURATIONS = [10, 15, 15, 20, 30, 30, 45]              # weighted towards common lengths
PAST_DAYS, FUTURE_DAYS = 90, 30

USER_COLUMNS = (
    "password", "last_login", "is_superuser", "username", "first_name", "last_name",
    "email", "is_staff", "is_active", "date_joined", "organisation_id", "role",
)
REQUEST_COLUMNS = (
    "organisation_id", "employee_id", "break_date", "start_at", "end_at",
    "duration_minutes", "status", "client_request_id", "reviewed_by_id", "reviewed_at",
    "review_note", "created_at", "updated_at",
)


def split_evenly(total, parts):
    """split_evenly(10, 3) -> [4, 3, 3]"""
    base, extra = divmod(total, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


class Command(BaseCommand):
    help = "Generate organisations, users and break requests for performance testing."

    def add_arguments(self, parser):
        parser.add_argument("--orgs", type=int, default=50)
        parser.add_argument("--employees", type=int, default=100_000)
        parser.add_argument("--managers", type=int, default=100)
        parser.add_argument("--requests", type=int, default=1_000_000)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--reset", action="store_true",
                            help="Delete previously generated data first.")

    # ------------------------------------------------------------------ main
    def handle(self, *args, **opts):
        existing_ids = list(
            Organisation.objects.filter(name__startswith=ORG_PREFIX).values_list("id", flat=True)
        )
        if existing_ids:
            if not opts["reset"]:
                raise CommandError("Generated data already exists. Re-run with --reset to replace it.")
            self.reset(existing_ids)

        if opts["managers"] < opts["orgs"]:
            raise CommandError("Need at least one manager per organisation.")
        if opts["requests"] > opts["employees"] * (PAST_DAYS + FUTURE_DAYS):
            raise CommandError("Too many requests: max one break per employee per day.")

        self.rng = random.Random(opts["seed"])         # reproducible dataset
        self.password_hash = make_password(PASSWORD)   # hashed ONCE, reused for every user
        self.tz = ZoneInfo(settings.TIME_ZONE)
        self.now = timezone.now()
        self.today = timezone.localdate()
        self.days = [self.today + timedelta(days=d) for d in range(-PAST_DAYS, FUTURE_DAYS)]

        employees_per_org = split_evenly(opts["employees"], opts["orgs"])
        managers_per_org = split_evenly(opts["managers"], opts["orgs"])
        requests_per_employee = split_evenly(opts["requests"], opts["employees"])

        totals = defaultdict(int)
        employee_offset = 0
        started = clock.perf_counter()

        for i in range(opts["orgs"]):
            org_started = clock.perf_counter()
            with transaction.atomic():  # one transaction per org: a failure never leaves half an org
                org, policy = self.create_org(i + 1)
                manager_ids, employee_ids = self.create_users(
                    org, i + 1, managers_per_org[i], employees_per_org[i]
                )
                quota = requests_per_employee[employee_offset: employee_offset + len(employee_ids)]
                counts = self.create_requests(org, policy, manager_ids, employee_ids, quota)
            employee_offset += len(employee_ids)
            for status, n in counts.items():
                totals[status] += n
            self.stdout.write(
                f"[{i + 1:>2}/{opts['orgs']}] {org.name}: {len(employee_ids):,} employees, "
                f"{sum(counts.values()):,} requests, capacity {policy.max_concurrent_breaks} "
                f"({clock.perf_counter() - org_started:.1f}s)"
            )

        self.stdout.write("Running VACUUM ANALYZE (planner statistics + visibility map) ...")
        with connection.cursor() as cursor:
            for table in ("accounts_organisation", "accounts_user",
                          "breaks_breakpolicy", "breaks_breakrequest"):
                cursor.execute(f"VACUUM ANALYZE {table}")

        self.stdout.write(self.style.SUCCESS(
            f"Done in {clock.perf_counter() - started:.0f}s. "
            f"Requests by status: {dict(totals)}. Password for all generated users: '{PASSWORD}'."
        ))

    # ------------------------------------------------------------------ steps
    def create_org(self, n):
        org = Organisation.objects.create(name=f"{ORG_PREFIX} {n:02d}")
        policy = BreakPolicy.objects.create(
            organisation=org,
            min_duration_minutes=5, max_duration_minutes=60, max_daily_minutes=90,
            max_requests_per_day=3, min_advance_notice_minutes=30,
            max_concurrent_breaks=self.rng.randint(8, 20),
            requires_approval=True,
        )
        return org, policy

    def create_users(self, org, n, managers, employees):
        prefix = f"gen_o{n:02d}"
        rows = [self.user_row(org.id, f"{prefix}_m{m}", MANAGER) for m in range(1, managers + 1)]
        rows += [self.user_row(org.id, f"{prefix}_e{e:05d}", EMPLOYEE) for e in range(1, employees + 1)]
        self.copy("accounts_user", USER_COLUMNS, rows)

        ids = defaultdict(list)
        for pk, role in (User.objects.filter(organisation=org)
                         .order_by("id").values_list("id", "role")):
            ids[role].append(pk)
        return ids[MANAGER], ids[EMPLOYEE]

    def create_requests(self, org, policy, manager_ids, employee_ids, quota):
        capacity = policy.max_concurrent_breaks
        buckets_per_day = WORKDAY_MINUTES // BUCKET_MINUTES
        occupancy = defaultdict(lambda: [0] * buckets_per_day)  # day -> people on break per bucket
        counts = defaultdict(int)

        def rows():  # a generator: rows are produced one at a time and streamed to COPY
            for employee_id, how_many in zip(employee_ids, quota):
                for day in self.rng.sample(self.days, how_many):  # distinct days -> no overlaps
                    offset = self.rng.choice(START_OFFSETS)
                    duration = self.rng.choice(DURATIONS)
                    status, note = self.pick_status(is_past=day < self.today)

                    if status == APPROVED:
                        buckets = occupancy[day]
                        first = offset // BUCKET_MINUTES
                        last = (offset + duration) // BUCKET_MINUTES
                        if all(buckets[b] < capacity for b in range(first, last)):
                            for b in range(first, last):
                                buckets[b] += 1
                        else:
                            status, note = REJECTED, CAPACITY_NOTE

                    counts[status] += 1
                    yield self.request_row(org.id, employee_id, day, offset, duration,
                                           status, note, manager_ids)

        self.copy("breaks_breakrequest", REQUEST_COLUMNS, rows())
        return counts

    # ------------------------------------------------------------------ helpers
    def pick_status(self, is_past):
        r = self.rng.random()
        if is_past:
            if r < 0.75:
                return APPROVED, ""
            if r < 0.92:
                return REJECTED, self.rng.choice(REJECTION_NOTES)
            return PENDING, ""  # never reviewed
        if r < 0.60:
            return PENDING, ""
        if r < 0.95:
            return APPROVED, ""
        return REJECTED, self.rng.choice(REJECTION_NOTES)

    def user_row(self, org_id, username, role):
        return (
            self.password_hash, None, False, username,
            self.rng.choice(FIRST_NAMES), self.rng.choice(LAST_NAMES),
            f"{username}@example.com", False, True, self.now, org_id, role,
        )

    def request_row(self, org_id, employee_id, day, offset, duration, status, note, manager_ids):
        start = datetime.combine(day, DAY_START, tzinfo=self.tz) + timedelta(minutes=offset)
        end = start + timedelta(minutes=duration)
        created = min(self.now, start - timedelta(hours=self.rng.randint(2, 7 * 24)))
        reviewed_by = reviewed_at = None
        if status != PENDING:
            reviewed_by = self.rng.choice(manager_ids)
            reviewed_at = min(self.now, created + timedelta(minutes=self.rng.randint(5, 600)))
        return (
            org_id, employee_id, day, start, end, duration, status, None,
            reviewed_by, reviewed_at, note, created, reviewed_at or created,
        )

    def copy(self, table, columns, rows):
        """Stream rows into Postgres with COPY (much faster than INSERT)."""
        sql = f"COPY {table} ({', '.join(columns)}) FROM STDIN"
        with connection.cursor() as cursor:
            with cursor.cursor.copy(sql) as copy:  # cursor.cursor = the raw psycopg cursor
                for row in rows:
                    copy.write_row(row)

    def reset(self, org_ids):
        """Raw SQL DELETE: the ORM would load millions of objects to process cascades."""
        self.stdout.write(f"Deleting generated data for {len(org_ids)} organisations ...")
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("DELETE FROM breaks_breakrequest WHERE organisation_id = ANY(%s)", [org_ids])
            cursor.execute("DELETE FROM breaks_breakpolicy WHERE organisation_id = ANY(%s)", [org_ids])
            cursor.execute("DELETE FROM accounts_user WHERE organisation_id = ANY(%s)", [org_ids])
            cursor.execute("DELETE FROM accounts_organisation WHERE id = ANY(%s)", [org_ids])
            