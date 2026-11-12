from django.urls import path

from .views import (
    ApprovalQueueView,
    BreakPolicyView,
    BulkReviewView,
    MyBreakRequestListCreateView,
    ReviewBreakRequestView,
)

urlpatterns = [
    path("policy/", BreakPolicyView.as_view(), name="break-policy"),
    path("my/break-requests/", MyBreakRequestListCreateView.as_view(), name="my-break-requests"),
    path("break-requests/", ApprovalQueueView.as_view(), name="approval-queue"),
    path("break-requests/bulk-review/", BulkReviewView.as_view(), name="bulk-review"),
    path("break-requests/<int:pk>/approve/",
         ReviewBreakRequestView.as_view(review_action="approve"), name="approve"),
    path("break-requests/<int:pk>/reject/",
         ReviewBreakRequestView.as_view(review_action="reject"), name="reject"),
]