from datetime import datetime, time, timedelta
from functools import reduce
from operator import or_

from django.contrib.postgres.fields import RangeBoundary
from django.db import IntegrityError, transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import User

from .exceptions import Conflict
from .models import BreakPolicy, BreakRequest, TsTzRange

ACTIVE_STATUSES = [BreakRequest.Status.PENDING, BreakRequest.Status.APPROVED]


def _violated_constraint(exc):
    """Name of the Postgres constraint behind an IntegrityError, if available."""
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None)


def local_day_bounds(day):
    """[start, end) of a calendar day in the project time zone, as aware datetimes."""
    start = timezone.make_aware(datetime.combine(day, time.min))
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
    return start, end

def peak_concurrency(intervals, window_start, window_end):
    """
    Highest number of intervals active at the same instant inside [window_start, window_end).
    Sweep line: +1 at each start, -1 at each end; ends sort before starts at the
    same instant because intervals are half-open '[)'.
    """
    events = []
    for start, end in intervals:
        start, end = max(start, window_start), min(end, window_end)
        if start < end:
            events.append((start, 1))
            events.append((end, -1))
    events.sort()  # (time, -1) sorts before (time, +1)
    peak = current = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


def fits_capacity(interval, busy_intervals, capacity):
    """Would adding `interval` keep the peak number of simultaneous breaks <= capacity?"""
    start, end = interval
    overlapping = [(s, e) for s, e in busy_intervals if s < end and e > start]
    return peak_concurrency(overlapping, start, end) + 1 <= capacity


def approved_intervals_overlapping(organisation_id, windows):
    """
    (start_at, end_at) of APPROVED breaks in the organisation that overlap ANY of the
    given windows. ONE query, served by the partial GiST index from Step 5.
    """
    if not windows:
        return []
    overlaps_any = reduce(or_, (
        Q(period__overlap=DateTimeTZRange(start, end, "[)")) for start, end in windows
    ))
    return list(
        BreakRequest.objects
        .filter(organisation_id=organisation_id, status=BreakRequest.Status.APPROVED)
        .annotate(period=TsTzRange("start_at", "end_at", RangeBoundary()))
        .filter(overlaps_any)
        .values_list("start_at", "end_at")
    )


def lock_policy(organisation_id):
    """
    Lock the organisation's policy row. Every capacity decision in that organisation
    happens while holding this lock, so they run one at a time (different orgs stay parallel).
    """
    policy, _ = BreakPolicy.objects.get_or_create(organisation_id=organisation_id)
    return BreakPolicy.objects.select_for_update().get(pk=policy.pk)

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
    day_start, day_end = local_day_bounds(timezone.localdate(start_at))
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
            if not policy.requires_approval:
                # This submission will be approved immediately, so it takes the
                # organisation lock (lock order: user row -> policy row).
                policy = lock_policy(employee.organisation_id)

            _validate_against_policy(employee, policy, start_at, duration_minutes)

            auto_approve = not policy.requires_approval
            if auto_approve:
                end_at = start_at + timedelta(minutes=duration_minutes)
                busy = approved_intervals_overlapping(employee.organisation_id, [(start_at, end_at)])
                if not fits_capacity((start_at, end_at), busy, policy.max_concurrent_breaks):
                    raise Conflict(
                        "The maximum number of employees on break at that time has been reached."
                    )

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


def review_break_requests(*, manager, ids, approve, note=""):
    """
    Approve or reject PENDING requests belonging to the manager's organisation.

    Returns (processed_ids, skipped) where skipped maps id -> reason:
      "not_found"                              - doesn't exist OR belongs to another org
      "already_approved" / "already_rejected"
      "capacity_reached"                       - approving would exceed max_concurrent_breaks
    """
    ids = list(dict.fromkeys(ids))
    new_status = BreakRequest.Status.APPROVED if approve else BreakRequest.Status.REJECTED
    now = timezone.now()
    capacity_skipped = []

    with transaction.atomic():
        # Lock order: policy (organisation) first, then break request rows by id.
        policy = lock_policy(manager.organisation_id) if approve else None

        rows = list(
            BreakRequest.objects
            .filter(organisation_id=manager.organisation_id, id__in=ids)
            .select_for_update()
            .order_by("id")
            .values_list("id", "status", "start_at", "end_at")
        )
        current_status = {pk: st for pk, st, _, _ in rows}
        pending = [(pk, start, end) for pk, st, start, end in rows
                   if st == BreakRequest.Status.PENDING]

        if approve and pending:
            busy = approved_intervals_overlapping(
                manager.organisation_id, [(start, end) for _, start, end in pending]
            )
            to_update = []
            for pk, start, end in pending:  # id order = first come, first served
                if fits_capacity((start, end), busy, policy.max_concurrent_breaks):
                    to_update.append(pk)
                    busy.append((start, end))  # later items in this batch must count it
                else:
                    capacity_skipped.append(pk)
        else:
            to_update = [pk for pk, _, _ in pending]

        if to_update:
            BreakRequest.objects.filter(id__in=to_update).update(
                status=new_status,
                reviewed_by=manager,
                reviewed_at=now,
                review_note=note,
                updated_at=now,
            )

    skipped = {}
    for pk in ids:
        if pk not in current_status:
            skipped[pk] = "not_found"
        elif pk in capacity_skipped:
            skipped[pk] = "capacity_reached"
        elif current_status[pk] != BreakRequest.Status.PENDING:
            skipped[pk] = f"already_{current_status[pk].lower()}"
    return to_update, skipped