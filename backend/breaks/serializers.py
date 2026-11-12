from rest_framework import serializers

from datetime import datetime, timedelta

from django.utils import timezone

from .models import BreakPolicy, BreakRequest


class BreakPolicySerializer(serializers.ModelSerializer):
    version = serializers.IntegerField(min_value=1)  # required on PUT, returned on GET
    updated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = BreakPolicy
        fields = [
            "min_duration_minutes",
            "max_duration_minutes",
            "max_daily_minutes",
            "max_requests_per_day",
            "min_advance_notice_minutes",
            "max_concurrent_breaks",
            "requires_approval",
            "version",
            "updated_at",
            "updated_by_name",
        ]
        read_only_fields = ["updated_at"]
        # Field-level limits: sensible business bounds, checked before the DB is touched.
        extra_kwargs = {
            "min_duration_minutes": {"min_value": 1, "max_value": 480},
            "max_duration_minutes": {"min_value": 1, "max_value": 480},
            "max_daily_minutes": {"min_value": 1, "max_value": 1440},
            "max_requests_per_day": {"min_value": 1, "max_value": 50},
            "min_advance_notice_minutes": {"min_value": 0, "max_value": 10080},  # up to 7 days
            "max_concurrent_breaks": {"min_value": 1, "max_value": 10000},
        }

    def get_updated_by_name(self, obj):
        return obj.updated_by.get_full_name() if obj.updated_by_id else None

    def validate(self, attrs):
        """Object-level validation: rules that involve several fields."""
        errors = BreakPolicy.cross_field_errors(
            attrs.get("min_duration_minutes"),
            attrs.get("max_duration_minutes"),
            attrs.get("max_daily_minutes"),
        )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class BreakRequestSerializer(serializers.ModelSerializer):
    """Output: how a break request looks in API responses."""

    class Meta:
        model = BreakRequest
        fields = [
            "id", "break_date", "start_at", "end_at", "duration_minutes",
            "status", "review_note", "reviewed_at", "created_at",
        ]
        read_only_fields = fields


class BreakRequestCreateSerializer(serializers.Serializer):
    """Input: what an employee sends to submit a break."""

    date = serializers.DateField()
    start_time = serializers.TimeField()
    duration_minutes = serializers.IntegerField(min_value=1, max_value=1440)
    client_request_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        start_time = attrs["start_time"].replace(second=0, microsecond=0)
        naive = datetime.combine(attrs["date"], start_time)
        attrs["start_at"] = timezone.make_aware(naive)  # interpret in the project time zone
        return attrs


class QueueItemSerializer(BreakRequestSerializer):
    """A break request as the manager sees it: includes the employee."""

    employee_id = serializers.IntegerField(read_only=True)
    employee_name = serializers.SerializerMethodField()

    class Meta(BreakRequestSerializer.Meta):
        fields = BreakRequestSerializer.Meta.fields + ["employee_id", "employee_name"]
        read_only_fields = fields

    def get_employee_name(self, obj):
        return obj.employee.get_full_name() or obj.employee.username


class ReviewSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class BulkReviewSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), min_length=1, max_length=100
    )
    action = serializers.ChoiceField(choices=["approve", "reject"])
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")



class OnBreakQuerySerializer(serializers.Serializer):
    at = serializers.DateTimeField()  # "2026-11-20T10:30" is read in the project time zone


class DateRangeQuerySerializer(serializers.Serializer):
    """Optional date range. Defaults to the last 30 days, capped at 366 days."""

    MAX_DAYS = 366

    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate(self, attrs):
        date_to = attrs.get("date_to") or timezone.localdate()
        date_from = attrs.get("date_from") or date_to - timedelta(days=29)
        if date_from > date_to:
            raise serializers.ValidationError({"date_from": "Must be on or before date_to."})
        if (date_to - date_from).days >= self.MAX_DAYS:
            raise serializers.ValidationError(
                {"date_to": f"The range can be at most {self.MAX_DAYS} days."}
            )
        attrs["date_from"], attrs["date_to"] = date_from, date_to
        return attrs