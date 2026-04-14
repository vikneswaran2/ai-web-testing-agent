# agent/executor.py

import asyncio
import logging
import os
import sys
import time
import uuid
from typing import Dict, List, Optional, Tuple

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from .ai_selector import AISelectorHealer
from .config import Config
from .smart_waits import SmartWait

logger = logging.getLogger(__name__)


class Executor:
    """
    Basic Playwright executor with heuristic and AI-powered selector healing.
    For advanced features (retry strategies, reporting, video config) use
    EnhancedExecutor instead.
    """

    def __init__(self):
        self.wait = SmartWait()
        # Single healer instance preserves the selector cache across actions.
        self._healer = AISelectorHealer(use_cache=True)

    # ------------------------------------------------------------------
    # Selector healing
    # ------------------------------------------------------------------

    def heal_selector(
        self, page: Page, selector: str, action_hint: str = "perform action"
    ) -> Tuple[str, str]:
        """
        Attempt to find a working replacement for *selector*.

        Strategies tried in order:
          1. Heuristic alternatives (quote style, tag swaps, common inputs)
          2. AI-powered DOM analysis (Grok)

        Returns:
            (selector, mode) where mode is "HEURISTIC", "AI", or "NONE".
        """
        # --- Strategy 1: heuristic alternatives ---
        alternatives = [
            selector,
            selector.replace("input", "textarea"),
            selector.replace("textarea", "input"),
            selector.replace("'", '"'),
            selector.replace('"', "'"),
            "input[type='text']",
            "textarea",
            "input",
        ]

        for alt in alternatives:
            try:
                page.wait_for_selector(alt, timeout=2000)
                if alt != selector:
                    logger.debug("Heuristic healed %r → %r", selector, alt)
                return alt, "HEURISTIC"
            except Exception:
                pass

        # --- Strategy 2: AI healing ---
        try:
            healed = self._healer.heal(
                page.content(), selector, action_hint,
                page_url=page.url, page_title=page.title()
            )
            if healed:
                logger.debug("AI healed %r → %r", selector, healed)
                return healed, "AI"
        except Exception:
            logger.exception("AI healing failed for selector %r", selector)

        return selector, "NONE"

    # ------------------------------------------------------------------
    # Main execution loop
    # ------------------------------------------------------------------

    def execute_actions(
        self, actions: List[Dict], settings: Optional[Dict] = None
    ) -> Dict:
        """Execute *actions* and return a result dict."""
        settings = settings or {}

        is_headless = settings.get("headless", Config.HEADLESS_MODE)
        global_timeout = settings.get("timeout", Config.DEFAULT_TIMEOUT)
        slow_mo = 0 if is_headless else Config.SLOW_MO

        # Must be set before sync_playwright starts on Windows.
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        logs: List[str] = []
        screenshots: List[str] = []
        video_path: Optional[str] = None

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

            if not is_headless:
                page.bring_to_front()

            page.set_default_timeout(global_timeout)

            def _close_and_collect_video() -> Optional[str]:
                """Close context/browser and return the finalised video path."""
                nonlocal video_path
                # context.close() must be called BEFORE reading .path() so
                # Playwright can finalise the video file.
                context.close()
                browser.close()
                if page.video:
                    video_path = page.video.path()
                return video_path

            def _build_result(success: bool) -> Dict:
                return {
                    "success": success,
                    "logs": logs,
                    "screenshots": screenshots,
                    "video": _close_and_collect_video(),
                }

            for act in actions:
                max_retries = 1
                action_success = False

                for attempt in range(1, max_retries + 1):
                    try:
                        self._perform_action(page, act, global_timeout, logs)
                        action_success = True
                        break

                    except Exception as exc:
                        if attempt < max_retries:
                            logs.append(
                                f"[RETRY] Retrying action due to: {str(exc)[:50]}…"
                            )
                            time.sleep(1)
                        else:
                            self._capture_screenshot(page, logs, screenshots)
                            logs.append(f"[ERROR] {exc}")
                            return _build_result(False)

            return _build_result(True)

    # ------------------------------------------------------------------
    # Per-action dispatch
    # ------------------------------------------------------------------

    def _perform_action(
        self, page: Page, act: Dict, timeout: int, logs: List[str]
    ) -> None:
        """Dispatch and execute a single action."""
        action_type = act.get("action")

        # --- GOTO ---
        if action_type == "goto":
            url = act["value"]
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            self.wait.wait_dom_ready(page)
            self.wait.wait_network_idle(page)
            logs.append(f"[OK] Navigated to {url}")
            logs.append("[WAIT] DOM ready & network idle")

        # --- CLICK ---
        elif action_type == "click":
            selector = act["value"]
            if not self.wait.wait_for_element(page, selector, timeout=timeout):
                selector, mode = self.heal_selector(
                    page, selector, action_hint=f"click {selector}"
                )
                logs.append(f"[{mode} HEAL] Click selector → {selector}")
            page.click(selector, timeout=timeout)
            logs.append(f"[OK] Clicked {selector}")

        # --- TYPE ---
        elif action_type == "type":
            selector = act["field"]
            value = act["value"]
            if not self.wait.wait_for_element(page, selector, timeout=timeout):
                selector, mode = self.heal_selector(
                    page, selector,
                    action_hint=f"type '{value}' into {selector}"
                )
                logs.append(f"[{mode} HEAL] Type selector → {selector}")
            try:
                page.fill(selector, value, timeout=timeout)
                logs.append(f"[OK] Typed '{value}'")
            except Exception:
                page.click(selector)
                page.keyboard.type(value)
                logs.append(f"[FALLBACK] Typed '{value}' using keyboard")

        # --- ASSERT TEXT ---
        elif action_type == "assert_text":
            expected = act["value"].lower()
            # Wait for DOM to settle before asserting
            self.wait.wait_dom_ready(page)
            content = page.inner_text("body").lower()
            if expected in content:
                logs.append(f"[ASSERT OK] Found text: {expected}")
            else:
                raise AssertionError(f"Expected text not found: '{expected}'")

        else:
            logs.append(f"[WARNING] Unknown action type: {action_type!r}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _capture_screenshot(
        self, page: Page, logs: List[str], screenshots: List[str]
    ) -> None:
        path = f"tests/screenshots/error_{uuid.uuid4()}.png"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            page.screenshot(path=path, timeout=3000, animations="disabled")
            screenshots.append(path)
            logs.append(f"[SCREENSHOT] {path}")
        except Exception:
            logger.exception("Failed to capture error screenshot")
            logs.append("[SCREENSHOT FAILED] Could not capture screenshot")