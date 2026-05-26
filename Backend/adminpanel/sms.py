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

    # Nepal local mobile fallback: 98XXXXXXXX -> 98XXXXXXXX
    # The provider accepts the local mobile number format in the `to` list.
    if cleaned.startswith("+977"):
        cleaned = cleaned[4:]
    elif cleaned.startswith("977") and len(cleaned) == 12:
        cleaned = cleaned[3:]
    elif cleaned.startswith("00") and cleaned[2:].startswith("977"):
        cleaned = cleaned[5:]

    if cleaned.startswith("+"):
        cleaned = cleaned[1:]

    if len(cleaned) == 10 and cleaned.startswith("9"):
        return cleaned

    return cleaned


def send_sms(phone_number: str, message: str) -> bool:
    """
    Send SMS via the configured provider.

    Returns True when the provider indicates success, otherwise False.
    """
    if not phone_number:
        return False

    try:
        api_key = getattr(settings, "SMS_TOKEN", "") or ""
        sender = getattr(settings, "SMS_FROM", "") or ""
        to_number = _normalize_phone(phone_number)

        if not api_key.strip():
            logger.error("SMS skipped: missing SMS_TOKEN in settings/environment")
            return False
        if not to_number:
            logger.error("SMS skipped: invalid phone number %r", phone_number)
            return False

        payload = {
            "to": [to_number],
            "text": message,
            "sender_id": {
                "NT": sender.strip(),
                "Ncell": sender.strip(),
            },
            "message_type": "plain",
        }

        response = requests.post(
            "https://app.bharosasms.com/api/v1/sms/send/",
            json=payload,
            headers={
                "X-API-KEY": api_key.strip(),
                "Content-Type": "application/json",
            },
            timeout=8,
        )

        try:
            result = response.json() if response.content else {}
        except ValueError:
            result = {"raw": response.text}

        code = result.get("response_code")
        ok = (
            str(code) == "200"
            if code is not None
            else response.ok
        )
        if not ok:
            logger.warning(
                "SMS provider returned non-success for %s: http=%s body=%s",
                to_number,
                response.status_code,
                result,
            )
        else:
            logger.info("SMS sent successfully to %s", to_number)
        return ok
    except Exception as exc:
        logger.exception("SMS failed for %s: %s", phone_number, exc)
        return False
