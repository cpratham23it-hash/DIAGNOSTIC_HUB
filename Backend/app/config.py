"""
Central app configuration. Every setting the app needs is declared here,
typed, with sensible defaults where safe. As later steps add DB/auth/Google
config, those fields get added to this same class — one place to look.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Diagnos API"
    app_env: str = "development"
    frontend_origin: str = "http://localhost:5500"

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "diagnos"

    session_secret: str = "dev-only-insecure-secret-change-me"
    session_expire_minutes: int = 60 * 24 * 7  # 7 days

    google_client_id: str = "88273943888-6cmula4m78gpqs0rvlvkb6mrt64mdq3v.apps.googleusercontent.com"

    upload_dir: str = "uploads"
    max_upload_size_bytes: int = 25 * 1024 * 1024  # 25 MB

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()