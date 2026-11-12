from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


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

    def __str__(self):
        return f"Policy for {self.organisation}"

    def clean(self):
        """Cross-field validation (rules that involve more than one field)."""
        errors = {}
        if self.min_duration_minutes > self.max_duration_minutes:
            errors["min_duration_minutes"] = "Must not exceed the maximum duration."
        if self.max_duration_minutes > self.max_daily_minutes:
            errors["max_duration_minutes"] = "A single break cannot exceed the daily allowance."
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
    )
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="break_requests",
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

    # NOTE: deliberately no Meta.ordering (design decision #7).

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