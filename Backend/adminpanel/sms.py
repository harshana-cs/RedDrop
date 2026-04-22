import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def send_sms(phone_number: str, message: str) -> bool:
    """
    Send SMS via the configured provider.

    Returns True when the provider indicates success, otherwise False.
    """
    if not phone_number:
        return False

    try:
        token = getattr(settings, "SMS_TOKEN", "") or ""
        sender = getattr(settings, "SMS_FROM", "") or ""

        response = requests.post(
            "https://app.bharosasms.com/api/v1/sms/send/",
            data={
                "token": token.strip(),
                "from": sender.strip(),
                "to": str(phone_number).strip(),
                "text": message,
            },
            timeout=8,
        )
        result = response.json() if response.content else {}
        ok = result.get("response_code") == 200
        if not ok:
            logger.warning("SMS provider returned non-success: %s", result)
        return ok
    except Exception as exc:
        logger.exception("SMS failed for %s: %s", phone_number, exc)
        return False

