from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"  # client may ask for ?page_size=50 ...
    max_page_size = 100                  # ... but never more than 100