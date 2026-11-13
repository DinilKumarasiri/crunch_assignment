import pytest

from accounts.models import User
from helpers import make_org, make_user


@pytest.fixture(autouse=True)
def fast_password_hashing(settings):
    """Real hashing is deliberately slow; tests don't need it to be secure."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def acme(db):
    return make_org("Acme")


@pytest.fixture
def globex(db):
    return make_org("Globex")


@pytest.fixture
def manager(acme):
    return make_user(acme, "acme_manager", User.Role.MANAGER)


@pytest.fixture
def employee(acme):
    return make_user(acme, "eric", first_name="Eric")


@pytest.fixture
def employee2(acme):
    return make_user(acme, "emma", first_name="Emma")


@pytest.fixture
def other_manager(globex):
    return make_user(globex, "globex_manager", User.Role.MANAGER)