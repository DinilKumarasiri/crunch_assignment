"""Small factories and shortcuts shared by all tests."""
from datetime import date, datetime, time, timedelta

from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Organisation, User
from breaks.models import BreakPolicy, BreakRequest

PASSWORD = "pass12345"
DEFAULT_POLICY = dict(
    min_duration_minutes=5, max_duration_minutes=60, max_daily_minutes=90,
    max_requests_per_day=3, min_advance_notice_minutes=30,
    max_concurrent_breaks=2, requires_approval=True,
)


def make_org(name, **policy):
    org = Organisation.objects.create(name=name)
    BreakPolicy.objects.create(organisation=org, **{**DEFAULT_POLICY, **policy})
    return org


def make_user(org, username, role=User.Role.EMPLOYEE, first_name=None):
    return User.objects.create_user(
        username=username, password=PASSWORD, organisation=org, role=role,
        first_name=first_name or username.title(), last_name="Test",
    )


def client_for(user):
    """An API client already authenticated as `user` (skips the JWT round trip)."""
    client = APIClient()
    client.force_authenticate(user)
    return client


def future_day(days=2):
    return (timezone.localdate() + timedelta(days=days)).isoformat()


def submit(client, day, start="10:00", minutes=15, key=None):
    body = {"date": day, "start_time": start, "duration_minutes": minutes}
    if key:
        body["client_request_id"] = str(key)
    return client.post("/api/my/break-requests/", body, format="json")


def create_break(employee, day, start, minutes, status=BreakRequest.Status.APPROVED):
    """Insert a break directly (bypassing the API), e.g. to set up register data."""
    start_at = timezone.make_aware(datetime.combine(date.fromisoformat(day), time.fromisoformat(start)))
    return BreakRequest.objects.create(
        employee=employee, start_at=start_at, duration_minutes=minutes, status=status
    )