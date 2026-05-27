import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _normalize_phone(phone_number: str) -> str:
    raw = str(phone_number or "").strip()
    if not raw:
        return ""

    cleaned = re.sub(r"[^\d+]", "", raw)
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]

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
    if not phone_number:
        return False

    try:
        api_key   = str(getattr(settings, "SMS_TOKEN", "") or "").strip().strip('"').strip("'")
        sender    = str(getattr(settings, "SMS_FROM",  "") or "").strip().strip('"').strip("'")
        to_number = _normalize_phone(phone_number)

        # ── DEBUG (remove after SMS is confirmed working) ──────
        print(f"[SMS] to={to_number}  sender={sender}  key_preview={api_key[:8]}...  key_len={len(api_key)}")

        if not api_key:
            print("[SMS] ❌ MISSING TOKEN — set SMS_TOKEN in .env")
            logger.error("SMS skipped: missing SMS_TOKEN")
            return False

        if not to_number:
            print("[SMS] ❌ INVALID PHONE —", phone_number)
            logger.error("SMS skipped: invalid phone number %r", phone_number)
            return False

        payload = {
            "to": [to_number],
            "text": message,
            "sender_id": {
                "NT":    sender,
                "Ncell": sender,
            },
            "message_type": "plain",
        }

        print(f"[SMS] Sending payload: {payload}")

        response = requests.post(
            "https://app.bharosasms.com/api/v1/sms/send/",
            json=payload,
            headers={
                "X-API-KEY":    api_key,
                "Content-Type": "application/json",
            },
            timeout=8,
        )

        print(f"[SMS] HTTP {response.status_code}  body={response.text[:400]}")

        try:
            result = response.json() if response.content else {}
        except ValueError:
            result = {"raw": response.text}

        code = result.get("response_code")
        ok   = str(code) == "200" if code is not None else response.ok

        print(f"[SMS] response_code={code}  ok={ok}")

        if not ok:
            logger.warning(
                "SMS provider non-success for %s: http=%s body=%s",
                to_number, response.status_code, result,
            )
        else:
            logger.info("SMS sent successfully to %s", to_number)

        return ok

    except Exception as exc:
        print(f"[SMS] ❌ EXCEPTION: {exc}")
        logger.exception("SMS failed for %s: %s", phone_number, exc)
        return False