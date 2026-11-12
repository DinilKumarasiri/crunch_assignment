from django.urls import path

from .views import BreakPolicyView, MyBreakRequestListCreateView

urlpatterns = [
    path("policy/", BreakPolicyView.as_view(), name="break-policy"),
    path("my/break-requests/", MyBreakRequestListCreateView.as_view(), name="my-break-requests"),
]