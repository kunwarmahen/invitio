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


settings = Settings()
