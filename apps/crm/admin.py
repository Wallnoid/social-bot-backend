"""
Admin for the crm app: the Social Bot team sees the contacts of the businesses, read only.
"""

from django.contrib import admin

from .models import Contact


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ["external_id", "tenant", "account", "created_at"]
    list_filter = ["account__channel"]
    search_fields = ["external_id", "tenant__name"]
    list_select_related = ["tenant", "account"]

    # Contacts are created by themselves from the chats; the businesses work them from the app
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
