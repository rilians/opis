from dataclasses import dataclass
import os


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./opis.db"
    demo_data: bool = True
    scheduler_enabled: bool = True
    allow_private_targets: bool = False
    check_concurrency: int = 10
    scheduler_interval: float = 2.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv("OPIS_DATABASE_URL", os.getenv("DATABASE_URL", "sqlite:///./opis.db")),
            demo_data=env_bool("OPIS_DEMO_DATA", True),
            scheduler_enabled=env_bool("OPIS_SCHEDULER_ENABLED", True),
            allow_private_targets=env_bool("OPIS_ALLOW_PRIVATE_TARGETS", False),
            check_concurrency=max(1, min(int(os.getenv("OPIS_CHECK_CONCURRENCY", "10")), 100)),
            scheduler_interval=max(0.25, float(os.getenv("OPIS_SCHEDULER_INTERVAL", "2"))),
        )
