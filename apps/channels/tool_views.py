"""
Views of the tools of the bot of an account, for the admins of the business.
"""

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.tenants.permissions import HasActiveTenant, IsTenantAdmin

from .models import ChannelAccount, ChannelTool
from .tool_serializers import MAX_TOOLS_PER_ACCOUNT, ChannelToolSerializer

AI_PROVIDER_WARNING = (
    "What the endpoint answers is sent to the AI provider so the bot can use it. Do not point a "
    "tool at an endpoint whose answer holds data that must not leave the business."
)


def one_tool_response(name):
    return inline_serializer(
        name, {"success": serializers.BooleanField(), "data": ChannelToolSerializer()}
    )


class ToolsView(generics.GenericAPIView):
    """What the views of the tools share: admins only, and only the accounts of the business."""

    serializer_class = ChannelToolSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, IsTenantAdmin]

    def get_link(self, request, account_id, lock=False):
        """The account of the business: another business's (or a disconnected one) is not found."""
        links = ChannelAccount.objects.filter(tenant=request.tenant).select_related("account")
        if lock:
            links = links.select_for_update()
        return get_object_or_404(links, pk=account_id)

    def get_tool(self, link, tool_id, lock=False):
        tools = ChannelTool.objects.filter(account=link.account)
        if lock:
            tools = tools.select_for_update()
        return get_object_or_404(tools, pk=tool_id)


class ChannelToolListView(ToolsView):
    """
    GET /api/v1/channels/accounts/<id>/tools/ → the tools of the bot of an account.
    POST /api/v1/channels/accounts/<id>/tools/ → add one.
    """

    @extend_schema(
        operation_id="v1_channels_accounts_tools_list",
        responses={
            200: inline_serializer(
                "ChannelToolListResponse",
                {
                    "success": serializers.BooleanField(),
                    "data": ChannelToolSerializer(many=True),
                },
            )
        },
    )
    def get(self, request, account_id):
        link = self.get_link(request, account_id)
        tools = ChannelTool.objects.filter(account=link.account)
        data = ChannelToolSerializer(tools, many=True, context={"account": link.account}).data
        return Response({"success": True, "data": data})

    @extend_schema(
        description="Adds a tool to the bot of the account. " + AI_PROVIDER_WARNING,
        request=ChannelToolSerializer,
        responses={201: one_tool_response("ChannelToolCreatedResponse")},
    )
    def post(self, request, account_id):
        with transaction.atomic():
            # Locked, so two requests never go over the limit together or repeat a name
            link = self.get_link(request, account_id, lock=True)
            serializer = ChannelToolSerializer(data=request.data, context={"account": link.account})
            serializer.is_valid(raise_exception=True)
            if ChannelTool.objects.filter(account=link.account).count() >= MAX_TOOLS_PER_ACCOUNT:
                raise ValidationError(
                    {"non_field_errors": [f"An account has at most {MAX_TOOLS_PER_ACCOUNT} tools."]}
                )
            tool = serializer.save(account=link.account)
        return Response(
            {"success": True, "data": ChannelToolSerializer(tool).data},
            status=status.HTTP_201_CREATED,
        )


class ChannelToolDetailView(ToolsView):
    """
    GET, PATCH and DELETE /api/v1/channels/accounts/<id>/tools/<tool_id>/ → read, edit or delete
    a tool of the bot of an account.
    """

    @extend_schema(responses={200: one_tool_response("ChannelToolResponse")})
    def get(self, request, account_id, tool_id):
        link = self.get_link(request, account_id)
        tool = self.get_tool(link, tool_id)
        return Response({"success": True, "data": ChannelToolSerializer(tool).data})

    @extend_schema(
        description="Edits a tool. The key is kept unless a new one is sent. "
        + AI_PROVIDER_WARNING,
        responses={200: one_tool_response("ChannelToolEditedResponse")},
    )
    def patch(self, request, account_id, tool_id):
        with transaction.atomic():
            # The account first, like when creating: renames and creations never run together
            link = self.get_link(request, account_id, lock=True)
            tool = self.get_tool(link, tool_id, lock=True)
            serializer = ChannelToolSerializer(
                tool, data=request.data, partial=True, context={"account": link.account}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response({"success": True, "data": ChannelToolSerializer(tool).data})

    @extend_schema(
        responses={
            200: inline_serializer(
                "ChannelToolDeletedResponse",
                {"success": serializers.BooleanField(), "message": serializers.CharField()},
            )
        }
    )
    def delete(self, request, account_id, tool_id):
        with transaction.atomic():
            link = self.get_link(request, account_id, lock=True)
            self.get_tool(link, tool_id, lock=True).soft_delete()
        return Response({"success": True, "message": "Tool deleted."})
