"""
Views of the inbox. The chats and messages are read by `wanps.inbox`; this backend decides
which accounts it may look at: only the connected accounts of the active business.
"""

import logging

import requests
from django.http import Http404
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from wanps.inbox.services import WindowClosed, get_messages, list_conversations, send_message
from wanps.messaging.meta_messaging import MetaAPIError
from wanps.messaging.models import Message
from wanps.whatsapp.client import WhatsAppError

from apps.channels.models import ChannelAccount
from apps.tenants.permissions import HasActiveTenant

from .serializers import (
    ChatMessagesSerializer,
    ConversationSerializer,
    ConversationsQuerySerializer,
    InboxMessageSerializer,
    MessagesQuerySerializer,
    SendMessageSerializer,
)

logger = logging.getLogger(__name__)


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


class ReplyWindowClosed(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The 24-hour window is closed: a reply cannot be sent from here."
    default_code = "window_closed"


class MessageNotDelivered(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = (
        "The message could not be delivered by the channel. "
        "If it keeps failing, ask an admin to check the account."
    )
    default_code = "message_not_delivered"


class SendMessageView(APIView):
    """POST /api/v1/inbox/<channel>/conversations/<contact>/send/ → reply as a person."""

    permission_classes = [IsAuthenticated, HasActiveTenant]

    @extend_schema(
        description=(
            "Sends the text from the account of the chat, in the name of the member. "
            "Sending pauses the bot in that chat until it is resumed."
        ),
        request=SendMessageSerializer,
        responses={
            201: inline_serializer(
                "SentMessageResponse",
                {"success": serializers.BooleanField(), "data": InboxMessageSerializer()},
            ),
            400: OpenApiResponse(description="Empty text, or the account is missing or malformed."),
            404: OpenApiResponse(
                description="The account is not one of the business's on this channel."
            ),
            409: OpenApiResponse(description="The 24-hour window is closed."),
            502: OpenApiResponse(description="The channel could not deliver the message."),
        },
    )
    def post(self, request, channel, contact_id):
        body = SendMessageSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        link = pick_link(business_links(request, channel), body.validated_data["account"])
        try:
            sent = send_message(
                TenantInbox([link.account]),
                contact_id,
                account=link.account,
                text=body.validated_data["text"],
                sent_by=request.user.full_name,
                channel=channel,
            )
        except WindowClosed:
            raise ReplyWindowClosed from None
        except (WhatsAppError, MetaAPIError, requests.RequestException) as exc:
            # Only the kind of error: its text can carry the URL with the access token
            logger.warning(
                "Could not send a %s message from account %s: %s",
                channel,
                link.id,
                type(exc).__name__,
            )
            raise MessageNotDelivered from None
        return Response(
            {"success": True, "data": InboxMessageSerializer(sent).data},
            status=status.HTTP_201_CREATED,
        )
