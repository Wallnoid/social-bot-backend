"""
Views of the inbox. The chats and messages are read by `wanps.inbox`; this backend decides
which accounts it may look at: only the connected accounts of the active business.
"""

import logging

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404, HttpResponse
from django.utils import timezone
from django.utils.http import content_disposition_header
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from wanps.inbox.services import (
    WindowClosed,
    get_messages,
    list_conversations,
    send_message,
    set_bot_paused,
)
from wanps.messaging.attachments import get_attachment
from wanps.messaging.meta_messaging import MetaAPIError
from wanps.messaging.models import Message
from wanps.whatsapp.client import WhatsAppError, list_templates

from apps.channels.models import ChannelAccount, ClientStrikes
from apps.channels.signals import client_block_changed
from apps.tenants.permissions import HasActiveTenant, IsSupervisorOrAdmin

from .files import open_message_file
from .realtime import issue_ticket
from .serializers import (
    BotStateSerializer,
    ChatMessagesSerializer,
    ConversationSerializer,
    ConversationsQuerySerializer,
    FileQuerySerializer,
    InboxMessageSerializer,
    MessagesQuerySerializer,
    PauseBotSerializer,
    SendMessageSerializer,
    TemplateSerializer,
    TemplatesQuerySerializer,
    UnblockSerializer,
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


def chat_scope(request, channel, account_id):
    """
    The account of a chat, and what `wanps.inbox` may read through it. Every action on a
    chat starts here, so the business scope is applied in a single place.
    """
    link = pick_link(business_links(request, channel), account_id)
    return link, TenantInbox([link.account])


def account_of(link):
    """How the inbox names an account: with the id the list of accounts shows."""
    return {"id": link.id, "name": link.account.name, "channel": link.account.channel}


def mark_files(messages, readable):
    """Add to each message the file it carries (or None). Only messages the business can read."""
    stored = readable.filter(
        pk__in=[message["id"] for message in messages], direction=Message.DIRECTION_IN
    )
    attachments = {message.pk: get_attachment(message) for message in stored}
    for message in messages:
        attachment = attachments.get(message["id"])
        message["file"] = (
            {
                "kind": attachment.kind,
                "mime_type": attachment.mime_type,
                "filename": attachment.filename,
            }
            if attachment
            else None
        )


def blocked_untils(chats):
    """Until when the bot does not answer each client of the chats (only the blocks still on)."""
    rows = ClientStrikes.objects.filter(
        account_id__in={chat["account"]["id"] for chat in chats},
        contact_id__in={chat["contact_id"] for chat in chats},
        blocked_until__gt=timezone.now(),
    )
    return {(row.account_id, row.contact_id): row.blocked_until for row in rows}


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
        blocked = blocked_untils(found["conversations"])
        conversations = [
            {
                **chat,
                "bot_blocked_until": blocked.get((chat["account"]["id"], chat["contact_id"])),
                "contact_name": chat["contact_name"] or GENERIC_NAMES.get(channel, ""),
                "account": account_of(by_account[chat["account"]["id"]]),
            }
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
        link, inbox = chat_scope(request, channel, query.validated_data["account"])
        found = get_messages(
            inbox,
            contact_id,
            account=link.account,
            channel=channel,
            limit=query.validated_data["limit"],
            before=query.validated_data.get("before"),
        )
        mark_files(found["messages"], inbox.messages(link.account))
        blocked_until = (
            ClientStrikes.objects.filter(
                account=link.account, contact_id=contact_id, blocked_until__gt=timezone.now()
            )
            .values_list("blocked_until", flat=True)
            .first()
        )
        data = ChatMessagesSerializer(
            {**found, "account": account_of(link), "bot_blocked_until": blocked_until}
        ).data
        return Response({"success": True, "data": data})


# Types a browser can show without running anything (an SVG can carry a script)
INLINE_TYPES = ("image/", "audio/", "video/")
NOT_INLINE = ("image/svg+xml",)


MEGABYTE = 1024 * 1024

# What a chat shows while Meta has not given the name of the client (shown, never saved)
GENERIC_NAMES = {"messenger": "Messenger user", "instagram": "Instagram user"}


class MessageFileView(APIView):
    """GET .../messages/<id>/file/ → the file a message carries, as its own bytes."""

    permission_classes = [IsAuthenticated, HasActiveTenant]

    @extend_schema(
        description=(
            "The file a message carries (its marker is the `file` field of the message), as its "
            "own bytes: there is no public address for it, so ask for it here with "
            "`Authorization` and `X-Tenant-ID` and show the answer as a blob. The first time it is "
            "opened the backend downloads it from Meta and saves it on the server; after that it "
            "is served from there, without calling Meta. Saved files are deleted after "
            f"{settings.MESSAGE_FILE_RETENTION_DAYS} days (they are asked from Meta again if "
            f"opened later) and nothing over {settings.MESSAGE_FILE_MAX_BYTES // MEGABYTE} MB "
            "is saved. "
            "Pictures, sounds and videos can be shown in the page; anything else comes as a "
            "download, with its file name."
        ),
        parameters=[FileQuerySerializer],
        responses={
            (200, "*/*"): OpenApiResponse(
                response=OpenApiTypes.BINARY, description="The bytes of the file."
            ),
            404: OpenApiResponse(description="No such message, or it carries no file."),
            410: OpenApiResponse(description="Meta does not keep the file any more."),
            413: OpenApiResponse(description="The file is bigger than the cap and is not saved."),
            502: OpenApiResponse(description="The file could not be fetched right now. Try again."),
        },
    )
    def get(self, request, channel, contact_id, message_id):
        query = FileQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        link, inbox = chat_scope(request, channel, query.validated_data["account"])
        message = (
            inbox.messages(link.account)
            .filter(
                pk=message_id,
                contact_id=contact_id,
                channel=channel,
                direction=Message.DIRECTION_IN,
            )
            .first()
        )
        attachment = get_attachment(message) if message else None
        if attachment is None:
            raise Http404
        content, mime_type = open_message_file(message)
        response = HttpResponse(content, content_type=mime_type)
        # The type comes from the client's side of Meta, so the browser must not guess another
        # one, and anything that is not a picture, a sound or a video is downloaded, not opened
        response["X-Content-Type-Options"] = "nosniff"
        if not mime_type.startswith(INLINE_TYPES) or mime_type in NOT_INLINE:
            response["Content-Disposition"] = content_disposition_header(
                True, attachment.filename or None
            )
        return response


class ConnectionTicketView(APIView):
    """POST /api/v1/inbox/ws-ticket/ → a permit to open the permanent connection of the inbox."""

    permission_classes = [IsAuthenticated, HasActiveTenant]

    @extend_schema(
        request=None,
        responses={
            201: inline_serializer(
                "ConnectionTicketResponse",
                {
                    "success": serializers.BooleanField(),
                    "data": inline_serializer(
                        "ConnectionTicket",
                        {
                            "ticket": serializers.CharField(),
                            "expires_in": serializers.IntegerField(
                                help_text="Seconds the permit can be used."
                            ),
                        },
                    ),
                },
            )
        },
    )
    def post(self, request):
        ticket = issue_ticket(request.user.pk, request.tenant.pk)
        data = {"ticket": ticket, "expires_in": settings.WS_TICKET_TIMEOUT}
        return Response({"success": True, "data": data}, status=status.HTTP_201_CREATED)


class TemplatesUnavailable(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = (
        "The channel could not give the templates. "
        "If it keeps failing, ask an admin to check the account."
    )
    default_code = "templates_unavailable"


def templates_of(link):
    """The templates of an account that can be sent, with the errors in the API format."""
    try:
        return list_templates(link.account)
    except ImproperlyConfigured:
        raise ValidationError(
            {
                "account": "This account has no WhatsApp Business account id, "
                "so its templates cannot be used."
            }
        ) from None
    except (WhatsAppError, requests.RequestException) as exc:
        # Only the kind of error: its text can carry the address with the access token
        logger.warning(
            "Could not list the templates of account %s: %s (status %s)",
            link.id,
            type(exc).__name__,
            getattr(exc, "status_code", None),
        )
        raise TemplatesUnavailable from None


def check_template(link, inbox, contact_id, template):
    """
    A template skips the 24-hour window and the check of the chat, so both are made here: it is
    only for a client who already wrote to this account, and for a template that can be sent.
    """
    wrote = inbox.messages(link.account).filter(
        contact_id=contact_id, channel="whatsapp", direction=Message.DIRECTION_IN
    )
    if not wrote.exists():
        raise Http404
    listed = next(
        (
            t
            for t in templates_of(link)
            if (t["name"], t["language"]) == (template["name"], template["language"])
        ),
        None,
    )
    if listed is None:
        raise ValidationError(
            {
                "template": "That template does not exist, is not approved or cannot be sent from here."
            }
        )
    if listed["variables"] != len(template["params"]):
        raise ValidationError(
            {
                "template": f"This template takes {listed['variables']} values "
                f"and {len(template['params'])} were given."
            }
        )


class ReplyWindowClosed(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The 24-hour window is closed: a reply cannot be sent from here."
    default_code = "window_closed"


class HumanAgentExpired(ReplyWindowClosed):
    """Even the human-agent option cannot help: the client's last message is too old."""

    default_code = "human_agent_expired"


USE_HUMAN_AGENT = (
    "The 24-hour window is closed: reply as a person with the human-agent option "
    "(up to 7 days after the client's last message)."
)
# Also the case of a contact that never wrote: there is no message of the client either
HUMAN_AGENT_EXPIRED = (
    "There is no message from the client in the last 7 days: it can no longer be answered."
)


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
            "Sends the text, or on WhatsApp an approved template, from the account of the chat, "
            "in the name of the member. A template can go out of the 24-hour window, but only to "
            "a client who already wrote to the account. Sending pauses the bot in that chat until "
            "it is resumed."
        ),
        request=SendMessageSerializer,
        responses={
            201: inline_serializer(
                "SentMessageResponse",
                {"success": serializers.BooleanField(), "data": InboxMessageSerializer()},
            ),
            400: OpenApiResponse(
                description="Empty text, both text and template or neither, the account is "
                "missing or malformed, the human-agent option is used on WhatsApp, or the template "
                "does not exist, is not approved or takes another number of values."
            ),
            404: OpenApiResponse(
                description="The account is not one of the business's on this channel."
            ),
            409: OpenApiResponse(
                description="The 24-hour window is closed. The `code` of the error tells the "
                "case: `window_closed` (on WhatsApp, a template is the way out; on Messenger and "
                "Instagram, use the human-agent option) or `human_agent_expired` (the option was "
                "used and the client's last message is more than 7 days old, or there is none: "
                "nothing can be sent)."
            ),
            502: OpenApiResponse(description="The channel could not deliver the message."),
        },
    )
    def post(self, request, channel, contact_id):
        body = SendMessageSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        human_agent = body.validated_data["human_agent"]
        template = body.validated_data.get("template")
        if human_agent and channel == "whatsapp":
            raise ValidationError(
                {"human_agent": "This option only exists on Messenger and Instagram."}
            )
        if template and channel != "whatsapp":
            raise ValidationError({"template": "Templates only exist on WhatsApp."})
        link, inbox = chat_scope(request, channel, body.validated_data["account"])
        if template:
            check_template(link, inbox, contact_id, template)
        try:
            sent = send_message(
                inbox,
                contact_id,
                account=link.account,
                text=body.validated_data.get("text", ""),
                template=dict(template) if template else None,
                human_agent=human_agent,
                sent_by=request.user.full_name,
                # The pause below ends by itself, instead of the one that lasts until resumed
                pause_bot=False,
                channel=channel,
            )
        except WindowClosed:
            if channel == "whatsapp":
                raise ReplyWindowClosed from None
            # On these channels the option decides what is left: if it was already used,
            # the 7 days are over; if not, it can still be used
            if human_agent:
                raise HumanAgentExpired(HUMAN_AGENT_EXPIRED) from None
            raise ReplyWindowClosed(USE_HUMAN_AGENT) from None
        except (WhatsAppError, MetaAPIError, requests.RequestException) as exc:
            # Only the kind of error: its text can carry the URL with the access token
            logger.warning(
                "Could not send a %s message from account %s: %s (status %s)",
                channel,
                link.id,
                type(exc).__name__,
                getattr(exc, "status_code", None),
            )
            raise MessageNotDelivered from None
        # A person is talking: the bot waits, and takes the chat back after an hour without them
        set_bot_paused(
            inbox,
            contact_id,
            link.account,
            paused=True,
            minutes=settings.BOT_RESUME_AFTER_MINUTES,
            paused_by=request.user.full_name,
            channel=channel,
        )
        return Response(
            {"success": True, "data": InboxMessageSerializer(sent).data},
            status=status.HTTP_201_CREATED,
        )


class BotView(APIView):
    """POST /api/v1/inbox/<channel>/conversations/<contact>/bot/ → pause or resume the bot."""

    permission_classes = [IsAuthenticated, HasActiveTenant]

    @extend_schema(
        description=(
            "Pauses the bot in the chat, for some minutes (up to one week) or until it is "
            "resumed, or resumes it. The chat shows who paused it and until when."
        ),
        request=PauseBotSerializer,
        responses={
            200: inline_serializer(
                "BotStateResponse",
                {"success": serializers.BooleanField(), "data": BotStateSerializer()},
            ),
            400: OpenApiResponse(description="The time or the body is not valid."),
            404: OpenApiResponse(
                description="The account is not one of the business's on this channel, or the chat does not exist."
            ),
        },
    )
    def post(self, request, channel, contact_id):
        body = PauseBotSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        link, inbox = chat_scope(request, channel, body.validated_data["account"])
        # Only chats that exist: otherwise anyone could create records for made-up ids
        if not inbox.messages(link.account).filter(contact_id=contact_id, channel=channel).exists():
            raise Http404
        state = set_bot_paused(
            inbox,
            contact_id,
            link.account,
            paused=body.validated_data["paused"],
            minutes=body.validated_data.get("minutes"),
            paused_by=request.user.full_name,
            channel=channel,
        )
        data = BotStateSerializer({**state, "account": account_of(link)}).data
        return Response({"success": True, "data": data})


class TemplateListView(APIView):
    """GET /api/v1/inbox/whatsapp/templates/ → the templates of an account that can be sent."""

    permission_classes = [IsAuthenticated, HasActiveTenant]

    @extend_schema(
        parameters=[TemplatesQuerySerializer],
        responses={
            200: inline_serializer(
                "TemplateListResponse",
                {"success": serializers.BooleanField(), "data": TemplateSerializer(many=True)},
            )
        },
    )
    def get(self, request):
        query = TemplatesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        link = pick_link(business_links(request, "whatsapp"), query.validated_data["account"])
        templates = templates_of(link)
        return Response({"success": True, "data": TemplateSerializer(templates, many=True).data})


class UnblockView(APIView):
    """POST /api/v1/inbox/<channel>/conversations/<contact>/unblock/ → lift the block of a client."""

    permission_classes = [IsAuthenticated, HasActiveTenant, IsSupervisorOrAdmin]

    @extend_schema(
        description=(
            "Lifts the block that the bot put on a client who insisted on messages unrelated to the "
            "business, and clears their faults, for supervisors and admins. It is fine if the "
            "client was not blocked."
        ),
        request=UnblockSerializer,
        responses={
            200: inline_serializer(
                "UnblockResponse",
                {"success": serializers.BooleanField(), "message": serializers.CharField()},
            ),
            404: OpenApiResponse(
                description="The account is not one of the business's on this channel, or the chat does not exist."
            ),
        },
    )
    def post(self, request, channel, contact_id):
        body = UnblockSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        link, inbox = chat_scope(request, channel, body.validated_data["account"])
        if not inbox.messages(link.account).filter(contact_id=contact_id, channel=channel).exists():
            raise Http404
        rows = ClientStrikes.objects.filter(account=link.account, contact_id=contact_id)
        was_blocked = rows.filter(blocked_until__gt=timezone.now()).exists()
        rows.update(strikes=0, blocked_until=None)
        if was_blocked:
            client_block_changed.send(
                sender=ClientStrikes,
                account=link.account,
                contact_id=contact_id,
                blocked_until=None,
            )
        return Response({"success": True, "message": "The block was lifted."})
