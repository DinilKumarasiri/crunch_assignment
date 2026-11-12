from rest_framework import serializers

from .models import BreakPolicy


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