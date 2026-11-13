import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from breaks.models import BreakRequest
from helpers import client_for, future_day, make_user, submit

pytestmark = pytest.mark.django_db


def pending(employee, day, start="10:00", minutes=15):
    res = submit(client_for(employee), day, start, minutes)
    assert res.status_code == 201, res.data
    return res.data["id"]


def approve(client, pk):
    return client.post(f"/api/break-requests/{pk}/approve/", {}, format="json")


def test_approve_sets_audit_fields(manager, employee):
    pk = pending(employee, future_day())
    res = client_for(manager).post(f"/api/break-requests/{pk}/approve/", {"note": "ok"}, format="json")
    assert res.status_code == 200
    reviewed = BreakRequest.objects.get(pk=pk)
    assert (reviewed.status, reviewed.reviewed_by, reviewed.review_note) == ("APPROVED", manager, "ok")
    assert reviewed.reviewed_at is not None


def test_second_review_conflicts(manager, employee):
    pk = pending(employee, future_day())
    client = client_for(manager)
    assert approve(client, pk).status_code == 200
    assert client.post(f"/api/break-requests/{pk}/reject/", {}, format="json").status_code == 409


def test_other_organisation_gets_404_and_nothing_changes(employee, other_manager):
    pk = pending(employee, future_day())
    assert approve(client_for(other_manager), pk).status_code == 404
    assert BreakRequest.objects.get(pk=pk).status == "PENDING"


def test_bulk_review_reports_every_item(manager, employee, employee2, other_manager):
    day = future_day()
    already = pending(employee, day, "09:00")
    fresh = pending(employee2, day, "11:00")
    foreign = pending(make_user(other_manager.organisation, "gx"), day)
    approve(client_for(manager), already)

    res = client_for(manager).post("/api/break-requests/bulk-review/",
                                   {"ids": [already, fresh, foreign], "action": "reject"}, format="json")
    assert res.data["processed"] == [fresh]
    assert {s["id"]: s["reason"] for s in res.data["skipped"]} == {
        already: "already_approved", foreign: "not_found",
    }


def test_bulk_approve_respects_capacity(acme, manager):  # capacity = 2
    day = future_day()
    ids = [pending(make_user(acme, f"e{i}"), day, "10:00", 30) for i in range(3)]
    res = client_for(manager).post("/api/break-requests/bulk-review/",
                                   {"ids": ids, "action": "approve"}, format="json")
    assert len(res.data["processed"]) == 2
    assert [s["reason"] for s in res.data["skipped"]] == ["capacity_reached"]
    assert BreakRequest.objects.filter(status="APPROVED").count() == 2


def test_capacity_counts_peak_overlap_not_total(acme, manager):  # capacity = 2
    day, client = future_day(), client_for(manager)
    x = pending(make_user(acme, "x"), day, "09:00", 10)   # 09:00-09:10
    y = pending(make_user(acme, "y"), day, "09:20", 10)   # 09:20-09:30
    z = pending(make_user(acme, "z"), day, "09:00", 30)   # overlaps both, never together
    w = pending(make_user(acme, "w"), day, "09:05", 10)   # would make 3 at 09:05
    assert approve(client, x).status_code == 200
    assert approve(client, y).status_code == 200
    assert approve(client, z).status_code == 200
    assert approve(client, w).status_code == 409


def test_queue_search_and_ordering(manager, employee, employee2):
    day = future_day()
    pending(employee, day, "09:00", 10)
    pending(employee2, day, "10:00", 30)
    client = client_for(manager)

    found = client.get("/api/break-requests/", {"search": "emma"}).data["results"]
    assert [r["employee_name"] for r in found] == ["Emma Test"]

    ordered = client.get("/api/break-requests/", {"ordering": "-duration_minutes"}).data["results"]
    assert [r["duration_minutes"] for r in ordered] == [30, 10]


def test_employee_cannot_open_queue(employee):
    assert client_for(employee).get("/api/break-requests/").status_code == 403


def test_queue_has_no_n_plus_one(acme, manager):
    day = future_day()
    for i in range(12):
        pending(make_user(acme, f"q{i}"), day, f"{8 + i % 8:02d}:{(i // 8) * 30:02d}", 10)
    client = client_for(manager)

    def queries_for(page_size):
        with CaptureQueriesContext(connection) as ctx:
            assert client.get("/api/break-requests/", {"page_size": page_size}).status_code == 200
        return len(ctx.captured_queries)

    assert queries_for(2) == queries_for(12)