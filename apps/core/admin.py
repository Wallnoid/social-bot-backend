"""
Admin helpers shared by the apps.
"""

from django.contrib import admin


class SoftDeleteAdminMixin:
    """
    Deleting from the admin is a soft delete: nothing leaves the database, so there is no cascade
    to show and nothing protected that could stop it (`QuerySet.delete()` would remove the rows
    for real, with no way back).
    """

    def get_deleted_objects(self, objs, request):
        objs = list(objs)
        names = {self.model._meta.verbose_name_plural: len(objs)}
        return [str(obj) for obj in objs], names, set(), []

    def delete_queryset(self, request, queryset):
        # A row deleted before keeps the date it was really deleted
        for obj in queryset.filter(is_deleted=False):
            obj.delete()


class DeletionStateFilter(admin.SimpleListFilter):
    """The active rows by default; the deleted ones, or all of them, on request."""

    title = "state"
    parameter_name = "state"

    def lookups(self, request, model_admin):
        return [("deleted", "Deleted"), ("all", "All")]

    def choices(self, changelist):
        yield {
            "selected": self.value() is None,
            "query_string": changelist.get_query_string(remove=[self.parameter_name]),
            "display": "Active",
        }
        for value, title in self.lookup_choices:
            yield {
                "selected": self.value() == value,
                "query_string": changelist.get_query_string({self.parameter_name: value}),
                "display": title,
            }

    def queryset(self, request, queryset):
        if self.value() == "deleted":
            return queryset.filter(is_deleted=True)
        if self.value() == "all":
            return queryset
        return queryset.filter(is_deleted=False)
