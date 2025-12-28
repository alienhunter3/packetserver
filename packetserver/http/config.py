from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and .env files.
    """
    # Define your settings fields with type hints and optional default values
    name: str = "PacketServer"
    zeo_file: str
    operator: str | None = None
    debug_mode: bool = False
    log_level: str = "info"

    # Configure how settings are loaded
    model_config = SettingsConfigDict(
        case_sensitive=False,  # Make environment variable names case-sensitive
        env_prefix="PS_APP_" # Use a prefix for environment variables (e.g., MY_APP_DATABASE_URL)
    )
