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

    SUPABASE_URL and SUPABASE_JWKS_URL have no defaults on purpose: JWT
    verification is a security-critical dependency used on every protected
    endpoint, so the app should fail loudly at startup if they're missing
    rather than silently running with an unusable auth setup.

    SUPABASE_SECRET_KEY has no default either: it's the service-role key
    used for every database read/write (bypasses RLS, since FastAPI - not
    Postgres - enforces ownership/authorization), so the app is unusable
    without it and should fail at startup rather than at the first request.

    ANTHROPIC_API_KEY has no default for the same reason: it's required to
    run a CV assessment, so the app should fail at startup rather than at
    the first POST /candidates/{id}/assess call.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "mini-ats-backend"
    environment: str = "development"

    supabase_url: str
    supabase_jwks_url: str
    supabase_secret_key: str
    # Supabase issues tokens with aud="authenticated" by default.
    supabase_jwt_audience: str = "authenticated"
    # Supabase's asymmetric JWT signing keys use ES256; RS256 is accepted
    # too since Supabase also supports RSA key pairs for this feature.
    supabase_jwt_algorithms: list[str] = ["ES256", "RS256"]

    anthropic_api_key: str


settings = Settings()
