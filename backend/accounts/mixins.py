class TenantScopedQuerysetMixin:
    """
    Restricts a view's queryset to the requesting user's organisation.

    Any view that inherits this CANNOT accidentally return another tenant's
    data: list endpoints only see their own org's rows, and detail endpoints
    return 404 for other orgs' objects (they are simply not in the queryset).
    """

    tenant_field = "organisation"  # override if the FK has a different name

    def get_queryset(self):
        queryset = super().get_queryset()
        organisation_id = getattr(self.request.user, "organisation_id", None)
        if organisation_id is None:
            return queryset.none()  # fail closed: no organisation → no data
        return queryset.filter(**{f"{self.tenant_field}_id": organisation_id})