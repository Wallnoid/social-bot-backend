"""
Admin configuration for the channels app.

The Social Bot team marks here which Meta App is the shared one. The Meta Apps
themselves (and their secrets) are managed in wanps-core's Messaging admin.
"""

from django.contrib import admin

from .models import SharedMetaApp


@admin.register(SharedMetaApp)
class SharedMetaAppAdmin(admin.ModelAdmin):
    list_display = ["app", "created_at"]
