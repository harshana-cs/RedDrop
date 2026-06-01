from __future__ import annotations

from html import escape
from typing import Iterable, Sequence

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags


def _normalize_lines(lines: Sequence[str] | None) -> str:
    if not lines:
        return ""
    return "".join(f"<p style=\"margin:0 0 12px;\">{escape(line)}</p>" for line in lines if line)


def _normalize_bullets(items: Sequence[str] | None) -> str:
    if not items:
        return ""
    return "".join(
        f"<li style=\"margin:0 0 8px;\">{escape(item)}</li>"
        for item in items
        if item
    )


def build_branded_email_html(
    *,
    title: str,
    lines: Sequence[str] | None = None,
    bullets: Sequence[str] | None = None,
    highlight_label: str | None = None,
    highlight_value: str | None = None,
    highlight_note: str | None = None,
    cta_text: str | None = None,
    cta_url: str | None = None,
    footer_note: str = "If you need help, reply to this email or contact the RedDrop team.",
    accent: str = "#B91C1C",
    eyebrow: str = "RedDrop",
) -> str:
    lines_html = _normalize_lines(lines)
    bullets_html = _normalize_bullets(bullets)
    highlight_html = ""
    if highlight_value:
        highlight_html = f"""
          <div style="margin:18px 0 12px;padding:18px 20px;border-radius:18px;background:linear-gradient(180deg,#fff7f7 0%,#ffffff 100%);border:1px solid #f2c7c7;">
            <div style="font-size:12px;letter-spacing:.12em;text-transform:uppercase;font-weight:700;color:{accent};margin-bottom:8px;">
              {escape(highlight_label or 'Verification Code')}
            </div>
            <div style="font-size:32px;line-height:1.1;font-weight:800;letter-spacing:.18em;color:#111827;font-family:Arial,Helvetica,sans-serif;">
              {escape(highlight_value)}
            </div>
            {f'<div style="margin-top:8px;font-size:13px;line-height:1.5;color:#6b7280;">{escape(highlight_note)}</div>' if highlight_note else ''}
          </div>
        """
    cta_html = ""
    if cta_text and cta_url:
        cta_html = f"""
          <div style="margin:28px 0 10px;">
            <a href="{escape(cta_url)}" style="display:inline-block;background:{accent};color:#ffffff;text-decoration:none;font-weight:700;padding:13px 22px;border-radius:14px;box-shadow:0 8px 20px rgba(0,0,0,0.12);">
              {escape(cta_text)}
            </a>
          </div>
        """

    bullets_block = ""
    if bullets_html:
        bullets_block = f"""
          <div style="background:#fff7f7;border:1px solid #f5d2d2;border-radius:18px;padding:18px 20px;margin:18px 0 8px;">
            <ul style="margin:0;padding-left:18px;color:#3d3d4a;line-height:1.6;">{bullets_html}</ul>
          </div>
        """

    return f"""
    <div style="margin:0;padding:0;background:#f4f7fb;">
      <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
        {escape(title)}
      </div>
      <div style="max-width:680px;margin:0 auto;padding:26px 12px;">
        <div style="background:#ffffff;border-radius:28px;overflow:hidden;border:1px solid #e8ebf2;box-shadow:0 18px 50px rgba(15,23,42,0.08);">
          <div style="background:linear-gradient(135deg,{accent} 0%, #7f1d1d 100%);padding:28px 30px;color:#fff;position:relative;">
            <div style="font-size:12px;letter-spacing:.2em;text-transform:uppercase;opacity:.9;font-weight:800;">{escape(eyebrow)}</div>
            <div style="font-size:30px;line-height:1.15;font-weight:800;margin-top:8px;">{escape(title)}</div>
            <div style="margin-top:12px;font-size:14px;line-height:1.6;opacity:.92;max-width:500px;">
              This message was sent automatically from the RedDrop system.
            </div>
          </div>

          <div style="padding:30px;color:#1f2937;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.7;">
            {lines_html}
            {highlight_html}
            {bullets_block}
            {cta_html}
            <div style="margin-top:28px;padding-top:18px;border-top:1px solid #ececf2;color:#6b7280;font-size:13px;">
              {escape(footer_note)}
            </div>
          </div>
        </div>
      </div>
    </div>
    """


def send_branded_email(
    *,
    subject: str,
    to: str | Sequence[str] | None = None,
    title: str,
    message: str | None = None,
    recipient_list: Sequence[str] | None = None,
    lines: Sequence[str] | None = None,
    bullets: Sequence[str] | None = None,
    highlight_label: str | None = None,
    highlight_value: str | None = None,
    highlight_note: str | None = None,
    cta_text: str | None = None,
    cta_url: str | None = None,
    footer_note: str = "If you need help, reply to this email or contact the RedDrop team.",
    from_email: str | None = None,
    accent: str = "#B91C1C",
    eyebrow: str = "RedDrop",
    fail_silently: bool = True,
) -> int:
    if lines is None and message:
        lines = [line for line in (part.strip() for part in message.splitlines()) if line]

    recipients_source: str | Sequence[str] | None = to if to is not None else recipient_list
    if recipients_source is None:
        recipients = []
    else:
        recipients = [recipients_source] if isinstance(recipients_source, str) else list(recipients_source)

    html = build_branded_email_html(
        title=title,
        lines=lines,
        bullets=bullets,
        highlight_label=highlight_label,
        highlight_value=highlight_value,
        highlight_note=highlight_note,
        cta_text=cta_text,
        cta_url=cta_url,
        footer_note=footer_note,
        accent=accent,
        eyebrow=eyebrow,
    )
    plain = strip_tags(html)
    msg = EmailMultiAlternatives(
        subject=subject,
        body=plain,
        from_email=from_email or settings.EMAIL_HOST_USER,
        to=recipients,
    )
    msg.attach_alternative(html, "text/html")
    return msg.send(fail_silently=fail_silently)
