"""
Sends an HTML email alert (with the snapshot attached) as the second
notification channel when an unknown person is detected, per the
assignment's Phase 5 requirement.
"""
import logging
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)

HTML_TEMPLATE = """\
<html>
  <body style="font-family: Arial, sans-serif;">
    <h2 style="color:#c0392b;">{title}</h2>
    <table style="border-collapse: collapse; margin-bottom: 16px;">
      <tr><td style="padding:4px 12px; border-bottom: 1px solid #eee;"><b>Timestamp</b></td><td style="padding:4px 12px; border-bottom: 1px solid #eee;">{timestamp}</td></tr>
      <tr><td style="padding:4px 12px; border-bottom: 1px solid #eee;"><b>Camera</b></td><td style="padding:4px 12px; border-bottom: 1px solid #eee;">{camera_name}</td></tr>
      <tr><td style="padding:4px 12px; border-bottom: 1px solid #eee;"><b>IP Address</b></td><td style="padding:4px 12px; border-bottom: 1px solid #eee;">{ip_address}</td></tr>
      <tr><td style="padding:4px 12px; border-bottom: 1px solid #eee;"><b>Confidence</b></td><td style="padding:4px 12px; border-bottom: 1px solid #eee;">{confidence:.0f}%</td></tr>
    </table>
    <p><b>Snapshot:</b></p>
    <p><img src="cid:snapshot" alt="Snapshot" style="max-width: 480px; border: 1px solid #ddd; border-radius: 8px;" /></p>
  </body>
</html>
"""


async def send_unknown_person_email(
    photo_path: str,
    camera_name: str,
    confidence: float,
    timestamp: str,
    ip_address: str = "N/A",
    custom_title: Optional[str] = None,
) -> bool:
    if not settings.EMAIL_ENABLED:
        logger.info("Email alerts disabled (EMAIL_ENABLED=false); skipping.")
        return False
    if not settings.SMTP_HOST or not settings.alert_recipients_list:
        logger.warning("Email alert requested but SMTP host/recipients not configured.")
        return False

    title_val = custom_title if custom_title else "⚠ Unknown Person Detected"
    conf_pct = confidence * 100 if confidence <= 1.0 else confidence
    
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = ", ".join(settings.alert_recipients_list)
    message["Subject"] = f"[ALERT] {title_val} - {camera_name}"

    # Plain text fallback
    message.set_content(
        f"{title_val}\n"
        f"Timestamp: {timestamp}\n"
        f"Camera: {camera_name}\n"
        f"IP Address: {ip_address}\n"
        f"Confidence: {conf_pct:.0f}%\n"
    )

    html_body = HTML_TEMPLATE.format(
        title=title_val,
        timestamp=timestamp,
        camera_name=camera_name,
        ip_address=ip_address,
        confidence=conf_pct,
    )

    message.add_alternative(html_body, subtype="html")
    image_file = Path(photo_path)
    if image_file.exists() and image_file.is_file():
        ext = image_file.suffix.lower().lstrip(".")
        subtype = "png" if ext == "png" else "jpeg"
        
        html_part = message.get_body("html")
        if html_part:
            html_part.add_related(
                image_file.read_bytes(),
                maintype="image",
                subtype=subtype,
                cid="<snapshot>",
                filename=image_file.name,
            )

    username = settings.SMTP_USERNAME if settings.SMTP_USERNAME else None
    password = settings.SMTP_PASSWORD if settings.SMTP_PASSWORD else None
    use_tls = settings.SMTP_PORT == 465
    start_tls = settings.SMTP_PORT == 587

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=username,
            password=password,
            use_tls=use_tls,
            start_tls=start_tls,
        )
        logger.info(f"Email alert successfully sent to {settings.alert_recipients_list}")
        return True
    except Exception:
        logger.exception("Failed to send email alert")
        return False

