from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Organisation, User


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "created_at")
    search_fields = ("name",)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Organisation", {"fields": ("organisation", "role")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Organisation", {"fields": ("organisation", "role")}),
    )
    list_display = ("username", "first_name", "last_name", "organisation", "role", "is_staff")
    list_filter = ("role", "is_staff")
    list_select_related = ("organisation",)  # JOIN once instead of 1 query per row
    show_full_result_count = False           # skip an expensive COUNT(*) on big tables