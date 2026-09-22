"""Celery tasks for the organisations app."""

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
def send_invitation_email(self, invitation_id: int, plain_token: str) -> None:
    """Email an organisation invitation link."""
    from .models import OrganisationInvitation

    try:
        invitation = OrganisationInvitation.objects.select_related(
            "organisation", "invited_by"
        ).get(pk=invitation_id)
    except OrganisationInvitation.DoesNotExist:
        logger.warning("send_invitation_email: invitation %s not found", invitation_id)
        return

    accept_url = f"{settings.FRONTEND_BASE_URL}/accept-invite?token={plain_token}"

    context = {
        "organisation": invitation.organisation.legal_name,
        "role": invitation.get_role_display(),
        "inviter": (
            invitation.invited_by.get_full_name() if invitation.invited_by else "An administrator"
        ),
        "accept_url": accept_url,
        "support_email": settings.DEFAULT_FROM_EMAIL,
    }

    subject = f"You've been invited to join {invitation.organisation.legal_name}"
    text_body = render_to_string("organisations/email/invitation.txt", context)
    html_body = render_to_string("organisations/email/invitation.html", context)

    send_mail(
        subject=subject,
        message=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.email],
        html_message=html_body,
        fail_silently=False,
    )
    logger.info("Invitation email sent to %s", invitation.email)
