# agent/error_handler.py

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .config import Config


class ErrorCategory(Enum):
    """Error categories for classification."""
    TIMEOUT           = "Timeout Error"
    ELEMENT_NOT_FOUND = "Element Not Found"
    NAVIGATION_ERROR  = "Navigation Error"
    ASSERTION_ERROR   = "Assertion Failure"
    NETWORK_ERROR     = "Network Error"
    PERMISSION_ERROR  = "Permission Error"
    FILE_ERROR        = "File Operation Error"
    IFRAME_ERROR      = "Iframe Error"
    UNKNOWN           = "Unknown Error"


class ErrorHandler:
    """
    Centralized error handling with categorization, recovery strategies,
    and detailed reporting.
    """

    def __init__(self):
        self.error_history: List[Dict] = []

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def categorize_error(
        self, error: Exception, context: Optional[Dict] = None
    ) -> ErrorCategory:
        """
        Categorize *error* based on exception type and message.

        Patterns are ordered from most-specific to least-specific to avoid
        broad substring matches misclassifying errors.
        """
        error_msg = str(error).lower()
        error_type = type(error).__name__

        # Check the Python exception type first — most reliable signal
        if error_type == "AssertionError":
            return ErrorCategory.ASSERTION_ERROR
        if error_type == "TimeoutError" or "PlaywrightTimeoutError" in error_type:
            return ErrorCategory.TIMEOUT

        # Playwright-specific prefixes (more specific than generic substrings)
        if "net::" in error_msg:
            return ErrorCategory.NETWORK_ERROR
        if "frame" in error_msg and "iframe" in error_msg:
            return ErrorCategory.IFRAME_ERROR

        # Ordered substring checks — specific before generic
        if "timed out" in error_msg or "timeout" in error_msg:
            return ErrorCategory.TIMEOUT
        if "not found" in error_msg or "no such element" in error_msg:
            return ErrorCategory.ELEMENT_NOT_FOUND
        if "navigation" in error_msg:
            return ErrorCategory.NAVIGATION_ERROR
        if "permission" in error_msg or "denied" in error_msg:
            return ErrorCategory.PERMISSION_ERROR
        if "upload" in error_msg or "download" in error_msg:
            return ErrorCategory.FILE_ERROR
        if "assertion" in error_msg:
            return ErrorCategory.ASSERTION_ERROR

        return ErrorCategory.UNKNOWN

    # ------------------------------------------------------------------
    # Recovery strategies
    # ------------------------------------------------------------------

    def get_recovery_strategy(
        self, category: ErrorCategory, action: Optional[Dict] = None
    ) -> List[str]:
        """Return a list of recovery suggestions for *category*."""
        strategies: Dict[ErrorCategory, List[str]] = {
            ErrorCategory.TIMEOUT: [
                "Increase timeout duration",
                "Wait for network idle before action",
                "Check if page is still loading",
                "Verify element selector is correct",
            ],
            ErrorCategory.ELEMENT_NOT_FOUND: [
                "Use AI healing to find the correct selector",
                "Wait longer for element to appear",
                "Check if element is inside an iframe",
                "Verify page has loaded completely",
                "Try alternative selectors",
            ],
            ErrorCategory.NAVIGATION_ERROR: [
                "Check internet connection",
                "Verify URL is correct",
                "Try navigation with a different wait strategy",
                "Check for redirects or blocking popups",
            ],
            ErrorCategory.ASSERTION_ERROR: [
                "Verify the expected value is correct",
                "Check if page content has changed",
                "Wait for dynamic content to load",
                "Review test logic",
            ],
            ErrorCategory.NETWORK_ERROR: [
                "Check network connectivity",
                "Verify server is accessible",
                "Try with a longer timeout",
                "Check for CORS issues",
            ],
            ErrorCategory.PERMISSION_ERROR: [
                "Check browser permissions",
                "Verify file paths are accessible",
                "Run with appropriate privileges",
            ],
            ErrorCategory.FILE_ERROR: [
                "Verify the file path exists",
                "Check file permissions",
                "Ensure correct file format",
                "Verify upload/download directory exists",
            ],
            ErrorCategory.IFRAME_ERROR: [
                "Use frame_locator() for iframe access",
                "Wait for iframe to load",
                "Verify iframe selector is correct",
                "Check iframe cross-origin permissions",
            ],
            ErrorCategory.UNKNOWN: [
                "Review error message for clues",
                "Check browser console logs",
                "Verify test environment",
                "Try with headed mode for debugging",
            ],
        }
        return strategies.get(category, strategies[ErrorCategory.UNKNOWN])

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def handle_error(
        self, error: Exception, action: Dict, context: Optional[Dict] = None
    ) -> Dict:
        """
        Categorize *error* and return a structured error-details dict.

        Only identifying fields from *action* are stored to prevent the
        history from growing unboundedly with large payloads.
        """
        category = self.categorize_error(error, context)
        strategies = self.get_recovery_strategy(category, action)

        # Store only lightweight action metadata — not the full dict
        action_summary = {
            "action": action.get("action"),
            "value": str(action.get("value", ""))[:200],
            "field": action.get("field"),
        }

        error_details = {
            "error_message": str(error),
            "error_type": type(error).__name__,
            "category": category.value,
            "action": action_summary,
            "context": context or {},
            "recovery_strategies": strategies,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        self.error_history.append(error_details)
        return error_details

    # ------------------------------------------------------------------
    # Retry logic
    # ------------------------------------------------------------------

    def should_retry(
        self,
        error_category: ErrorCategory,
        retry_count: int,
        max_retries: int = 3,
    ) -> Tuple[bool, int]:
        """
        Determine whether to retry and how long to wait (milliseconds).

        Returns:
            (should_retry, wait_ms)
        """
        if retry_count >= max_retries:
            return False, 0

        # Base wait per category; (False, 0) means never retry
        retry_config: Dict[ErrorCategory, Tuple[bool, int]] = {
            ErrorCategory.TIMEOUT:           (True,  2000),
            ErrorCategory.ELEMENT_NOT_FOUND: (True,  1000),
            ErrorCategory.NETWORK_ERROR:     (True,  3000),
            ErrorCategory.NAVIGATION_ERROR:  (True,  2000),
            ErrorCategory.ASSERTION_ERROR:   (False,    0),  # logic errors; retrying won't help
            ErrorCategory.PERMISSION_ERROR:  (False,    0),  # environment issue; retrying won't help
            ErrorCategory.FILE_ERROR:        (True,   500),
            ErrorCategory.IFRAME_ERROR:      (True,  1000),
            ErrorCategory.UNKNOWN:           (True,  1000),
        }

        should_retry, base_wait = retry_config.get(
            error_category, (True, 1000)
        )

        if not should_retry:
            return False, 0

        if Config.EXPONENTIAL_BACKOFF:
            # retry_count starts at 1 on the first retry, so 2**1 = 2× base
            wait_ms = base_wait * (2 ** retry_count)
        else:
            wait_ms = base_wait

        return True, min(wait_ms, 10_000)  # cap at 10 seconds

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def format_error_report(self, error_details: Dict) -> str:
        """Format *error_details* into a human-readable box report."""
        width = 64
        border = "═" * width

        def row(label: str, value: str) -> str:
            content = f"{label}: {value}"
            # Truncate so the line fits inside the box (accounting for "║ " and " ║")
            max_content = width - 4
            if len(content) > max_content:
                content = content[: max_content - 1] + "…"
            return f"║ {content:<{max_content}} ║"

        lines = [
            f"╔{border}╗",
            f"║{'ERROR REPORT':^{width}}║",
            f"╠{border}╣",
            row("Category", error_details["category"]),
            row("Type",     error_details["error_type"]),
            row("Message",  error_details["error_message"]),
            row("Action",   error_details["action"].get("action", "unknown")),
            f"╠{border}╣",
            f"║ {'RECOVERY SUGGESTIONS':<{width - 2}} ║",
        ]

        for i, strategy in enumerate(error_details["recovery_strategies"], 1):
            lines.append(row(str(i), strategy))

        lines.append(f"╚{border}╝")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_error_statistics(self) -> Dict:
        """Return aggregate statistics about errors encountered so far."""
        if not self.error_history:
            return {"total_errors": 0}

        categories: Dict[str, int] = {}
        for error in self.error_history:
            cat = error["category"]
            categories[cat] = categories.get(cat, 0) + 1

        most_common = max(categories, key=lambda k: categories[k])

        return {
            "total_errors": len(self.error_history),
            "by_category": categories,
            "most_common": most_common,
        }

    def clear_history(self) -> None:
        """Clear accumulated error history."""
        self.error_history = []