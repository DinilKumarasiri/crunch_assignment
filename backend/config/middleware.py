import time

from django.db import connection


class QueryCountMiddleware:
    """
    Adds two response headers:
      X-Query-Count       - number of SQL queries the request executed
      X-Response-Time-Ms  - server-side processing time
    Used to spot N+1 problems and in the benchmarks.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        query_count = 0

        def count_queries(execute, sql, params, many, context):
            nonlocal query_count
            query_count += 1
            return execute(sql, params, many, context)

        started = time.perf_counter()
        with connection.execute_wrapper(count_queries):
            response = self.get_response(request)
        response["X-Query-Count"] = str(query_count)
        response["X-Response-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
        return response