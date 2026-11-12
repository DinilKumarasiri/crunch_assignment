from datetime import timedelta

from django.contrib.postgres.fields import RangeBoundary
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.db.models import Count, Sum
from rest_framework.exceptions import ValidationError

from config.pagination import NewestFirstCursorPagination


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

from .models import BreakPolicy, BreakRequest, TsTzRange
from .serializers import (
    BreakPolicySerializer,
    BreakRequestCreateSerializer,
    BreakRequestSerializer,
    BulkReviewSerializer,
    DateRangeQuerySerializer,
    OnBreakQuerySerializer,
    QueueItemSerializer,
    ReviewSerializer,
)
from .services import local_day_bounds, review_break_requests, submit_break_request

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

REVIEW_ERRORS = {
    "already_approved": "This request has already been approved.",
    "already_rejected": "This request has already been rejected.",
    "capacity_reached": "Approving this would exceed the maximum number of "
                        "employees allowed on break at the same time.",
}

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
            raise Conflict(REVIEW_ERRORS[skipped[pk]])

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

def approved_breaks_for(user):
    """Approved breaks of the user's organisation: the base of every Screen 4 query."""
    return BreakRequest.objects.filter(
        organisation_id=user.organisation_id,
        status=BreakRequest.Status.APPROVED,
    )


class BreakRegisterView(TenantScopedQuerysetMixin, generics.ListAPIView):
    """GET /api/register/ - approved breaks, newest first, keyset-paginated."""

    permission_classes = [IsManager]
    serializer_class = QueueItemSerializer
    pagination_class = NewestFirstCursorPagination
    filter_backends = [DjangoFilterBackend]  # no OrderingFilter: the order is fixed
    filterset_class = BreakRequestFilter
    queryset = (
        BreakRequest.objects
        .filter(status=BreakRequest.Status.APPROVED)
        .select_related("employee")
        .only(*QUEUE_FIELDS)
    )


class RegisterSummaryView(APIView):
    """GET /api/register/summary/ - totals for the same filters as the register."""

    permission_classes = [IsManager]

    def get(self, request):
        filterset = BreakRequestFilter(
            request.query_params, queryset=approved_breaks_for(request.user), request=request
        )
        if not filterset.is_valid():
            raise ValidationError(filterset.errors)

        # ONE query returns all three numbers.
        totals = filterset.qs.aggregate(
            total_breaks=Count("id"),
            total_minutes=Sum("duration_minutes"),
            unique_employees=Count("employee_id", distinct=True),
        )
        minutes = totals["total_minutes"] or 0
        return Response({
            "total_breaks": totals["total_breaks"],
            "total_minutes": minutes,
            "total_hours": round(minutes / 60, 2),
            "unique_employees": totals["unique_employees"],
        })


class OnBreakView(APIView):
    """GET /api/register/on-break/?at=2026-11-20T10:30 - who is on break at that moment."""

    permission_classes = [IsManager]
    MAX_RESULTS = 500

    def get(self, request):
        params = OnBreakQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        at = params.validated_data["at"]

        breaks = list(
            approved_breaks_for(request.user)
            # Same expression as the GiST index, so Postgres can use it.
            .annotate(period=TsTzRange("start_at", "end_at", RangeBoundary()))
            .filter(period__overlap=DateTimeTZRange(at, at, "[]"))  # period contains `at`
            .select_related("employee")
            .only(*QUEUE_FIELDS)
            .order_by("start_at", "id")[: self.MAX_RESULTS]
        )
        return Response({
            "at": at,
            "count": len(breaks),
            "breaks": QueueItemSerializer(breaks, many=True).data,
        })


class DailyStatsView(APIView):
    """GET /api/register/daily-stats/?date_from=&date_to= - one row per day."""

    permission_classes = [IsManager]

    def get(self, request):
        params = DateRangeQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        date_from = params.validated_data["date_from"]
        date_to = params.validated_data["date_to"]
        range_start, _ = local_day_bounds(date_from)
        _, range_end = local_day_bounds(date_to)

        # GROUP BY break_date, computed entirely in Postgres.
        rows = (
            approved_breaks_for(request.user)
            .filter(start_at__gte=range_start, start_at__lt=range_end)
            .values("break_date")
            .annotate(
                breaks=Count("id"),
                total_minutes=Sum("duration_minutes"),
                unique_employees=Count("employee_id", distinct=True),
            )
            .order_by("break_date")
        )
        by_day = {row["break_date"]: row for row in rows}

        # Fill in days with no breaks, so charts have no gaps.
        days, day = [], date_from
        while day <= date_to:
            row = by_day.get(day)
            days.append({
                "date": day,
                "breaks": row["breaks"] if row else 0,
                "total_minutes": row["total_minutes"] if row else 0,
                "unique_employees": row["unique_employees"] if row else 0,
            })
            day += timedelta(days=1)

        return Response({"date_from": date_from, "date_to": date_to, "days": days})