from rest_framework.pagination import CursorPagination, PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class NewestFirstCursorPagination(CursorPagination):
    """Keyset pagination, newest first. Constant speed at any depth, no COUNT query."""

    ordering = "-start_at"
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100