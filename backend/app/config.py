from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "extra": "ignore"}

    # Debug
    debug: bool = False

    # CORS — JSON list, e.g. ALLOWED_ORIGINS=["https://invite.example.com"]
    allowed_origins: list[str] = ["http://localhost:8000", "http://localhost:8080"]

    # Auth
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    # Database
    database_provider: str = "sqlite"
    database_url: str = "sqlite+aiosqlite:///./invitio.db"

    # Uploaded invite images live here (bind-mounted on the NAS so they survive
    # container/image churn). Served read-only at /uploads/<file>.
    upload_dir: str = "./uploads"
    max_upload_mb: int = 10

    # Anti-abuse rate limiting on the open, no-account endpoints (per client IP,
    # fixed 1-hour window). In-memory, single-instance; a no-op when disabled.
    # Set the limit to 0 to disable an individual bucket.
    rate_limit_enabled: bool = True
    rate_limit_create_per_hour: int = 10   # quick-create events
    rate_limit_rsvp_per_hour: int = 60     # RSVP submissions
    rate_limit_wall_per_hour: int = 30     # guest-wall posts
    rate_limit_auth_per_hour: int = 30     # signup + login attempts

    # Page size for the guest-list / RSVP lists on the dashboard. The event detail
    # embeds (at most) this many of each; the rest are fetched on demand from the
    # paginated /invites and /rsvps endpoints.
    list_page_size: int = 50

    # Absolute base URL used to build RSVP links inside outbound emails. Without
    # it the app falls back to relative links, which don't work in email.
    public_base_url: str = "http://localhost:8080"

    # Outbound email via Gmail SMTP with an App Password. Leave the app password
    # blank to disable sending — invite creation still works, the link is just
    # not emailed (the host can copy/share it instead).
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    gmail_address: str = ""       # sender address + SMTP username
    gmail_app_password: str = ""  # 16-char Google App Password (NOT your login password)
    email_from_name: str = "invitio"

    # Reminder emails. A background loop (started only when email is configured)
    # periodically finds events starting within `reminder_window_hours` and emails
    # a reminder to "yes" guests plus a nudge to anyone who hasn't responded.
    # Each event is reminded at most once. Set reminders_enabled=False to disable.
    reminders_enabled: bool = True
    reminder_window_hours: int = 24
    reminder_check_interval_minutes: int = 60

    # Optional AI generation. Both default OFF and are configured independently —
    # text and images usually run on different local servers (e.g. Ollama for
    # text, LocalAI for images). Any OpenAI-compatible endpoint works (local or
    # hosted); only the base URL / key / model change.
    #
    # Text (LLM): /v1/chat/completions — Ollama (:11434/v1) or llama.cpp
    # llama-server (:8080/v1); set the api key only for hosted providers.
    ai_llm_enabled: bool = False
    ai_llm_base_url: str = "http://localhost:11434/v1"
    ai_llm_api_key: str = ""
    ai_llm_model: str = "llama3.1"
    ai_llm_timeout: int = 60
    # Images: /v1/images/generations — e.g. LocalAI serving SDXL/FLUX on a GPU.
    # For an RTX 3090 (24 GB): SDXL 1.0 (default), SDXL-Turbo, or FLUX.1-schnell.
    ai_image_enabled: bool = False
    ai_image_base_url: str = "http://localhost:8080/v1"
    ai_image_api_key: str = ""
    ai_image_model: str = "sdxl"
    ai_image_size: str = "1024x1024"
    ai_image_timeout: int = 180


settings = Settings()
