from django.contrib import admin

from .models import BreakPolicy, BreakRequest


@admin.register(BreakPolicy)
class BreakPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "organisation", "min_duration_minutes", "max_duration_minutes",
        "max_daily_minutes", "max_requests_per_day", "max_concurrent_breaks",
        "requires_approval",
    )
    list_select_related = ("organisation",)


@admin.register(BreakRequest)
class BreakRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "employee", "organisation", "start_at", "duration_minutes", "status")
    list_filter = ("status",)
    list_select_related = ("employee", "organisation")
    raw_id_fields = ("employee", "reviewed_by")
    readonly_fields = ("end_at", "break_date", "created_at", "updated_at")
    show_full_result_count = False