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
    cta_text: str | None = None,
    cta_url: str | None = None,
    footer_note: str = "If you need help, reply to this email or contact the RedDrop team.",
    accent: str = "#B91C1C",
    eyebrow: str = "RedDrop",
) -> str:
    lines_html = _normalize_lines(lines)
    bullets_html = _normalize_bullets(bullets)
    cta_html = ""
    if cta_text and cta_url:
        cta_html = f"""
          <div style="margin:28px 0 10px;">
            <a href="{escape(cta_url)}" style="display:inline-block;background:{accent};color:#ffffff;text-decoration:none;font-weight:700;padding:12px 20px;border-radius:12px;">
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
    <div style="margin:0;padding:0;background:#f6f7fb;">
      <div style="max-width:680px;margin:0 auto;padding:24px 12px;">
        <div style="background:#ffffff;border-radius:24px;overflow:hidden;border:1px solid #e9e8ef;box-shadow:0 14px 40px rgba(0,0,0,0.08);">
          <div style="background:linear-gradient(135deg,{accent} 0%, #7f1d1d 100%);padding:24px 28px;color:#fff;">
            <div style="font-size:12px;letter-spacing:.18em;text-transform:uppercase;opacity:.88;font-weight:700;">{escape(eyebrow)}</div>
            <div style="font-size:28px;line-height:1.15;font-weight:800;margin-top:8px;">{escape(title)}</div>
          </div>

          <div style="padding:28px;color:#1f2937;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.7;">
            {lines_html}
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
    to: str | Sequence[str],
    title: str,
    lines: Sequence[str] | None = None,
    bullets: Sequence[str] | None = None,
    cta_text: str | None = None,
    cta_url: str | None = None,
    footer_note: str = "If you need help, reply to this email or contact the RedDrop team.",
    from_email: str | None = None,
    accent: str = "#B91C1C",
    eyebrow: str = "RedDrop",
    fail_silently: bool = True,
) -> int:
    recipients = [to] if isinstance(to, str) else list(to)
    html = build_branded_email_html(
        title=title,
        lines=lines,
        bullets=bullets,
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
