import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _normalize_phone(phone_number: str) -> str:
    """
    Normalize numbers for provider:
    - keep leading +
    - strip spaces/dashes/parentheses
    - convert local Nepal mobile (98XXXXXXXX) -> +97798XXXXXXXX
    """
    raw = str(phone_number or "").strip()
    if not raw:
        return ""

    # Keep digits and optional leading +
    cleaned = re.sub(r"[^\d+]", "", raw)
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]

    # Nepal local mobile fallback
    if not cleaned.startswith("+") and len(cleaned) == 10 and cleaned.startswith("9"):
        cleaned = f"+977{cleaned}"

    return cleaned


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
        to_number = _normalize_phone(phone_number)

        if not token.strip():
            logger.error("SMS skipped: missing SMS_TOKEN in settings/environment")
            return False
        if not to_number:
            logger.error("SMS skipped: invalid phone number %r", phone_number)
            return False

        response = requests.post(
            "https://app.bharosasms.com/api/v1/sms/send/",
            data={
                "token": token.strip(),
                "from": sender.strip(),
                "to": to_number,
                "text": message,
            },
            timeout=8,
        )
        result = response.json() if response.content else {}
        code = result.get("response_code")
        ok = str(code) == "200" if code is not None else (response.status_code == 200)
        if not ok:
            logger.warning(
                "SMS provider returned non-success for %s: http=%s body=%s",
                to_number,
                response.status_code,
                result,
            )
        return ok
    except Exception as exc:
        logger.exception("SMS failed for %s: %s", phone_number, exc)
        return False
