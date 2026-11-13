import pytest

from breaks.models import BreakPolicy
from helpers import client_for

pytestmark = pytest.mark.django_db

EDITABLE = [
    "min_duration_minutes", "max_duration_minutes", "max_daily_minutes",
    "max_requests_per_day", "min_advance_notice_minutes",
    "max_concurrent_breaks", "requires_approval",
]


def payload(current, **changes):
    body = {key: current[key] for key in EDITABLE}
    body["version"] = current["version"]
    body.update(changes)
    return body


def test_employee_can_read_but_not_update(employee):
    client = client_for(employee)
    current = client.get("/api/policy/")
    assert current.status_code == 200
    assert client.put("/api/policy/", payload(current.data), format="json").status_code == 403


def test_update_increments_version(manager):
    client = client_for(manager)
    current = client.get("/api/policy/").data
    res = client.put("/api/policy/", payload(current, max_concurrent_breaks=7), format="json")
    assert res.status_code == 200
    assert res.data["version"] == current["version"] + 1
    assert res.data["max_concurrent_breaks"] == 7


def test_stale_version_is_rejected_and_nothing_is_lost(manager):
    client = client_for(manager)
    current = client.get("/api/policy/").data
    client.put("/api/policy/", payload(current, max_concurrent_breaks=7), format="json")
    stale = client.put("/api/policy/", payload(current, max_concurrent_breaks=9), format="json")
    assert stale.status_code == 409
    assert BreakPolicy.objects.get(organisation=manager.organisation).max_concurrent_breaks == 7


@pytest.mark.parametrize("changes, field", [
    ({"min_duration_minutes": 50, "max_duration_minutes": 30}, "min_duration_minutes"),
    ({"max_duration_minutes": 120, "max_daily_minutes": 60}, "max_duration_minutes"),
    ({"max_requests_per_day": 0}, "max_requests_per_day"),
])
def test_invalid_policy_is_rejected(manager, changes, field):
    client = client_for(manager)
    current = client.get("/api/policy/").data
    res = client.put("/api/policy/", payload(current, **changes), format="json")
    assert res.status_code == 400
    assert field in res.data


def test_policies_are_isolated_per_organisation(manager, other_manager):
    client = client_for(manager)
    current = client.get("/api/policy/").data
    client.put("/api/policy/", payload(current, max_concurrent_breaks=9), format="json")
    other = client_for(other_manager).get("/api/policy/").data
    assert other["version"] == 1
    assert other["max_concurrent_breaks"] == 2