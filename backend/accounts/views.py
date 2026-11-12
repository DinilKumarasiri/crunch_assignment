from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .mixins import TenantScopedQuerysetMixin
from .models import User
from .permissions import IsManager, IsTenantUser
from .serializers import MeSerializer, TenantTokenObtainPairSerializer, UserListSerializer


class LoginView(TokenObtainPairView):
    """POST username + password → access, refresh, user. (Public endpoint.)"""

    serializer_class = TenantTokenObtainPairSerializer


class MeView(APIView):
    """GET the currently logged-in user's profile."""

    permission_classes = [IsTenantUser]

    def get(self, request):
        return Response(MeSerializer(request.user).data)


class OrganisationUserListView(TenantScopedQuerysetMixin, generics.ListAPIView):
    """Managers: list the users in their own organisation."""

    permission_classes = [IsManager]
    serializer_class = UserListSerializer
    queryset = (
        User.objects
        .only("id", "username", "first_name", "last_name", "role", "organisation_id")
        .order_by("last_name", "first_name", "id")
    )
    filterset_fields = ["role"]  # e.g. /api/users/?role=EMPLOYEE