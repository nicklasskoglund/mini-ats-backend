"""
Central application configuration.

Reads environment variables via Pydantic Settings so all env vars
(including future secrets like the Supabase secret key) are handled in one
place, instead of scattered os.environ calls across files. This makes it
easier to keep track of what's required to run the app, and reduces the
risk of a secret being accidentally logged or committed.

The Settings instance is created once (`settings`) and imported wherever
it's needed.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables / .env.

    More fields (SUPABASE_URL, SUPABASE_JWKS_URL, SUPABASE_SECRET_KEY, etc.)
    are added in step 2 when JWT verification against Supabase is built.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "mini-ats-backend"
    environment: str = "development"


settings = Settings()
