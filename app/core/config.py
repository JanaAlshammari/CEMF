from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Campus Event Management Framework"
    api_prefix: str = "/api/v1"
    timezone_name: str = "Asia/Riyadh"   # used for dates printed on certificates

    database_url: str
    secret_key: str
    ticket_signing_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    cors_origins: list[str] = ["http://localhost:8000"]


settings = Settings()
