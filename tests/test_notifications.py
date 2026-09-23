import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from pathlib import Path

from app.notifications.email import send_unknown_person_email
from app.notifications.telegram import send_unknown_person_alert
from app.core.config import settings


@pytest.mark.anyio
async def test_email_notification_with_credentials_and_tls():
    settings.EMAIL_ENABLED = True
    settings.SMTP_HOST = "smtp.example.com"
    settings.SMTP_PORT = 587
    settings.SMTP_USERNAME = ""
    settings.SMTP_PASSWORD = ""
    settings.ALERT_EMAIL_RECIPIENTS = "admin@example.com"

    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = ({}, "250 OK")
        result = await send_unknown_person_email(
            photo_path="nonexistent.jpg",
            camera_name="CAM_ENTRANCE_01",
            confidence=0.85,
            timestamp="2026-08-01 12:00",
            ip_address="192.168.1.50",
            custom_title="⚠ Spoofing Attack Detected"
        )
        assert result is True
        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert kwargs["username"] is None
        assert kwargs["password"] is None
        assert kwargs["start_tls"] is True
        assert kwargs["use_tls"] is False


@pytest.mark.anyio
async def test_telegram_notification_html_escaping():
    settings.TELEGRAM_ENABLED = True
    settings.TELEGRAM_BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    settings.TELEGRAM_CHAT_ID = "987654321"

    with patch("telegram.Bot.send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        result = await send_unknown_person_alert(
            photo_path="nonexistent.jpg",
            camera_name="CAM_FRONT_GATE_01",
            confidence=0.85,
            timestamp="2026-08-01 12:00",
            custom_title="🚨 Warning - Unknown Person Detected"
        )
        assert result is True
        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert "CAM_FRONT_GATE_01" in kwargs["text"]
        assert kwargs["parse_mode"].name == "HTML"
