import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    DB_HOST     = os.getenv("DB_HOST", "localhost")
    DB_PORT     = int(os.getenv("DB_PORT", 5432))
    DB_NAME     = os.getenv("DB_NAME", "industrial_db")
    DB_USER     = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    PLC_HOST    = os.getenv("PLC_HOST", "192.168.15.1")
    PLC_PORT    = int(os.getenv("PLC_PORT", 502))
    PLC_UNIT_ID = int(os.getenv("PLC_UNIT_ID", 1))
    PLC_SYNC_INTERVAL_SECONDS = int(os.getenv("PLC_SYNC_INTERVAL_SECONDS", 5))
    PLC_SIMULATION = _env_bool("PLC_SIMULATION", False)

    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    ]

    TOTAL_LEDS = 8
