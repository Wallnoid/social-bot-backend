"""
The permanent connection of the inbox: a member joins the group of their business and receives
its events (see `events.py`). The connection only listens; nothing the browser sends is read.
"""

from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.tenants.models import Membership, Tenant

from .realtime import group_of, redeem_ticket


@database_sync_to_async
def is_member(user_id, tenant_id) -> bool:
    return Membership.objects.filter(
        user_id=user_id,
        tenant_id=tenant_id,
        tenant__is_deleted=False,
        tenant__suspended_at__isnull=True,
        user__is_active=True,
    ).exists()


@database_sync_to_async
def is_open(tenant_id) -> bool:
    return Tenant.objects.filter(pk=tenant_id, suspended_at__isnull=True).exists()


# The business was suspended: the browser can tell this apart from a network cut and not retry
SUSPENDED_CLOSE_CODE = 4403


class InboxConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        query = parse_qs(self.scope["query_string"].decode())
        ticket = (query.get("ticket") or [""])[0]
        # The permits live in Redis: a blocking call, so it must not run on the event loop
        holder = await sync_to_async(redeem_ticket)(ticket) if ticket else None
        if holder is None or not await is_member(*holder):
            await self.close()
            return
        self.group = group_of(holder[1])
        await self.channel_layer.group_add(self.group, self.channel_name)
        # Checked again once in the group: a suspension between the two checks closes it here,
        # since its message to close the group did not reach this connection yet
        if not await is_open(holder[1]):
            await self.channel_layer.group_discard(self.group, self.channel_name)
            await self.close(code=SUSPENDED_CLOSE_CODE)
            return
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def business_suspended(self, event):
        """The Social Bot team suspended the business: the connection ends now."""
        await self.close(code=SUSPENDED_CLOSE_CODE)

    async def inbox_event(self, event):
        """Hand to the browser an event sent to the group of the business."""
        await self.send_json(event["payload"])
