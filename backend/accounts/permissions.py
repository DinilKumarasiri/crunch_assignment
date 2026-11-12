from rest_framework.permissions import BasePermission

from .models import User


class IsTenantUser(BasePermission):
    """Logged in AND belongs to an organisation (excludes site superusers)."""

    message = "This account is not linked to an organisation."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.organisation_id)


class IsManager(IsTenantUser):
    message = "Only managers can perform this action."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.role == User.Role.MANAGER


class IsEmployee(IsTenantUser):
    message = "Only employees can perform this action."

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.role == User.Role.EMPLOYEE