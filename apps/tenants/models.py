"""
Tenant models.

A tenant is a business using the suite. Users belong to tenants through
memberships, which carry the role the user has in that business.
"""

from django.conf import settings
from django.db import models

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
