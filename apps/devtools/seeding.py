"""
Realistic demo data for trying the frontend without real accounts.

Everything seeded is marked with the `demo-` prefix (business names, account and contact ids,
user emails), so it can be found and deleted without touching real data.
"""

import itertools
from datetime import timedelta

from django.contrib.auth import get_user_model
from wanps.messaging.models import Account, App, Conversation, Message

from apps.channels.models import ChannelAccount
from apps.tenants.models import Membership, Tenant

User = get_user_model()

PREFIX = "demo-"
EMAIL_DOMAIN = "demo.test"
ACME = "demo-Acme Dental"
RIVAL = "demo-Rival Clinic"
APP_NAME = "demo-meta-app"

# What the seeding creates, by exact name: a real business or user whose name only starts with
# "demo-" is never taken for seeded data.
DEMO_TENANTS = (ACME, RIVAL)
ACCOUNT_SLUGS = ("wa-1", "wa-2", "msg-1", "msg-off", "ig-1", "rival-wa")
DEMO_ACCOUNT_IDS = [f"{PREFIX}{slug}" for slug in ACCOUNT_SLUGS]
USER_SLUGS = ("admin", "supervisor", "agent", "multi", "rival-admin")


def demo_email(slug):
    return f"{PREFIX}{slug}@{EMAIL_DOMAIN}"


DEMO_EMAILS = [demo_email(slug) for slug in USER_SLUGS]


def seed_businesses_and_users(password):
    """The two demo businesses, a user per role in the first and one user in both."""
    acme = Tenant.objects.create(name=ACME, industry=Tenant.Industry.HEALTH)
    rival = Tenant.objects.create(name=RIVAL, industry=Tenant.Industry.HEALTH)

    def member(slug, first_name, last_name, *roles):
        user = User.objects.create_user(
            email=demo_email(slug), password=password, first_name=first_name, last_name=last_name
        )
        for tenant, role in roles:
            Membership.objects.create(tenant=tenant, user=user, role=role)
        return user

    roles = Membership.Role
    member("admin", "Rosa", "Vega", (acme, roles.ADMIN))
    member("supervisor", "Sergio", "Luna", (acme, roles.SUPERVISOR))
    member("agent", "Ana", "Mora", (acme, roles.AGENT))
    member("multi", "Marco", "Polo", (acme, roles.ADMIN), (rival, roles.AGENT))
    member("rival-admin", "Rita", "Soto", (rival, roles.ADMIN))
    return acme, rival


def seed_accounts(acme, rival):
    """The channel accounts of both businesses, on a demo Meta App, with fake tokens."""
    app = App.objects.create(
        name=APP_NAME,
        app_secret="demo-fake-app-secret",
        verify_token="demo-fake-verify-token",
    )
    for tenant in (acme, rival):
        tenant.meta_app = app
        tenant.save()

    def connect(tenant, channel, slug, name, is_active=True):
        account = Account.objects.create(
            channel=channel,
            app=app,
            name=f"{PREFIX}{name}",
            external_id=f"{PREFIX}{slug}",
            business_id=f"{PREFIX}waba-{slug}" if channel == "whatsapp" else "",
            access_token="demo-fake-token",
            is_active=is_active,
        )
        ChannelAccount.objects.create(tenant=tenant, account=account)
        return account

    return {
        "wa1": connect(acme, "whatsapp", "wa-1", "Recepción WhatsApp"),
        "wa2": connect(acme, "whatsapp", "wa-2", "Ventas WhatsApp"),
        "msg1": connect(acme, "messenger", "msg-1", "Página Messenger"),
        "msg_off": connect(acme, "messenger", "msg-off", "Página inactiva", is_active=False),
        "ig1": connect(acme, "instagram", "ig-1", "Instagram"),
        "rival_wa": connect(rival, "whatsapp", "rival-wa", "Rival WhatsApp"),
    }


IN, OUT = Message.DIRECTION_IN, Message.DIRECTION_OUT
HOUR, DAY = 60, 24 * 60  # the times below are minutes before now

