from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.mixins import TenantScopedQuerysetMixin
from accounts.permissions import IsEmployee, IsManager, IsTenantUser

from .exceptions import Conflict
from .filters import BreakRequestFilter, StableOrderingFilter
from .models import BreakPolicy, BreakRequest
from .serializers import (
    BreakPolicySerializer,
    BreakRequestCreateSerializer,
    BreakRequestSerializer,
    BulkReviewSerializer,
    QueueItemSerializer,
    ReviewSerializer,
)
from .services import review_break_requests, submit_break_request


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


class MyBreakRequestListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/my/break-requests/  - the employee's own history (?status=PENDING etc.)
    POST /api/my/break-requests/  - submit a new break request
    """

    permission_classes = [IsEmployee]
    serializer_class = BreakRequestSerializer
    filterset_fields = ["status"]

    def get_queryset(self):
        # Scoped to the employee themself. This is stricter than organisation scoping.
        return (
            BreakRequest.objects
            .filter(employee_id=self.request.user.id)
            .order_by("-start_at", "-id")
        )

    def create(self, request, *args, **kwargs):
        input_serializer = BreakRequestCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        break_request, created = submit_break_request(
            employee=request.user,
            start_at=data["start_at"],
            duration_minutes=data["duration_minutes"],
            client_request_id=data.get("client_request_id"),
        )
        return Response(
            BreakRequestSerializer(break_request).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


QUEUE_FIELDS = [
    "id", "break_date", "start_at", "end_at", "duration_minutes", "status",
    "review_note", "reviewed_at", "created_at",
    "employee", "employee__first_name", "employee__last_name", "employee__username",
]


class ApprovalQueueView(TenantScopedQuerysetMixin, generics.ListAPIView):
    """GET /api/break-requests/ - the manager's queue for their organisation."""

    permission_classes = [IsManager]
    serializer_class = QueueItemSerializer
    filter_backends = [DjangoFilterBackend, StableOrderingFilter]
    filterset_class = BreakRequestFilter
    ordering_fields = ["start_at", "created_at", "duration_minutes", "employee__last_name"]
    ordering = ["start_at"]  # default: soonest first
    queryset = BreakRequest.objects.select_related("employee").only(*QUEUE_FIELDS)


class ReviewBreakRequestView(APIView):
    """POST /api/break-requests/<id>/approve/ or /reject/"""

    permission_classes = [IsManager]
    review_action = None  # set in urls.py: "approve" or "reject"

    def post(self, request, pk):
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        _, skipped = review_break_requests(
            manager=request.user,
            ids=[pk],
            approve=self.review_action == "approve",
            note=serializer.validated_data["note"],
        )
        if skipped.get(pk) == "not_found":
            raise NotFound("Break request not found.")
        if pk in skipped:
            raise Conflict(f"This request is {skipped[pk].replace('_', ' ')}.")

        item = BreakRequest.objects.select_related("employee").only(*QUEUE_FIELDS).get(pk=pk)
        return Response(QueueItemSerializer(item).data)


class BulkReviewView(APIView):
    """POST /api/break-requests/bulk-review/  {"ids": [...], "action": "approve"|"reject"}"""

    permission_classes = [IsManager]

    def post(self, request):
        serializer = BulkReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        processed, skipped = review_break_requests(
            manager=request.user,
            ids=data["ids"],
            approve=data["action"] == "approve",
            note=data["note"],
        )
        return Response({
            "processed": processed,
            "skipped": [{"id": pk, "reason": reason} for pk, reason in skipped.items()],
        })