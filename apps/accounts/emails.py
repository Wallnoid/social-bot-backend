"""
Emails sent to users by the accounts app.
"""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def send_set_password_email(user):
    """Email the user a one-time link to create their password."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.FRONTEND_URL}/set-password?uid={uid}&token={token}"
    hours = -(-settings.PASSWORD_RESET_TIMEOUT // (60 * 60))
    if hours % 24 == 0:
        days = hours // 24
        validity = f"{days} {'día' if days == 1 else 'días'}"
    else:
        validity = f"{hours} {'hora' if hours == 1 else 'horas'}"
    send_mail(
        subject="Crea tu contraseña de Social Bot",
        message=(
            f"Hola {user.first_name},\n\n"
            "Ya tienes acceso a Social Bot. Crea tu contraseña con este enlace "
            f"(válido por {validity}):\n\n"
            f"{link}\n\n"
            "Si no esperabas este correo, puedes ignorarlo."
        ),
        from_email=None,
        recipient_list=[user.email],
    )