# For each account: its chats as (client, name, minutes since the client wrote, who answered
# last, bot pause). The pause is None, ("forever", by) or ("until", minutes from now, by).
SCENARIOS = {
    "wa1": [
        ("ana", "Ana Pérez", 5, "bot", None),
        ("luis", "Luis Mora", 2 * HOUR, "person", ("forever", "Rosa Vega")),
        ("marta", "Marta Ruiz", 3 * HOUR, "person", ("until", 90, "Rosa Vega")),
        ("pablo", "Pablo Vera", 30 * HOUR, "bot", None),
        ("sofia", "Sofía León", 5 * DAY, "bot", None),
        ("carlos", "Carlos Díaz", HOUR, "bot", None),
    ],
    "wa2": [
        ("carlos", "Carlos Díaz", 40 * HOUR, "bot", None),
        ("julia", "Julia Sanz", 20, "bot", None),
        ("hugo", "Hugo Paz", 6 * DAY, "bot", None),
    ],
    "msg1": [
        ("lucia", "Lucía Gómez", 10, "bot", None),
        ("diego", "Diego Pino", 3 * HOUR, "person", ("forever", "Sergio Luna")),
        ("nora", "Nora Vidal", 4 * HOUR, "person", ("until", 45, "Ana Mora")),
        ("raul", "Raúl Ortiz", 26 * HOUR, "bot", None),
        ("ines", "Inés Mar", 3 * DAY, "bot", None),
        ("tito", "Tito Rey", 9 * DAY, "bot", None),
        ("carla", "Carla Sol", 15 * DAY, "bot", None),
        ("beto", "Beto Cano", HOUR, "bot", None),
    ],
    "msg_off": [
        ("diego", "Diego Pino", 2 * DAY, "bot", None),
        ("zoe", "Zoe Lara", 5 * HOUR, "bot", None),
    ],
    "ig1": [
        ("mia", "Mía Torres", 15, "bot", None),
        ("leo", "Leo Prado", 2 * HOUR, "person", ("forever", "Ana Mora")),
        ("vera", "Vera Núñez", 6 * HOUR, "person", ("until", 120, "Sergio Luna")),
        ("omar", "Omar Reyes", 27 * HOUR, "bot", None),
        ("pili", "Pili Costa", 4 * DAY, "bot", None),
        ("rene", "René Alba", 8 * DAY, "bot", None),
        ("sara", "Sara Vidal", 12 * DAY, "bot", None),
        ("juan", "Juan Ríos", 30, "bot", None),
    ],
    "rival_wa": [
        ("irma", "Irma Cuesta", 25, "bot", None),
        ("jose", "José Pardo", 2 * DAY, "bot", None),
        ("kira", "Kira Báez", 3 * HOUR, "person", ("forever", "Rita Soto")),
    ],
}


class MessageBuilder:
    """Collects messages and saves them together, each with its own date."""

    def __init__(self, now):
        self.now = now
        self.pending = []
        self.numbers = itertools.count(1)

    def add(
        self,
        account,
        contact_id,
        name,
        direction,
        text,
        minutes_ago,
        message_type="text",
        status="",
        sent_by="",
    ):
        message = Message(
            channel=account.channel,
            account=account,
            external_id=f"{PREFIX}msg-{next(self.numbers):06d}",
            direction=direction,
            contact_id=contact_id,
            contact_name=name if direction == IN else "",
            message_type=message_type,
            text=text,
            status=status,
            sent_by=sent_by,
            processed=True,
        )
        self.pending.append((message, minutes_ago))

    def save(self):
        # `created_at` is set when a message is created, so the dates are set afterwards
        created = Message.objects.bulk_create([message for message, _ in self.pending])
        for message, (_, minutes_ago) in zip(created, self.pending, strict=True):
            message.created_at = self.now - timedelta(minutes=minutes_ago)
        Message.objects.bulk_update(created, ["created_at"])


