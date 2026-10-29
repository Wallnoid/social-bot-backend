"""
Custom pagination classes for the API.
"""

from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """
    Standard pagination with configurable page size.

    Query params:
        - page: Page number (default: 1)
        - page_size: Number of results per page (default: 20, max: 100)
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class LargeResultsSetPagination(PageNumberPagination):
    """
    Pagination for endpoints that return large datasets.
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500


class SmallResultsSetPagination(PageNumberPagination):
    """
    Pagination for endpoints that return small datasets (e.g., dropdowns).
    """

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50
