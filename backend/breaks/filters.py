from django.db.models import Q
from django_filters import rest_framework as filters
from rest_framework.filters import OrderingFilter

from accounts.models import User

from .models import BreakRequest
from .services import local_day_bounds


class BreakRequestFilter(filters.FilterSet):
    status = filters.ChoiceFilter(choices=BreakRequest.Status.choices)
    employee = filters.NumberFilter(field_name="employee_id")
    date_from = filters.DateFilter(method="filter_date_from")
    date_to = filters.DateFilter(method="filter_date_to")
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = BreakRequest
        fields = ["status", "employee", "date_from", "date_to", "search"]

    # Dates become start_at ranges so the (organisation, status, start_at) index is used.
    def filter_date_from(self, queryset, name, value):
        start, _ = local_day_bounds(value)
        return queryset.filter(start_at__gte=start)

    def filter_date_to(self, queryset, name, value):
        _, end = local_day_bounds(value)
        return queryset.filter(start_at__lt=end)

    def filter_search(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        # Find matching employees first (trigram indexes), then their requests.
        matching_employees = User.objects.filter(
            Q(first_name__icontains=value)
            | Q(last_name__icontains=value)
            | Q(username__icontains=value),
            organisation_id=self.request.user.organisation_id,
        ).values("id")
        return queryset.filter(employee_id__in=matching_employees)


class StableOrderingFilter(OrderingFilter):
    """OrderingFilter that always adds `id` as a tie-breaker, so pagination is stable."""

    def get_ordering(self, request, queryset, view):
        ordering = list(super().get_ordering(request, queryset, view) or [])
        if not any(field.lstrip("-") == "id" for field in ordering):
            descending = bool(ordering) and ordering[0].startswith("-")
            ordering.append("-id" if descending else "id")
        return ordering
        