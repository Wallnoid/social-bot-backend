"""
Views of the inbox. The chats and messages are read by `wanps.inbox`; this backend decides
which accounts it may look at: only the connected accounts of the active business.
"""

from django.http import Http404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from wanps.inbox.services import get_messages, list_conversations
from wanps.messaging.models import Message

from apps.channels.models import ChannelAccount
from apps.tenants.permissions import HasActiveTenant

from .serializers import (
    ChatMessagesSerializer,
    ConversationSerializer,
    ConversationsQuerySerializer,
    MessagesQuerySerializer,
)


class TenantInbox:
    """
    What `wanps.inbox` asks of a connection: the accounts it can see and their messages.

    It is built on each request from the active business, so there are no stored keys to
    keep in sync. With no accounts it reads nothing: a real connection without accounts
    would read the messages that have no account (single-business mode).
    """

    def __init__(self, accounts):
        self._accounts = accounts

    def scope_accounts(self):
        return self._accounts

    def messages(self, account=None):
        messages = Message.objects.filter(account__in=self._accounts)
        return messages.filter(account=account) if account is not None else messages


def business_links(request, channel):
    """The connected accounts of the active business on one channel."""
    return list(
        ChannelAccount.objects.filter(tenant=request.tenant, account__channel=channel)
        .select_related("account")
        .order_by("created_at")
    )


def pick_link(links, account_id):
    """The account with that id. One that is not among `links` is simply not found."""
    for link in links:
        if link.id == account_id:
            return link
    raise Http404


def account_of(link):
    """How the inbox names an account: with the id the list of accounts shows."""
    return {"id": link.id, "name": link.account.name, "channel": link.account.channel}


class ConversationListView(APIView):
    """GET /api/v1/inbox/<channel>/conversations/ → the chats of the business on a channel."""

    permission_classes = [IsAuthenticated, HasActiveTenant]

    @extend_schema(
        parameters=[ConversationsQuerySerializer],
        responses={
            200: inline_serializer(
                "ConversationListResponse",
                {
                    "success": serializers.BooleanField(),
                    "data": inline_serializer(
                        "ConversationList",
                        {
                            "conversations": ConversationSerializer(many=True),
                            "has_more": serializers.BooleanField(),
                        },
                    ),
                },
            )
        },
    )
    def get(self, request, channel):
        query = ConversationsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        links = business_links(request, channel)
        if "account" in query.validated_data:
            links = [pick_link(links, query.validated_data["account"])]
        by_account = {link.account_id: link for link in links}
        found = list_conversations(
            TenantInbox([link.account for link in links]),
            channel=channel,
            limit=query.validated_data["limit"],
            offset=query.validated_data["offset"],
        )
        conversations = [
            {**chat, "account": account_of(by_account[chat["account"]["id"]])}
            for chat in found["conversations"]
        ]
        data = {
            "conversations": ConversationSerializer(conversations, many=True).data,
            "has_more": found["has_more"],
        }
        return Response({"success": True, "data": data})


class MessageListView(APIView):
    """GET /api/v1/inbox/<channel>/conversations/<contact>/messages/ → the messages of a chat."""

    permission_classes = [IsAuthenticated, HasActiveTenant]

    @extend_schema(
        parameters=[MessagesQuerySerializer],
        responses={
            200: inline_serializer(
                "ChatMessagesResponse",
                {"success": serializers.BooleanField(), "data": ChatMessagesSerializer()},
            )
        },
    )
    def get(self, request, channel, contact_id):
        query = MessagesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        link = pick_link(business_links(request, channel), query.validated_data["account"])
        found = get_messages(
            TenantInbox([link.account]),
            contact_id,
            account=link.account,
            channel=channel,
            limit=query.validated_data["limit"],
            before=query.validated_data.get("before"),
        )
        data = ChatMessagesSerializer({**found, "account": account_of(link)}).data
        return Response({"success": True, "data": data})