def short_chat(builder, account, contact, name, client_wrote_ago, last_answer, person=""):
    """A chat of four or five messages; the client wrote last `client_wrote_ago` minutes ago."""
    contact_id = f"{PREFIX}{contact}"
    ago = client_wrote_ago
    builder.add(account, contact_id, name, IN, "Hola, buenas tardes", ago + 9)
    builder.add(
        account,
        contact_id,
        name,
        OUT,
        "¡Hola! Soy el asistente virtual. ¿En qué puedo ayudarte?",
        ago + 8,
        status="read",
    )
    builder.add(account, contact_id, name, IN, "¿Tienen cita disponible esta semana?", ago)
    answer_at = max(ago - 1, 0)
    if last_answer == "bot":
        builder.add(
            account,
            contact_id,
            name,
            OUT,
            "Claro, tengo el martes y el jueves por la tarde.",
            answer_at,
            status="delivered",
        )
    else:
        builder.add(
            account,
            contact_id,
            name,
            OUT,
            "Hola, te escribo yo. El jueves a las 16:00 te queda bien?",
            answer_at,
            status="read",
            sent_by=person,
        )


def pause_bot(account, contact, now, pause):
    until = now + timedelta(minutes=pause[1]) if pause[0] == "until" else None
    Conversation.objects.create(
        account=account,
        channel=account.channel,
        contact_id=f"{PREFIX}{contact}",
        bot_paused=True,
        bot_paused_until=until,
        paused_by=pause[-1],
    )


def seed_conversations(accounts, now):
    """The short chats of every account, with the bot active or paused."""
    builder = MessageBuilder(now)
    for key, chats in SCENARIOS.items():
        for contact, name, wrote_ago, last_answer, pause in chats:
            # The person who answered is who paused the bot in that chat
            person = pause[-1] if pause else ""
            short_chat(builder, accounts[key], contact, name, wrote_ago, last_answer, person)
            if pause:
                pause_bot(accounts[key], contact, now, pause)
    long_chat(builder, accounts["wa1"], "elena", "Elena Cruz")
    every_kind_chat(builder, accounts["wa1"], "tomas", "Tomás Gil")
    many_chats(builder, accounts["wa1"])
    builder.save()
    return builder


LONG_TEXT = (
    "Buenas tardes, le escribo porque necesito reagendar la cita que tenía para el próximo lunes. "
    "Resulta que me surgió un compromiso de trabajo que no puedo mover, y quisiera saber si hay "
    "alguna otra hora disponible durante la semana, preferiblemente por la tarde, después de las "
    "cuatro, porque en la mañana estoy ocupado. También quería preguntar si el tratamiento que "
    "me indicaron incluye la revisión posterior o si se cobra aparte, y si puedo pagar con "
    "tarjeta o solamente en efectivo. Muchas gracias de antemano por la ayuda."
)
LONG_LINK = "https://clinica-demo.example.com/reservas/confirmar?token=" + "a1b2c3" * 40


def long_chat(builder, account, contact, name, total=130):
    """A very long chat, to try scrolling and loading older messages."""
    contact_id = f"{PREFIX}{contact}"
    for n in range(total):
        minutes_ago = 10 + (total - 1 - n) * 3
        incoming = n % 2 == 0
        if n % 10 == 0:
            text = LONG_TEXT
        elif n % 10 == 1:
            text = "Línea uno del mensaje\nLínea dos\n\nLínea cuatro, tras una línea en blanco"
        elif n % 10 == 3:
            text = "¡Muchas gracias! 😀🙏👍 Nos vemos pronto 🦷✨"
        elif n % 13 == 0:
            text = f"Aquí está el enlace para confirmar: {LONG_LINK}"
        else:
            text = f"Mensaje número {n + 1} de la conversación larga"
        if incoming:
            builder.add(account, contact_id, name, IN, text, minutes_ago)
        else:
            builder.add(account, contact_id, name, OUT, text, minutes_ago, status="read")


