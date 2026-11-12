from datetime import timedelta

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators
from django.contrib.postgres.indexes import GistIndex
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Func, Q
from django.utils import timezone


class TsTzRange(Func):
    """SQL: TSTZRANGE(start_at, end_at, '[)') - a time period as one value."""

    function = "TSTZRANGE"
    output_field = DateTimeRangeField()

class BreakPolicy(models.Model):
    """Break rules for one organisation. Configured by managers (Screen 1)."""

    organisation = models.OneToOneField(
        "accounts.Organisation",
        on_delete=models.CASCADE,
        related_name="break_policy",
    )
    min_duration_minutes = models.PositiveSmallIntegerField(default=5)
    max_duration_minutes = models.PositiveSmallIntegerField(default=60)
    max_daily_minutes = models.PositiveSmallIntegerField(default=90)
    max_requests_per_day = models.PositiveSmallIntegerField(default=3)
    min_advance_notice_minutes = models.PositiveIntegerField(default=30)
    max_concurrent_breaks = models.PositiveSmallIntegerField(default=5)
    requires_approval = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)  # optimistic locking

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",  # "+" = no reverse relation needed
    )

    class Meta:
        verbose_name_plural = "break policies"
        constraints = [
            models.CheckConstraint(
                condition=Q(min_duration_minutes__gte=1),
                name="policy_min_duration_gte_1",
            ),
            models.CheckConstraint(
                condition=Q(min_duration_minutes__lte=F("max_duration_minutes")),
                name="policy_min_lte_max_duration",
            ),
            models.CheckConstraint(
                condition=Q(max_duration_minutes__lte=F("max_daily_minutes")),
                name="policy_max_duration_lte_daily",
            ),
            models.CheckConstraint(
                condition=Q(max_requests_per_day__gte=1),
                name="policy_requests_per_day_gte_1",
            ),
            models.CheckConstraint(
                condition=Q(max_concurrent_breaks__gte=1),
                name="policy_concurrent_gte_1",
            ),
        ]

    def __str__(self):
        return f"Policy for {self.organisation}"

    # def clean(self):
    #     """Cross-field validation (rules that involve more than one field)."""
    #     errors = {}
    #     if self.min_duration_minutes > self.max_duration_minutes:
    #         errors["min_duration_minutes"] = "Must not exceed the maximum duration."
    #     if self.max_duration_minutes > self.max_daily_minutes:
    #         errors["max_duration_minutes"] = "A single break cannot exceed the daily allowance."
    #     if errors:
    #         raise ValidationError(errors)
    @staticmethod
    def cross_field_errors(min_duration, max_duration, max_daily):
        """Rules involving several fields. Shared by Model.clean() and the API serializer."""
        errors = {}
        if min_duration is not None and max_duration is not None and min_duration > max_duration:
            errors["min_duration_minutes"] = "Must not exceed the maximum duration."
        if max_duration is not None and max_daily is not None and max_duration > max_daily:
            errors["max_duration_minutes"] = "A single break cannot exceed the daily allowance."
        return errors

    def clean(self):
        errors = self.cross_field_errors(
            self.min_duration_minutes, self.max_duration_minutes, self.max_daily_minutes
        )
        if errors:
            raise ValidationError(errors)


class BreakRequest(models.Model):
    """A single break submitted by an employee (Screens 2, 3, 4)."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    # Denormalised tenant column (see design decision #2).
    organisation = models.ForeignKey(
        "accounts.Organisation",
        on_delete=models.PROTECT,
        related_name="break_requests",
        db_index=False,  # covered by composite indexes starting with organisation
    )
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="break_requests",
        db_index=False,  # covered by the (employee, start_at) index
    )

    # Time fields. end_at and break_date are derived (design decision #3).
    break_date = models.DateField()
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField()

    status = models.CharField(
        max_length=8,
        choices=Status.choices,
        default=Status.PENDING,
    )

    # Idempotency key sent by the client (design decision #5).
    client_request_id = models.UUIDField(null=True, blank=True)

    # Review / audit trail.
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_break_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Still no `ordering` on purpose (see Step 4, decision #7).
        indexes = [
            # Screen 2 history + per-employee policy checks
            models.Index(fields=["employee", "start_at"], name="breakreq_emp_start_idx"),
            # Screen 3 queue with no status filter
            models.Index(fields=["organisation", "start_at"], name="breakreq_org_start_idx"),
            # Screen 3 queue by status + Screen 4 register/stats (status=APPROVED)
            models.Index(
                fields=["organisation", "status", "start_at"],
                name="breakreq_org_status_start_idx",
            ),
            # "Who is on break at time T" + max concurrent check, approved rows only
            GistIndex(
                F("organisation"),
                TsTzRange("start_at", "end_at", RangeBoundary()),
                name="breakreq_approved_period_gist",
                condition=Q(status="APPROVED"),
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(duration_minutes__gt=0),
                name="breakreq_duration_positive",
            ),
            models.CheckConstraint(
                condition=Q(end_at__gt=F("start_at")),
                name="breakreq_end_after_start",
            ),
            # Duplicate submissions (double-click / network retry)
            models.UniqueConstraint(
                fields=["employee", "client_request_id"],
                condition=Q(client_request_id__isnull=False),
                name="breakreq_unique_client_request",
                violation_error_message="This request has already been submitted.",
            ),
            # Overlapping requests, enforced by Postgres even under race conditions
            ExclusionConstraint(
                name="breakreq_no_overlap_per_employee",
                expressions=[
                    ("employee", RangeOperators.EQUAL),
                    (TsTzRange("start_at", "end_at", RangeBoundary()), RangeOperators.OVERLAPS),
                ],
                condition=Q(status__in=["PENDING", "APPROVED"]),
                violation_error_message="You already have a break that overlaps this time.",
            ),
        ]

    def __str__(self):
        return f"{self.employee_id} @ {self.start_at:%Y-%m-%d %H:%M} ({self.status})"

    def populate_derived_fields(self):
        """Fill organisation, end_at and break_date from the source fields."""
        if self.employee_id and not self.organisation_id:
            self.organisation_id = self.employee.organisation_id
        if self.start_at is not None and self.duration_minutes:
            self.end_at = self.start_at + timedelta(minutes=self.duration_minutes)
            self.break_date = timezone.localdate(self.start_at)

    def clean(self):
        self.populate_derived_fields()
        if self.employee_id and self.organisation_id != self.employee.organisation_id:
            raise ValidationError("Request organisation must match the employee's organisation.")

    def save(self, *args, **kwargs):
        self.populate_derived_fields()
        super().save(*args, **kwargs)