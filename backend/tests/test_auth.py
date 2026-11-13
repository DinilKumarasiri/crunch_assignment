import pytest
from rest_framework.test import APIClient

from accounts.models import User
from helpers import PASSWORD, client_for

pytestmark = pytest.mark.django_db  # every test in this file may use the database


def login(username, password=PASSWORD):
    return APIClient().post("/api/auth/login/", {"username": username, "password": password}, format="json")


def test_login_returns_tokens_and_profile(employee):
    res = login("eric")
    assert res.status_code == 200
    assert {"access", "refresh"} <= res.data.keys()
    assert res.data["user"]["role"] == "EMPLOYEE"


def test_wrong_password_is_rejected(employee):
    assert login("eric", "wrong").status_code == 401


def test_account_without_organisation_cannot_use_the_api():
    User.objects.create_superuser("admin", "admin@example.com", PASSWORD)
    assert login("admin").status_code == 401


def test_endpoints_require_authentication():
    assert APIClient().get("/api/auth/me/").status_code == 401


def test_jwt_grants_access(employee):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login('eric').data['access']}")
    res = client.get("/api/auth/me/")
    assert res.status_code == 200
    assert res.data["organisation_name"] == "Acme"


def test_tampered_token_is_rejected(employee):
    token = login("eric").data["access"]
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token[:-4]}abcd")
    assert client.get("/api/auth/me/").status_code == 401


def test_manager_lists_only_own_organisation(manager, employee, other_manager):
    res = client_for(manager).get("/api/users/")
    assert {u["username"] for u in res.data["results"]} == {"acme_manager", "eric"}


def test_employee_cannot_list_users(employee):
    assert client_for(employee).get("/api/users/").status_code == 403