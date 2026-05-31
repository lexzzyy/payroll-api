"""
Celery tasks for the accounts app.

Tasks pass *IDs* as arguments, not model instances. The worker re-fetches
fresh data from the database, avoiding serialisation issues and stale
data problems.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_backoff_max=600,
    retry_jitter=True,
)
def send_verification_email(self, user_id: int, plain_token: str) -> None:
    """
    Send an email verification link to the user.

    Retries up to 3 times with exponential backoff on any failure.
    In dev, emails are printed to the console via Django's console backend.
    """
    from .models import User

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.warning("send_verification_email: user %s not found, skipping", user_id)
        return

    verification_url = f"{settings.FRONTEND_BASE_URL}/verify-email?token={plain_token}"

    context = {
        "user": user,
        "verification_url": verification_url,
        "support_email": settings.DEFAULT_FROM_EMAIL,
    }

    subject = "Verify your email address"
    text_body = render_to_string("accounts/email/verify_email.txt", context)
    html_body = render_to_string("accounts/email/verify_email.html", context)

    send_mail(
        subject=subject,
        message=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_body,
        fail_silently=False,
    )

    logger.info("Verification email sent to %s", user.email)
