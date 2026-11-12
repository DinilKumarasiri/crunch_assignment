from datetime import datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import User

from .exceptions import Conflict
from .models import BreakPolicy, BreakRequest

ACTIVE_STATUSES = [BreakRequest.Status.PENDING, BreakRequest.Status.APPROVED]


def _violated_constraint(exc):
    """Name of the Postgres constraint behind an IntegrityError, if available."""
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None)


def _local_day_bounds(day):
    """[start, end) of a calendar day in the project time zone, as aware datetimes."""
    start = timezone.make_aware(datetime.combine(day, time.min))
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
    return start, end


def _validate_against_policy(employee, policy, start_at, duration_minutes):
    # Rules 1 & 2: cheap checks that don't need the database.
    errors = {}
    if not policy.min_duration_minutes <= duration_minutes <= policy.max_duration_minutes:
        errors["duration_minutes"] = (
            f"Duration must be between {policy.min_duration_minutes} "
            f"and {policy.max_duration_minutes} minutes."
        )
    earliest = timezone.now() + timedelta(minutes=policy.min_advance_notice_minutes)
    if start_at < earliest:
        errors["start_time"] = (
            f"Breaks must be requested at least {policy.min_advance_notice_minutes} "
            f"minutes in advance."
        )
    if errors:
        raise ValidationError(errors)

    # Rules 3 & 4: ONE aggregate query gives both the count and the minutes used.
    day_start, day_end = _local_day_bounds(timezone.localdate(start_at))
    totals = BreakRequest.objects.filter(
        employee=employee,
        status__in=ACTIVE_STATUSES,
        start_at__gte=day_start,   # range on start_at → uses the (employee, start_at) index
        start_at__lt=day_end,
    ).aggregate(count=Count("id"), minutes=Sum("duration_minutes"))

    if totals["count"] >= policy.max_requests_per_day:
        raise ValidationError(
            {"non_field_errors": [
                f"You can request at most {policy.max_requests_per_day} breaks per day."
            ]}
        )
    used = totals["minutes"] or 0
    if used + duration_minutes > policy.max_daily_minutes:
        raise ValidationError(
            {"duration_minutes": [
                f"Daily allowance exceeded: {used} of {policy.max_daily_minutes} "
                f"minutes already used on this day."
            ]}
        )


def submit_break_request(*, employee, start_at, duration_minutes, client_request_id=None):
    """
    Create a break request for `employee`, enforcing the organisation's policy.

    Returns (break_request, created). created=False means an idempotent replay:
    the same client_request_id was already submitted, so the original is returned.
    """
    try:
        with transaction.atomic():
            # Serialise submissions from THIS employee only (fixes the check-then-act race).
            User.objects.select_for_update(no_key=True).only("id").get(pk=employee.pk)

            # Idempotency: checked INSIDE the lock, so a parallel duplicate sees the first one.
            if client_request_id:
                existing = BreakRequest.objects.filter(
                    employee=employee, client_request_id=client_request_id
                ).first()
                if existing:
                    return existing, False

            policy, _ = BreakPolicy.objects.get_or_create(
                organisation_id=employee.organisation_id
            )
            _validate_against_policy(employee, policy, start_at, duration_minutes)

            auto_approve = not policy.requires_approval
            # TODO (Step 11): auto-approved breaks must also respect max_concurrent_breaks.
            break_request = BreakRequest(
                organisation_id=employee.organisation_id,
                employee=employee,
                start_at=start_at,
                duration_minutes=duration_minutes,
                client_request_id=client_request_id,
                status=BreakRequest.Status.APPROVED if auto_approve else BreakRequest.Status.PENDING,
                reviewed_at=timezone.now() if auto_approve else None,
            )
            break_request.save()  # the DB exclusion constraint checks overlaps here
    except IntegrityError as exc:
        constraint = _violated_constraint(exc)
        if constraint == "breakreq_no_overlap_per_employee":
            raise Conflict("You already have a pending or approved break that overlaps this time.")
        if constraint == "breakreq_unique_client_request":
            # Defensive: the lock should prevent this, but replay safely if it ever happens.
            return BreakRequest.objects.get(
                employee=employee, client_request_id=client_request_id
            ), False
        raise  # unknown problem → the global handler returns 409

    return break_request, True

    