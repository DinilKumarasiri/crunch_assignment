from django.urls import path

from .views import BreakPolicyView

urlpatterns = [
    path("policy/", BreakPolicyView.as_view(), name="break-policy"),
]