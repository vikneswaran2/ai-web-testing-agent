# agent/enhanced_executor.py

import asyncio
import logging
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from .advanced_actions import (
    DataExtractor,
    FileHandler,
    InteractionHandler,
    IframeHandler,
    ScrollManager,
    TabManager,
)
from .ai_selector import AISelectorHealer
from .config import Config
from .error_handler import ErrorCategory, ErrorHandler
from .smart_waits import SmartWait

logger = logging.getLogger(__name__)


class EnhancedExecutor:
    """
    Enhanced executor with support for complex actions, intelligent error
    handling, and advanced web interactions.
    """

    def __init__(self):
        self.wait = SmartWait()
        self.healer = AISelectorHealer(use_cache=True)
        self.error_handler = ErrorHandler()
        self.tab_manager = TabManager()
        self.variables: Dict[str, Any] = {}

        Config.validate()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute_actions(
        self, actions: List[Dict], settings: Optional[Dict] = None
    ) -> Dict:
        """Execute a list of actions with enhanced error handling and recovery."""
        settings = settings or {}

        is_headless = settings.get("headless", Config.HEADLESS_MODE)
        global_timeout = settings.get("timeout", Config.DEFAULT_TIMEOUT)
        slow_mo = 0 if is_headless else Config.SLOW_MO

        # Must be set before sync_playwright starts on Windows
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        logs: List[str] = []
        screenshots: List[str] = []
        video_path: Optional[str] = None
        console_logs: List[str] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=is_headless, slow_mo=slow_mo)
            context = browser.new_context(
                record_video_dir=(
                    Config.VIDEO_DIR if Config.VIDEO_RECORDING_ENABLED else None
                ),
                viewport={
                    "width": Config.VIEWPORT_WIDTH,
                    "height": Config.VIEWPORT_HEIGHT,
                },
            )
            page = context.new_page()

            if Config.INCLUDE_CONSOLE_LOGS:
                page.on(
                    "console",
                    lambda msg: console_logs.append(
                        f"[CONSOLE] {msg.type}: {msg.text}"
                    ),
                )

            if not is_headless:
                page.bring_to_front()

            page.set_default_timeout(global_timeout)

            def _build_result(success: bool) -> Dict:
                # Video file is only complete after context.close()
                nonlocal video_path
                context.close()
                browser.close()
                if page.video:
                    video_path = page.video.path()
                result = {
                    "success": success,
                    "logs": logs,
                    "screenshots": screenshots,
                    "video": video_path,
                    "console_logs": (
                        console_logs if Config.INCLUDE_CONSOLE_LOGS else []
                    ),
                    "error_stats": self.error_handler.get_error_statistics(),
                }
                if success:
                    result["variables"] = self.variables
                    result["healing_stats"] = self.healer.get_healing_stats()
                return result

            for i, act in enumerate(actions):
                action_type = act.get("action", "unknown")
                logs.append(f"\n[STEP {i + 1}] Executing: {action_type}")

                success, action_logs, action_screenshots = (
                    self._execute_single_action(page, act, global_timeout, settings)
                )
                logs.extend(action_logs)
                screenshots.extend(action_screenshots)

                if not success:
                    self._capture_screenshot(page, logs, screenshots, label="error")
                    return _build_result(False)

                if Config.SCREENSHOT_EACH_STEP:
                    self._capture_screenshot(
                        page, logs, screenshots, label=f"step_{i + 1}"
                    )

            if Config.SCREENSHOT_ON_SUCCESS:
                self._capture_screenshot(page, logs, screenshots, label="success")
                logs.append(
                    f"[SUCCESS] All {len(actions)} actions completed successfully"
                )

            return _build_result(True)

    # ------------------------------------------------------------------
    # Retry wrapper
    # ------------------------------------------------------------------

    def _execute_single_action(
        self, page: Page, action: Dict, timeout: int, settings: Dict
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Execute a single action with retry logic.

        Returns (success, logs, screenshots).
        """
        logs: List[str] = []
        screenshots: List[str] = []
        action_type = action.get("action")
        max_retries = Config.MAX_RETRIES

        for attempt in range(1, max_retries + 1):
            try:
                action_logs = self._perform_action(page, action, timeout)
                logs.extend(action_logs)

                if Config.SMART_WAIT_ENABLED:
                    self.wait.smart_wait_after_action(page, action_type)

                return True, logs, screenshots

            except Exception as exc:
                error_details = self.error_handler.handle_error(
                    exc,
                    action,
                    context={"page_url": page.url, "retry_count": attempt},
                )
                category = ErrorCategory(error_details["category"])
                should_retry, wait_ms = self.error_handler.should_retry(
                    category, attempt, max_retries
                )

                is_last_attempt = attempt == max_retries
                if should_retry and not is_last_attempt:
                    logs.append(
                        f"[RETRY {attempt}/{max_retries}] "
                        f"{error_details['category']}: {str(exc)[:100]}"
                    )
                    if wait_ms > 0:
                        time.sleep(wait_ms / 1000.0)
                else:
                    logs.append(f"[ERROR] {error_details['category']}: {exc}")
                    logs.append(
                        f"[SUGGESTIONS] "
                        f"{', '.join(error_details['recovery_strategies'][:2])}"
                    )
                    return False, logs, screenshots

        # Should be unreachable, but satisfies type checkers
        return False, logs, screenshots

    # ------------------------------------------------------------------
    # Action dispatcher
    # ------------------------------------------------------------------

    def _perform_action(self, page: Page, action: Dict, timeout: int) -> List[str]:
        """Dispatch and perform a single action; return log lines."""
        logs: List[str] = []
        action_type = action.get("action")
        action_timeout = Config.get_timeout(action_type)

        # --- NAVIGATION ---
        if action_type == "goto":
            url = self._replace_variables(action.get("value", ""))
            page.goto(url, timeout=action_timeout, wait_until="domcontentloaded")
            self.wait.wait_dom_ready(page)
            self.wait.wait_network_idle(page)
            logs.append(f"[OK] Navigated to {url}")

        # --- CLICK ---
        elif action_type == "click":
            selector = self._replace_variables(action.get("value", ""))

            if not self.wait.wait_for_element_clickable(
                page, selector, timeout=action_timeout
            ):
                selector = self._try_heal(
                    page, selector, f"click {selector}", logs
                )

            page.click(selector, timeout=action_timeout)
            logs.append(f"[OK] Clicked: {selector}")

        # --- TYPE ---
        elif action_type == "type":
            selector = self._replace_variables(action.get("field", "input"))
            value = self._replace_variables(action.get("value", ""))

            if not self.wait.wait_for_element(
                page, selector, timeout=action_timeout
            ):
                selector = self._try_heal(
                    page, selector, f"type '{value}' into {selector}", logs
                )

            try:
                page.fill(selector, value, timeout=action_timeout)
                logs.append(f"[OK] Typed '{value}' into {selector}")
            except Exception:
                page.click(selector)
                page.keyboard.type(value)
                logs.append(f"[FALLBACK] Typed '{value}' using keyboard")

        # --- HOVER ---
        elif action_type == "hover":
            selector = self._replace_variables(action.get("value", ""))
            InteractionHandler.hover(page, selector, timeout=action_timeout)
            logs.append(f"[OK] Hovered over: {selector}")

        # --- SELECT ---
        elif action_type == "select":
            selector = action.get("field", "select")
            value = action.get("value")
            label = action.get("label")
            if value is None and label is None:
                raise ValueError(
                    f"'select' action on '{selector}' requires 'value' or 'label'."
                )
            InteractionHandler.select_option(
                page, selector, value=value, label=label, timeout=action_timeout
            )
            logs.append(f"[OK] Selected option in: {selector}")

        # --- SCROLL ---
        elif action_type == "scroll":
            direction = action.get("direction", "down")
            value = action.get("value", 500)
            if direction == "to_element":
                ScrollManager.scroll_to_element(page, str(value))
                logs.append(f"[OK] Scrolled to element: {value}")
            elif direction == "down":
                ScrollManager.scroll_by_pixels(page, y=int(value))
                logs.append(f"[OK] Scrolled down {value}px")
            elif direction == "up":
                ScrollManager.scroll_by_pixels(page, y=-int(value))
                logs.append(f"[OK] Scrolled up {value}px")
            else:
                logs.append(f"[WARNING] Unknown scroll direction: {direction}")

        # --- WAIT ---
        elif action_type == "wait":
            condition = action.get("condition", "time")
            value = action.get("value", 1000)
            if condition == "time":
                time.sleep(int(value) / 1000.0)
                logs.append(f"[WAIT] Waited {value}ms")
            elif condition == "element":
                self.wait.wait_for_element(
                    page, str(value), timeout=action_timeout
                )
                logs.append(f"[WAIT] Waited for element: {value}")
            elif condition == "text":
                self.wait.wait_for_text(page, str(value), timeout=action_timeout)
                logs.append(f"[WAIT] Waited for text: {value}")
            else:
                logs.append(f"[WARNING] Unknown wait condition: {condition}")

        # --- EXTRACT ---
        elif action_type == "extract":
            selector = action.get("field", "")
            variable = action.get("variable", "extracted_value")
            attribute = action.get("attribute")
            extracted = (
                DataExtractor.extract_attribute(page, selector, attribute)
                if attribute
                else DataExtractor.extract_text(page, selector)
            )
            self.variables[variable] = extracted
            logs.append(f"[EXTRACT] Saved '{extracted}' as {{{variable}}}")

        # --- UPLOAD ---
        elif action_type == "upload":
            selector = action.get("field", "input[type='file']")
            file_path = self._replace_variables(action.get("value", ""))
            FileHandler.upload_file(page, selector, file_path, timeout=action_timeout)
            logs.append(f"[OK] Uploaded file: {file_path}")

        # --- PRESS KEY ---
        elif action_type == "press_key":
            key = action.get("value", "Enter")
            selector = action.get("field")
            InteractionHandler.press_key(page, key, selector=selector)
            logs.append(f"[OK] Pressed key: {key}")

        # --- ASSERT TEXT ---
        elif action_type == "assert_text":
            expected = self._replace_variables(action.get("value", ""))
            logs.append(f"[CHECK] Verifying text: '{expected}'...")
            if self.wait.wait_for_text(page, expected, timeout=action_timeout):
                logs.append(f"[ASSERT OK] Found text: '{expected}'")
            else:
                raise AssertionError(
                    f"Expected text not found: '{expected}' after {action_timeout}ms"
                )

        # --- ASSERT ELEMENT ---
        elif action_type == "assert_element":
            selector = self._replace_variables(action.get("value", ""))
            if self.wait.wait_for_element(page, selector, timeout=action_timeout):
                logs.append(f"[ASSERT OK] Element exists: {selector}")
            else:
                raise AssertionError(f"Element not found: {selector}")

        # --- EXECUTE JS ---
        elif action_type == "execute_js":
            js_code = action.get("value", "")
            result = page.evaluate(js_code)
            result_preview = repr(result)[:200]
            logs.append(f"[JS] Executed JavaScript, result: {result_preview}")

        else:
            logs.append(f"[WARNING] Unknown action type: {action_type}")

        return logs

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _try_heal(
        self, page: Page, selector: str, action_hint: str, logs: List[str]
    ) -> str:
        """
        Attempt AI healing for a selector.  Returns the healed selector if
        healing succeeded, or the original selector if it did not, so the
        caller always gets a usable string.
        """
        if not Config.AI_HEALING_ENABLED:
            return selector

        logs.append(f"[AI HEALING] Attempting to heal selector: {selector}")
        healed = self.healer.heal(
            page.content(),
            selector,
            action_hint,
            page_url=page.url,
            page_title=page.title(),
        )
        if healed:
            logs.append(f"[AI HEAL] {selector} → {healed}")
            return healed

        logs.append("[AI HEAL] Healing failed — retrying with original selector")
        return selector

    def _capture_screenshot(
        self,
        page: Page,
        logs: List[str],
        screenshots: List[str],
        label: str = "screenshot",
    ) -> None:
        """Take a screenshot and append the path to logs and screenshots."""
        path = f"tests/screenshots/{label}_{uuid.uuid4()}.png"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            page.screenshot(path=path, timeout=3000, animations="disabled")
            screenshots.append(path)
            logs.append(f"[SCREENSHOT] {path}")
        except Exception:
            logger.exception("Failed to capture screenshot")
            logs.append(f"[SCREENSHOT FAILED] Could not capture {label} screenshot")

    def _replace_variables(self, text: str) -> str:
        """Replace {{variable}} placeholders with stored values."""
        if not isinstance(text, str):
            return text
        for name, value in self.variables.items():
            text = text.replace(f"{{{{{name}}}}}", str(value))
        return text