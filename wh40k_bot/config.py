import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # Telegram
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))

    # Database
    db_host: str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    db_port: int = field(default_factory=lambda: int(os.getenv("DB_PORT", "5432")))
    db_name: str = field(default_factory=lambda: os.getenv("DB_NAME", "wh40k_bot"))
    db_user: str = field(default_factory=lambda: os.getenv("DB_USER", "postgres"))
    db_password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", ""))

    # Redis
    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    redis_port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    redis_db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))

    # Admin user IDs (Telegram user_id)
    admin_ids: List[int] = field(default_factory=lambda: [
        int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
    ])

    # Proxy (опционально, для локальной разработки)
    proxy_url: str = field(default_factory=lambda: os.getenv("PROXY_URL", ""))

    # Game settings
    default_deadline_hours: int = 24  # дефолтный дедлайн для отправки списков
    reminder_before_hours: int = 2    # напоминание за N часов до дедлайна

    # Timezone offset for display and input (UTC+N), e.g. 10 for UTC+10
    timezone_offset: int = field(default_factory=lambda: int(os.getenv("TIMEZONE_OFFSET", "0")))

    @property
    def db_url(self) -> str:
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


config = Config()