def every_kind_chat(builder, account, contact, name):
    """One chat with every type of message, every delivery status and every sender."""
    contact_id = f"{PREFIX}{contact}"
    steps = [  # (direction, text, type, status, sent_by)
        (IN, "Hola, quería consultar por una limpieza dental", "text", "", ""),
        (OUT, "¡Hola! Soy el asistente virtual. ¿En qué puedo ayudarte?", "text", "sent", ""),
        (IN, "[image]", "image", "", ""),
        (OUT, "Recibí tu foto, déjame revisarla.", "text", "delivered", ""),
        (IN, "[document]", "document", "", ""),
        (IN, "[audio]", "audio", "", ""),
        (OUT, "Te llamo en un momento para verlo.", "text", "read", "Rosa Vega"),
        (OUT, "Mientras tanto, ¿me confirmas tu nombre completo?", "text", "delivered", ""),
        (OUT, "También puedes dejarme tu correo.", "text", "sent", ""),
        (OUT, "Te envié la dirección de la clínica.", "text", "failed", "Rosa Vega"),
        (IN, "No me llegó nada", "text", "", ""),
    ]
    for n, (direction, text, message_type, status, sent_by) in enumerate(steps):
        minutes_ago = 12 + (len(steps) - 1 - n) * 2
        builder.add(
            account, contact_id, name, direction, text, minutes_ago, message_type, status, sent_by
        )


def many_chats(builder, account, total=150):
    """Many simple chats on one account, to try the list with its "load more"."""
    for n in range(1, total + 1):
        contact_id = f"{PREFIX}cliente-{n:04d}"
        name = f"Cliente {n:04d}"
        minutes_ago = 30 + n * 7
        builder.add(
            account,
            contact_id,
            name,
            IN,
            f"Hola, soy el cliente {n}. ¿Siguen atendiendo?",
            minutes_ago,
        )
        builder.add(
            account,
            contact_id,
            name,
            OUT,
            "Sí, estamos atendiendo hasta las 18:00.",
            minutes_ago - 1,
            status="read",
        )


def demo_tenants():
    return Tenant.all_objects.filter(name__in=DEMO_TENANTS)


def already_seeded():
    return demo_tenants().exists()


def reset_demo():
    """Delete what the seeding created, and nothing else: all of it carries the demo prefix."""
    accounts = Account.objects.filter(external_id__in=DEMO_ACCOUNT_IDS)
    Message.objects.filter(account__in=accounts).delete()
    Conversation.objects.filter(account__in=accounts).delete()
    ChannelAccount.all_objects.filter(account__in=accounts).delete()
    accounts.delete()
    demo_tenants().delete()  # also their memberships
    App.objects.filter(name=APP_NAME).delete()
    User.objects.filter(email__in=DEMO_EMAILS).delete()


def add_admin(user):
    """Make an existing user an admin of both demo businesses."""
    for tenant in demo_tenants():
        Membership.objects.update_or_create(
            tenant=tenant, user=user, defaults={"role": Membership.Role.ADMIN}
        )


def summary():
    """What is seeded, as text. It never includes the password."""
    accounts = Account.objects.filter(external_id__in=DEMO_ACCOUNT_IDS)
    messages = Message.objects.filter(account__in=accounts)
    lines = [
        "Demo data:",
        "  Businesses: " + ", ".join(sorted(demo_tenants().values_list("name", flat=True))),
    ]
    for label, queryset in (
        ("Accounts", accounts.values_list("channel", flat=True)),
        ("Conversations", messages.values_list("channel", "account", "contact_id").distinct()),
    ):
        per_channel = {}
        for row in queryset:
            channel = row if isinstance(row, str) else row[0]
            per_channel[channel] = per_channel.get(channel, 0) + 1
        lines.append(
            f"  {label}: "
            + ", ".join(f"{channel} {n}" for channel, n in sorted(per_channel.items()))
        )
    lines.append(f"  Messages: {messages.count()}")
    lines.append("  Users (the password of all of them is the value of SEED_DEMO_PASSWORD):")
    for membership in (
        Membership.objects.filter(tenant__in=demo_tenants())
        .select_related("user", "tenant")
        .order_by("tenant__name", "role")
    ):
        lines.append(f"    {membership.user.email} - {membership.role} of {membership.tenant.name}")
    return "\n".join(lines)
