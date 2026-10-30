"""
Emails sent to users by the tenants app.
"""

from django.conf import settings
from django.core.mail import send_mail

from apps.accounts.emails import format_validity


def send_invitation_email(invitation):
    """Email the invited person a link to join the business."""
    link = f"{settings.FRONTEND_URL}/accept-invitation?token={invitation.token}"
    send_mail(
        subject=f"Te invitaron a {invitation.tenant.name} en Social Bot",
        message=(
            f"Te invitaron a unirte a {invitation.tenant.name} en Social Bot "
            f"con el rol {invitation.get_role_display()}.\n\n"
            "Acepta la invitación con este enlace "
            f"(válido por {format_validity(settings.INVITATION_TIMEOUT)}):\n\n"
            f"{link}\n\n"
            "Si no esperabas este correo, puedes ignorarlo."
        ),
        from_email=None,
        recipient_list=[invitation.email],
    )
