# agent/config.py

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _bool_env(key: str, default: bool) -> bool:
    """Read a boolean from an env var (1/true/yes → True, else → False)."""
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes")


def _int_env(key: str, default: int) -> int:
    """Read an integer from an env var, falling back to *default* on error."""
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        logger.warning("Config: env var %r is not a valid integer (%r); using default %d", key, raw, default)
        return default


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class Config:
    """
    Centralized, validated configuration for the AI Web Testing Agent.

    All values can be overridden via environment variables.  Timeouts are
    stored in milliseconds throughout (matching Playwright's convention).
    When a timeout is needed in seconds (e.g. for time.sleep), divide by
    1000 at the call site — do NOT store seconds here.

    Call Config.validate() once at startup to catch missing required values.
    """

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    GROK_API_KEY: str | None = os.getenv("GROK_API_KEY")
    GROK_API_URL: str = "https://api.x.ai/v1/chat/completions"
    GROK_MODEL: str = "grok-beta"

    # ------------------------------------------------------------------
    # Timeouts — all values in milliseconds (Playwright convention)
    # ------------------------------------------------------------------
    DEFAULT_TIMEOUT: int    = _int_env("DEFAULT_TIMEOUT",    10_000)
    NAVIGATION_TIMEOUT: int = _int_env("NAVIGATION_TIMEOUT", 30_000)
    ELEMENT_TIMEOUT: int    = _int_env("ELEMENT_TIMEOUT",     5_000)
    NETWORK_IDLE_TIMEOUT: int = _int_env("NETWORK_IDLE_TIMEOUT", 5_000)

    # ------------------------------------------------------------------
    # Retry — RETRY_DELAY is in milliseconds; divide by 1000 for time.sleep
    # ------------------------------------------------------------------
    MAX_RETRIES: int         = _int_env("MAX_RETRIES", 3)
    RETRY_DELAY_MS: int      = _int_env("RETRY_DELAY_MS", 1_000)   # milliseconds
    EXPONENTIAL_BACKOFF: bool = _bool_env("EXPONENTIAL_BACKOFF", True)

    @classmethod
    def retry_delay_seconds(cls) -> float:
        """Convenience: RETRY_DELAY_MS converted to seconds for time.sleep()."""
        return cls.RETRY_DELAY_MS / 1000.0

    # ------------------------------------------------------------------
    # Wait strategy
    # ------------------------------------------------------------------
    SMART_WAIT_ENABLED: bool    = _bool_env("SMART_WAIT_ENABLED",    True)
    WAIT_FOR_ANIMATIONS: bool   = _bool_env("WAIT_FOR_ANIMATIONS",   True)
    WAIT_FOR_NETWORK_IDLE: bool = _bool_env("WAIT_FOR_NETWORK_IDLE", True)

    # ------------------------------------------------------------------
    # AI healing
    # ------------------------------------------------------------------
    AI_HEALING_ENABLED: bool     = _bool_env("AI_HEALING_ENABLED",     True)
    VISUAL_HEALING_ENABLED: bool = _bool_env("VISUAL_HEALING_ENABLED", False)
    SELECTOR_CACHE_ENABLED: bool = _bool_env("SELECTOR_CACHE_ENABLED", True)
    MAX_HEALING_ATTEMPTS: int    = _int_env("MAX_HEALING_ATTEMPTS",    2)

    # ------------------------------------------------------------------
    # Screenshots
    # ------------------------------------------------------------------
    SCREENSHOT_ON_ERROR: bool   = _bool_env("SCREENSHOT_ON_ERROR",   True)
    SCREENSHOT_ON_SUCCESS: bool = _bool_env("SCREENSHOT_ON_SUCCESS", False)
    SCREENSHOT_EACH_STEP: bool  = _bool_env("SCREENSHOT_EACH_STEP",  False)

    # ------------------------------------------------------------------
    # Video recording
    # ------------------------------------------------------------------
    VIDEO_RECORDING_ENABLED: bool = _bool_env("VIDEO_RECORDING_ENABLED", True)
    VIDEO_DIR: str                = os.getenv("VIDEO_DIR", "tests/videos/")

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    GENERATE_HTML_REPORT: bool  = _bool_env("GENERATE_HTML_REPORT",  True)
    GENERATE_PDF_REPORT: bool   = _bool_env("GENERATE_PDF_REPORT",   True)
    GENERATE_JSON_REPORT: bool  = _bool_env("GENERATE_JSON_REPORT",  True)
    INCLUDE_CONSOLE_LOGS: bool  = _bool_env("INCLUDE_CONSOLE_LOGS",  True)
    INCLUDE_NETWORK_LOGS: bool  = _bool_env("INCLUDE_NETWORK_LOGS",  False)

    # ------------------------------------------------------------------
    # Browser
    # ------------------------------------------------------------------
    HEADLESS_MODE: bool    = _bool_env("HEADLESS_MODE", True)
    SLOW_MO: int           = _int_env("SLOW_MO", 0)          # milliseconds
    VIEWPORT_WIDTH: int    = _int_env("VIEWPORT_WIDTH",  1280)
    VIEWPORT_HEIGHT: int   = _int_env("VIEWPORT_HEIGHT",  720)

    # ------------------------------------------------------------------
    # Advanced features
    # ------------------------------------------------------------------
    IFRAME_SUPPORT: bool     = _bool_env("IFRAME_SUPPORT",     True)
    MULTI_TAB_SUPPORT: bool  = _bool_env("MULTI_TAB_SUPPORT",  True)
    FILE_UPLOAD_SUPPORT: bool = _bool_env("FILE_UPLOAD_SUPPORT", True)
    SHADOW_DOM_SUPPORT: bool = _bool_env("SHADOW_DOM_SUPPORT", True)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    # Stored as the stdlib integer level so callers can pass it directly
    # to logging.setLevel() without conversion.
    LOG_LEVEL: int       = logging.getLevelName(os.getenv("LOG_LEVEL", "INFO").upper())
    VERBOSE_LOGGING: bool = _bool_env("VERBOSE_LOGGING", False)

    # ------------------------------------------------------------------
    # Action → timeout mapping
    # ------------------------------------------------------------------

    @classmethod
    def get_timeout(cls, action_type: str) -> int:
        """Return the timeout (ms) for a given action type."""
        timeout_map = {
            "goto":     cls.NAVIGATION_TIMEOUT,
            "click":    cls.ELEMENT_TIMEOUT,
            "type":     cls.ELEMENT_TIMEOUT,
            "wait":     cls.DEFAULT_TIMEOUT,
            "upload":   cls.NAVIGATION_TIMEOUT,
            "download": cls.NAVIGATION_TIMEOUT,
        }
        return timeout_map.get(action_type, cls.DEFAULT_TIMEOUT)

    # ------------------------------------------------------------------
    # Validation — call once at startup
    # ------------------------------------------------------------------

    @classmethod
    def validate(cls) -> bool:
        """
        Validate configuration and log warnings for non-fatal issues.

        Returns True if the configuration is fully valid, False if any
        non-fatal problems were found (so callers can decide whether to
        abort or continue with degraded functionality).

        Does NOT mutate class attributes — runtime overrides belong in
        application startup code, not here.
        """
        valid = True

        if not cls.GROK_API_KEY and cls.AI_HEALING_ENABLED:
            logger.warning(
                "GROK_API_KEY is not set but AI_HEALING_ENABLED is True. "
                "Set AI_HEALING_ENABLED=false in your environment or provide "
                "the key to suppress this warning."
            )
            valid = False

        if cls.VIDEO_RECORDING_ENABLED:
            video_path = Path(cls.VIDEO_DIR)
            if not video_path.exists():
                logger.info("VIDEO_DIR %r does not exist — creating it.", cls.VIDEO_DIR)
                video_path.mkdir(parents=True, exist_ok=True)

        if not isinstance(cls.LOG_LEVEL, int):
            logger.warning(
                "LOG_LEVEL resolved to a non-integer (%r). "
                "Check that LOG_LEVEL env var is a valid level name (DEBUG, INFO, WARNING, ERROR).",
                cls.LOG_LEVEL,
            )
            valid = False

        return valid