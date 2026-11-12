import logging

from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    """DRF's default handler, plus: database integrity errors become 409, not 500."""
    response = exception_handler(exc, context)
    if response is None and isinstance(exc, IntegrityError):
        logger.warning("Unhandled IntegrityError in %s: %s", context.get("view"), exc)
        return Response(
            {"detail": "The request conflicts with existing data."},
            status=status.HTTP_409_CONFLICT,
        )
    return response

    