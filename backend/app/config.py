from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openweather_api_key: str = ""
    swimguide_api_key: str = ""
    cache_ttl_seconds: int = 1800  # 30 minutes
    noaa_user_agent: str = "water-monitor/1.0 ceesco53@gmail.com"

    model_config = {"env_file": ".env"}


settings = Settings()
