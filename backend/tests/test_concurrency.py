"""
Real concurrent requests against the real database.

transaction=True: data is actually COMMITTED, so every thread's own database
connection can see it (normal tests run inside one uncommitted transaction).
"""
import threading
import uuid

import pytest
from django.db import connection

from accounts.models import User
from breaks.models import BreakPolicy, BreakRequest
from helpers import client_for, future_day, make_org, make_user, submit

pytestmark = pytest.mark.django_db(transaction=True)


def run_in_parallel(count, action):
    """Run action(i) in `count` threads released at the same instant. Returns results in order."""
    barrier = threading.Barrier(count)
    results = [None] * count

    def worker(i):
        try:
            barrier.wait()            # everyone starts together → maximum contention
            results[i] = action(i)
        except Exception as exc:      # surface errors as results instead of losing them
            results[i] = exc
        finally:
            connection.close()        # each thread opened its own DB connection

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_parallel_requests_for_same_slot_create_exactly_one():
    org = make_org("Race Co")
    employee = make_user(org, "racer")
    day = future_day()

    codes = run_in_parallel(8, lambda i: submit(client_for(employee), day, "10:00", 15).status_code)

    assert sorted(codes) == [201] + [409] * 7
    assert BreakRequest.objects.filter(employee=employee).count() == 1


def test_parallel_requests_respect_daily_limit():
    org = make_org("Limit Co")  # max_requests_per_day = 3
    employee = make_user(org, "busy")
    day = future_day()
    slots = ["08:00", "09:00", "10:00", "11:00", "12:00", "13:00"]

    codes = run_in_parallel(6, lambda i: submit(client_for(employee), day, slots[i], 10).status_code)

    assert sorted(codes) == [201] * 3 + [400] * 3
    assert BreakRequest.objects.filter(employee=employee).count() == 3


def test_parallel_double_click_creates_one_request():
    org = make_org("Click Co")
    employee = make_user(org, "clicker")
    day, key = future_day(), uuid.uuid4()

    responses = run_in_parallel(5, lambda i: submit(client_for(employee), day, "10:00", 15, key))

    assert sorted(r.status_code for r in responses) == [200] * 4 + [201]
    assert len({r.data["id"] for r in responses}) == 1
    assert BreakRequest.objects.filter(employee=employee).count() == 1


def test_parallel_approvals_never_exceed_capacity():
    org = make_org("Cap Co")  # max_concurrent_breaks = 2
    manager = make_user(org, "boss", User.Role.MANAGER)
    day = future_day()
    ids = [submit(client_for(make_user(org, f"e{i}")), day, "10:00", 30).data["id"] for i in range(6)]

    codes = run_in_parallel(6, lambda i: client_for(manager).post(
        f"/api/break-requests/{ids[i]}/approve/", {}, format="json").status_code)

    assert sorted(codes) == [200] * 2 + [409] * 4
    assert BreakRequest.objects.filter(organisation=org, status="APPROVED").count() == 2


def test_parallel_auto_approvals_never_exceed_capacity():
    org = make_org("Auto Co", requires_approval=False)  # capacity 2
    employees = [make_user(org, f"a{i}") for i in range(6)]
    day = future_day()

    codes = run_in_parallel(6, lambda i: submit(client_for(employees[i]), day, "12:00", 15).status_code)

    assert sorted(codes) == [201] * 2 + [409] * 4
    assert BreakRequest.objects.filter(organisation=org, status="APPROVED").count() == 2


def test_overlapping_bulk_reviews_do_not_deadlock():
    org = make_org("Bulk Co", max_concurrent_breaks=50)
    managers = [make_user(org, f"m{i}", User.Role.MANAGER) for i in range(2)]
    day = future_day()
    ids = [submit(client_for(make_user(org, f"b{i}")), day, f"{8 + i}:00", 15).data["id"]
           for i in range(8)]
    batches = [ids, list(reversed(ids))]  # opposite orders: would deadlock without sorted locking

    responses = run_in_parallel(2, lambda i: client_for(managers[i]).post(
        "/api/break-requests/bulk-review/", {"ids": batches[i], "action": "approve"}, format="json"))

    assert [r.status_code for r in responses] == [200, 200]
    processed = responses[0].data["processed"] + responses[1].data["processed"]
    assert sorted(processed) == sorted(ids)  # every request approved exactly once
    