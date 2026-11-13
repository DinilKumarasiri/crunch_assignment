import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from breaks.models import BreakPolicy, BreakRequest
from helpers import client_for, future_day, make_user, submit

pytestmark = pytest.mark.django_db


def test_valid_request_is_created_pending_with_derived_fields(employee):
    day = future_day()
    res = submit(client_for(employee), day, "10:00", 15)
    assert res.status_code == 201
    assert res.data["status"] == "PENDING"
    created = BreakRequest.objects.get(pk=res.data["id"])
    assert created.organisation_id == employee.organisation_id
    assert created.end_at - created.start_at == timedelta(minutes=15)
    assert created.break_date.isoformat() == day


def test_overlap_rejected_but_back_to_back_allowed(employee):
    client, day = client_for(employee), future_day()
    assert submit(client, day, "10:00", 15).status_code == 201
    assert submit(client, day, "10:10", 15).status_code == 409
    assert submit(client, day, "10:15", 15).status_code == 201


def test_rejected_request_frees_the_slot(employee):
    client, day = client_for(employee), future_day()
    first = submit(client, day, "10:00", 15).data
    BreakRequest.objects.filter(pk=first["id"]).update(status="REJECTED")
    assert submit(client, day, "10:00", 15).status_code == 201


@pytest.mark.parametrize("minutes", [4, 61])
def test_duration_must_respect_policy(employee, minutes):
    res = submit(client_for(employee), future_day(), "10:00", minutes)
    assert res.status_code == 400
    assert "duration_minutes" in res.data


def test_advance_notice_is_enforced(employee):
    soon = timezone.localtime() + timedelta(minutes=10)
    res = submit(client_for(employee), soon.date().isoformat(), soon.strftime("%H:%M"), 10)
    assert res.status_code == 400
    assert "start_time" in res.data


def test_max_requests_per_day(employee):
    client, day = client_for(employee), future_day()
    for start in ("09:00", "10:00", "11:00"):
        assert submit(client, day, start, 10).status_code == 201
    res = submit(client, day, "12:00", 10)
    assert res.status_code == 400
    assert "non_field_errors" in res.data


def test_daily_minutes_allowance(employee):
    client, day = client_for(employee), future_day()
    assert submit(client, day, "09:00", 60).status_code == 201
    res = submit(client, day, "11:00", 45)  # 60 + 45 > 90
    assert res.status_code == 400
    assert "duration_minutes" in res.data


def test_same_client_request_id_is_replayed_not_duplicated(employee):
    client, day, key = client_for(employee), future_day(), uuid.uuid4()
    first = submit(client, day, "10:00", 15, key)
    again = submit(client, day, "10:00", 15, key)
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.data["id"] == again.data["id"]
    assert BreakRequest.objects.filter(employee=employee).count() == 1


def test_auto_approval_when_policy_allows(employee):
    BreakPolicy.objects.filter(organisation=employee.organisation).update(requires_approval=False)
    res = submit(client_for(employee), future_day())
    assert res.status_code == 201
    assert res.data["status"] == "APPROVED"


def test_auto_approval_respects_capacity(acme):
    BreakPolicy.objects.filter(organisation=acme).update(requires_approval=False, max_concurrent_breaks=1)
    day = future_day()
    assert submit(client_for(make_user(acme, "a")), day, "10:00", 30).status_code == 201
    assert submit(client_for(make_user(acme, "b")), day, "10:15", 30).status_code == 409


def test_history_shows_only_own_requests(employee, employee2):
    day = future_day()
    submit(client_for(employee2), day, "10:00", 15)
    mine = submit(client_for(employee), day, "11:00", 15).data["id"]
    res = client_for(employee).get("/api/my/break-requests/")
    assert [r["id"] for r in res.data["results"]] == [mine]


def test_manager_cannot_use_employee_endpoint(manager):
    assert submit(client_for(manager), future_day()).status_code == 403