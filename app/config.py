from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    demo: bool = False
    http_timeout: float = 8.0
    model_config = SettingsConfigDict(env_prefix="HOME_CHECK_", env_file=ROOT / ".env")

settings = Settings()
DB_PATH = ROOT / "data" / "homecheck.db"

