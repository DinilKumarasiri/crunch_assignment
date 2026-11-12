from rest_framework import status
from rest_framework.exceptions import APIException


class Conflict(APIException):
    """HTTP 409: the request conflicts with the current state of the data."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "The resource was changed by someone else. Reload and try again."
    default_code = "conflict"
    