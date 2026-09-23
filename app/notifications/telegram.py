"""
Sends an instant Telegram alert (with the snapshot photo attached)
whenever an unknown person is detected. Telegram is used as the
primary/fastest channel per the assignment ("Telegram is much faster
than email").

Setup:
1. Create a bot via @BotFather on Telegram, copy the token.
2. Message your bot once (or add it to a group) and hit
   https://api.telegram.org/bot<TOKEN>/getUpdates to find the chat_id.
3. Put both into .env as TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID.
"""
import html
import logging
from pathlib import Path
from typing import Optional

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_unknown_person_alert(
    photo_path: str, camera_name: str, confidence: float, timestamp: str, custom_title: Optional[str] = None
) -> bool:
    """Returns True if the alert was sent successfully."""
    if not settings.TELEGRAM_ENABLED:
        logger.info("Telegram alerts disabled (TELEGRAM_ENABLED=false); skipping.")
        return False
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        logger.warning("Telegram alert requested but bot token/chat id not configured.")
        return False

    title_val = custom_title if custom_title else "🚨 <b>Warning - Unknown Person Detected</b>"
    if custom_title and not (custom_title.startswith("<") and custom_title.endswith(">")):
        title_val = f"<b>{html.escape(custom_title)}</b>"

    conf_pct = confidence * 100 if confidence <= 1.0 else confidence

    caption = (
        f"{title_val}\n"
        f"<b>Time:</b> {html.escape(str(timestamp))}\n"
        f"<b>Camera:</b> {html.escape(str(camera_name))}\n"
        f"<b>Confidence:</b> {conf_pct:.0f}%"
    )

    try:
        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        image_file = Path(photo_path)
        if image_file.exists() and image_file.is_file():
            with image_file.open("rb") as photo:
                await bot.send_photo(
                    chat_id=settings.TELEGRAM_CHAT_ID,
                    photo=photo,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
        else:
            await bot.send_message(
                chat_id=settings.TELEGRAM_CHAT_ID,
                text=caption + "\n<i>(snapshot file missing)</i>",
                parse_mode=ParseMode.HTML,
            )
        return True
    except TelegramError:
        logger.exception("Failed to send Telegram alert")
        return False
