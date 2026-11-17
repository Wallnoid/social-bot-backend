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


# The business was suspended or deleted: the browser can tell these apart from a network cut
# and not retry
SUSPENDED_CLOSE_CODE = 4403
DELETED_CLOSE_CODE = 4404


@database_sync_to_async
def close_code_of(tenant_id):
    """Why a connection of the business must end now, or None when the business is open."""
    tenant = Tenant.all_objects.filter(pk=tenant_id).only("is_deleted", "suspended_at").first()
    if tenant is None or tenant.is_deleted:
        return DELETED_CLOSE_CODE
    return SUSPENDED_CLOSE_CODE if tenant.suspended_at is not None else None


class InboxConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        query = parse_qs(self.scope["query_string"].decode())
        ticket = (query.get("ticket") or [""])[0]
        # The permits live in Redis: a blocking call, so it must not run on the event loop
        holder = await sync_to_async(redeem_ticket)(ticket) if ticket else None
        if holder is None or not await is_member(*holder):
            # A business that is off says why, so the browser does not retry it as a network cut
            code = await close_code_of(holder[1]) if holder is not None else None
            await self.close(code=code)
            return
        self.group = group_of(holder[1])
        await self.channel_layer.group_add(self.group, self.channel_name)
        # Checked again once in the group: a suspension between the two checks closes it here,
        # since its message to close the group did not reach this connection yet
        code = await close_code_of(holder[1])
        if code is not None:
            await self.channel_layer.group_discard(self.group, self.channel_name)
            await self.close(code=code)
            return
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def business_suspended(self, event):
        """The Social Bot team suspended the business: the connection ends now."""
        await self.close(code=SUSPENDED_CLOSE_CODE)

    async def business_deleted(self, event):
        """The Social Bot team deleted the business: the connection ends now."""
        await self.close(code=DELETED_CLOSE_CODE)

    async def inbox_event(self, event):
        """Hand to the browser an event sent to the group of the business."""
        await self.send_json(event["payload"])
