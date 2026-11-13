"""
Tenant models.

A tenant is a business using the suite. Users belong to tenants through
memberships, which carry the role the user has in that business.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class Tenant(BaseModel):
    """A business using the suite."""

    class Industry(models.TextChoices):
        RETAIL = "retail", "Comercio minorista"
        FOOD_BEVERAGE = "food_beverage", "Restaurantes y alimentos"
        HEALTH = "health", "Salud y clínicas"
        BEAUTY_WELLNESS = "beauty_wellness", "Belleza y bienestar"
        FITNESS = "fitness", "Deporte y gimnasios"
        EDUCATION = "education", "Educación"
        REAL_ESTATE = "real_estate", "Inmobiliaria"
        AUTOMOTIVE = "automotive", "Automotriz"
        TOURISM = "tourism", "Turismo y hospitalidad"
        PROFESSIONAL_SERVICES = "professional_services", "Servicios profesionales"
        TECHNOLOGY = "technology", "Tecnología"
        CONSTRUCTION = "construction", "Construcción"
        AGRIBUSINESS = "agribusiness", "Agroindustria"
        LOGISTICS = "logistics", "Transporte y logística"
        FINANCE = "finance", "Finanzas y seguros"
        MANUFACTURING = "manufacturing", "Manufactura"
        OTHER = "other", "Otro"

    name = models.CharField(max_length=255)
    industry = models.CharField(max_length=30, choices=Industry.choices, blank=True)
    description = models.TextField(blank=True)
    meta_app = models.ForeignKey(
        "messaging.App",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tenants",
        help_text="The business's own Meta App. Empty uses the shared Social Bot app.",
    )
    bot_max_replies_per_day = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Replies the bots of the business may send in a day. Empty uses the general "
        "number of the server (BOT_MAX_REPLIES_PER_DAY).",
    )

    class Meta(BaseModel.Meta):
        verbose_name = "business"
        verbose_name_plural = "businesses"

    def __str__(self):
        return self.name


class Membership(BaseModel):
    """Links a user to a tenant with a role."""

    class Role(models.TextChoices):
        AGENT = "agent", "Agent"
        SUPERVISOR = "supervisor", "Supervisor"
        ADMIN = "admin", "Admin"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=20, choices=Role.choices)

    class Meta(BaseModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user"],
                condition=models.Q(is_deleted=False),
                name="unique_active_membership_per_tenant_user",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.tenant} ({self.role})"


def generate_invitation_token():
    return secrets.token_urlsafe(32)


def default_invitation_expiry():
    return timezone.now() + timedelta(seconds=settings.INVITATION_TIMEOUT)


class Invitation(BaseModel):
    """An invitation for a person to join a tenant with a role."""

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=Membership.Role.choices)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_invitations",
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_invitation_token,
        editable=False,
    )
    expires_at = models.DateTimeField(default=default_invitation_expiry)

    @classmethod
    def pending(cls):
        """Invitations that can still be accepted: not used, cancelled or expired."""
        return cls.objects.filter(expires_at__gt=timezone.now())

    def __str__(self):
        return f"{self.email} - {self.tenant} ({self.role})"
