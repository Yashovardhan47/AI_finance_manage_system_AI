from __future__ import annotations

import json
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

from app.billing_models import BillingNotification
from app.core.config import Settings


@dataclass(frozen=True)
class DeliveryResult:
    provider: str
    message_id: str
    response: dict


class NotificationDeliveryError(RuntimeError):
    pass


class NotificationAdapter:
    provider = "unknown"

    def send(self, notification: BillingNotification) -> DeliveryResult:
        raise NotImplementedError


def _message_content(notification: BillingNotification) -> tuple[str, str]:
    payload = notification.payload or {}
    subject = str(payload.get("subject") or f"BillFlow: {notification.event_type.replace('_', ' ').title()}")
    body = str(
        payload.get("message")
        or payload.get("summary")
        or "\n".join(f"{key.replace('_', ' ').title()}: {value}" for key, value in payload.items())
        or subject
    )
    return subject, body


class SandboxAdapter(NotificationAdapter):
    provider = "sandbox"

    def send(self, notification: BillingNotification) -> DeliveryResult:
        return DeliveryResult(
            provider=self.provider,
            message_id=f"sandbox_{notification.channel}_{uuid4().hex}",
            response={"accepted": True, "mode": "sandbox", "channel": notification.channel},
        )


class SMTPEmailAdapter(NotificationAdapter):
    provider = "smtp"

    def __init__(self, settings: Settings):
        if not settings.smtp_host:
            raise NotificationDeliveryError("SMTP_HOST is required when EMAIL_PROVIDER=smtp")
        self.settings = settings

    def send(self, notification: BillingNotification) -> DeliveryResult:
        subject, body = _message_content(notification)
        message = EmailMessage()
        message["From"] = self.settings.smtp_from_email
        message["To"] = notification.recipient
        message["Subject"] = subject
        message["Message-ID"] = f"<{uuid4().hex}@billflow>"
        message.set_content(body)
        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=15) as client:
                client.ehlo()
                if self.settings.smtp_starttls:
                    client.starttls(context=ssl.create_default_context())
                    client.ehlo()
                if self.settings.smtp_username:
                    client.login(self.settings.smtp_username, self.settings.smtp_password or "")
                refused = client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise NotificationDeliveryError(f"SMTP delivery failed: {exc}") from exc
        if refused:
            raise NotificationDeliveryError(f"SMTP refused recipient: {list(refused)}")
        return DeliveryResult(self.provider, str(message["Message-ID"]), {"accepted": True})


class TwilioSMSAdapter(NotificationAdapter):
    provider = "twilio"

    def __init__(self, settings: Settings):
        if not all((settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_from_number)):
            raise NotificationDeliveryError(
                "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER are required"
            )
        self.settings = settings

    def send(self, notification: BillingNotification) -> DeliveryResult:
        _, body = _message_content(notification)
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.settings.twilio_account_sid}/Messages.json"
        try:
            response = httpx.post(
                url,
                data={"To": notification.recipient, "From": self.settings.twilio_from_number, "Body": body[:1600]},
                auth=(self.settings.twilio_account_sid or "", self.settings.twilio_auth_token or ""),
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise NotificationDeliveryError(f"Twilio delivery failed: {exc}") from exc
        return DeliveryResult(self.provider, str(data["sid"]), {"status": data.get("status")})


class FCMPushAdapter(NotificationAdapter):
    provider = "fcm"
    scopes = ["https://www.googleapis.com/auth/firebase.messaging"]

    def __init__(self, settings: Settings):
        if not settings.fcm_project_id or not settings.fcm_service_account_json:
            raise NotificationDeliveryError("FCM_PROJECT_ID and FCM_SERVICE_ACCOUNT_JSON are required")
        self.settings = settings

    def _credentials(self):
        source = self.settings.fcm_service_account_json or ""
        if source.lstrip().startswith("{"):
            info = json.loads(source)
        else:
            info = json.loads(Path(source).read_text(encoding="utf-8"))
        credentials = service_account.Credentials.from_service_account_info(info, scopes=self.scopes)
        credentials.refresh(GoogleAuthRequest())
        return credentials

    def send(self, notification: BillingNotification) -> DeliveryResult:
        subject, body = _message_content(notification)
        try:
            credentials = self._credentials()
            response = httpx.post(
                f"https://fcm.googleapis.com/v1/projects/{self.settings.fcm_project_id}/messages:send",
                headers={"Authorization": f"Bearer {credentials.token}"},
                json={
                    "message": {
                        "token": notification.recipient,
                        "notification": {"title": subject, "body": body[:4096]},
                        "data": {"event_type": notification.event_type, "notification_id": str(notification.id)},
                    }
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
        except (OSError, ValueError, httpx.HTTPError) as exc:
            raise NotificationDeliveryError(f"FCM delivery failed: {exc}") from exc
        return DeliveryResult(self.provider, str(data["name"]), {"name": data["name"]})


def adapter_for(notification: BillingNotification, settings: Settings) -> NotificationAdapter:
    if notification.channel == "email" and settings.email_provider.lower() == "smtp":
        return SMTPEmailAdapter(settings)
    if notification.channel == "sms" and settings.sms_provider.lower() == "twilio":
        return TwilioSMSAdapter(settings)
    if notification.channel == "push" and settings.push_provider.lower() == "fcm":
        return FCMPushAdapter(settings)
    return SandboxAdapter()
