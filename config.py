from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "").strip()
    # Numeric private chat_id: the manager must open the bot and send /start, then /id.
    manager_chat_id: str = os.getenv("MANAGER_CHAT_ID", "").strip()
    # Public Telegram username, used to let clients open a direct chat with the manager.
    manager_username: str = os.getenv("MANAGER_USERNAME", "juuusmi").strip().lstrip("@")
    brand_name: str = os.getenv("BRAND_NAME", "JUSTRAVEL").strip() or "JUSTRAVEL"
    privacy_policy_url: str = os.getenv("PRIVACY_POLICY_URL", "").strip()
    database_path: Path = BASE_DIR / os.getenv("DATABASE_PATH", "data/applications.db")
    welcome_image: Path = BASE_DIR / os.getenv("WELCOME_IMAGE", "welcome.jpg")
    reminder_after_minutes: int = int(os.getenv("REMINDER_AFTER_MINUTES", "60"))


settings = Settings()
