from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR / 'quoteforge.db'}"
    SECRET_KEY: str = "quoteforge-super-secret-key-change-in-production-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    OPENAI_API_KEY: str = ""
    AI_MODEL: str = "gpt-4o-mini"
    AI_TEMPERATURE: float = 0.7
    AI_MAX_TOKENS: int = 2000

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@quoteforge.io"

    SALESFORCE_CLIENT_ID: str = ""
    SALESFORCE_CLIENT_SECRET: str = ""
    # login.salesforce.com for prod, test.salesforce.com for sandbox. Apex
    # admins flip this per packaging org. Used to build /authorize URLs.
    SALESFORCE_LOGIN_URL: str = "https://login.salesforce.com"
    HUBSPOT_CLIENT_ID: str = ""
    HUBSPOT_CLIENT_SECRET: str = ""

    # Public base URL the backend is reachable at (no trailing slash).
    # Used to build OAuth callback URLs and the post-consent redirect.
    # Empty in local dev — code falls back to http://localhost:8000.
    PUBLIC_BASE_URL: str = ""

    # Fernet key used to encrypt Salesforce OAuth tokens at rest. Generate
    # with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
    # Empty in dev → app/core/crypto.py generates an ephemeral key and
    # logs a warning. Required for any deploy that persists tokens.
    TOKEN_ENCRYPTION_KEY: str = ""

    # CORS — comma-separated origin allowlist. Empty string keeps the
    # legacy "*" behaviour for local dev. Production should set this to
    # the frontend origin (Render web URL, prod app domain, etc.).
    # Salesforce Lightning hosts are matched via regex in app/core/cors.py.
    CORS_ALLOW_ORIGINS: str = ""

    # Comma-separated list of email addresses with platform-wide
    # super-admin access — they can see every tenant via the
    # /api/admin/* endpoints and the /admin/tenants frontend page.
    # Stored as an env var, NOT a DB flag, so a runaway script can't
    # accidentally elevate a user account. Defaults to the project
    # owner's address for FYP demos; override in prod.
    SUPER_ADMIN_EMAILS: str = "fahad.saleem@demandzen.com"

    # Agent Gateway (Module 1)
    GATEWAY_DEV_AUTH: bool = True              # TODO: flip to False once OAuth 2.1 lands
    GATEWAY_ISSUER: str = "https://quoteforge.local"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Buyer Room (Module 5) — public-facing mediator assistant
    ANTHROPIC_API_KEY: str = ""
    BUYER_ROOM_MODEL: str = "claude-sonnet-4-6"
    BUYER_ROOM_MAX_TOKENS: int = 2048
    # Base URL that share links embed. Set in .env in prod; sensible dev default.
    BUYER_ROOM_PUBLIC_BASE: str = "http://localhost:3000"

    # Negotiation AI (Module 3)
    # backend: mlx | ollama | vllm | stub. "stub" is the integration-test
    # backend — pure Python, no model. Use for tests + CI; swap to a real
    # backend via env var in dev/prod.
    NEGOTIATION_MODEL_BACKEND: str = "stub"
    NEGOTIATION_MODEL_PATH: str = "models/quoteforge-v3"       # MLX adapter path
    NEGOTIATION_OLLAMA_URL: str = "http://localhost:11434"
    NEGOTIATION_OLLAMA_MODEL: str = "llama3.2:1b"
    NEGOTIATION_VLLM_URL: str = "http://localhost:8000"
    NEGOTIATION_VLLM_MODEL: str = "meta-llama/Llama-3.2-1B-Instruct"
    NEGOTIATION_TIMEOUT_SECONDS: float = 5.0
    NEGOTIATION_MAX_RETRIES: int = 3
    NEGOTIATION_MAX_TOKENS: int = 512

    class Config:
        env_file = str(BASE_DIR / ".env")
        extra = "ignore"  # Allow extra env vars (MLX config, etc.)


settings = Settings()
