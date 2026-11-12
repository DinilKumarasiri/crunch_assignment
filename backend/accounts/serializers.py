from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class MeSerializer(serializers.ModelSerializer):
    organisation_name = serializers.CharField(source="organisation.name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "role",
                  "organisation_id", "organisation_name"]


class UserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "role"]


class TenantTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login: returns access + refresh tokens and the user's profile."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Extra claims, for the React UI's convenience only.
        # The server NEVER trusts these for authorisation: it re-loads
        # the user from the database on every request.
        token["role"] = user.role
        token["organisation_id"] = user.organisation_id
        return token

    def validate(self, attrs):
        data = super().validate(attrs)  # checks username/password → 401 if wrong
        if not self.user.organisation_id:
            raise AuthenticationFailed("This account is not linked to an organisation.")
        data["user"] = MeSerializer(self.user).data
        return data