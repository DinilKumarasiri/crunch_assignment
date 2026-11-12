from django.db import transaction
from rest_framework import generics
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response

from accounts.permissions import IsManager, IsTenantUser

from .exceptions import Conflict
from .models import BreakPolicy
from .serializers import BreakPolicySerializer


class BreakPolicyView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/policy/  - any tenant user reads their organisation's policy.
    PUT  /api/policy/  - managers replace it (optimistic locking via `version`).
    """

    serializer_class = BreakPolicySerializer
    http_method_names = ["get", "put", "head", "options"]  # no PATCH, no DELETE

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:  # GET, HEAD, OPTIONS
            return [IsTenantUser()]
        return [IsManager()]

    def get_object(self):
        # The organisation comes from the token, never from the URL.
        policy, _ = (
            BreakPolicy.objects.select_related("updated_by")
            .get_or_create(organisation_id=self.request.user.organisation_id)
        )
        return policy

    def update(self, request, *args, **kwargs):
        self.get_object()  # make sure a policy row exists before locking it

        with transaction.atomic():
            # Lock the row: a second concurrent PUT waits here until we commit.
            policy = BreakPolicy.objects.select_for_update().get(
                organisation_id=request.user.organisation_id
            )

            serializer = self.get_serializer(policy, data=request.data)
            serializer.is_valid(raise_exception=True)

            submitted_version = serializer.validated_data.pop("version")
            if submitted_version != policy.version:
                raise Conflict(
                    "This policy was changed by someone else. Reload to see the latest values."
                )

            serializer.save(updated_by=request.user, version=policy.version + 1)

        return Response(serializer.data)