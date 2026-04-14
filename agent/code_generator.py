# agent/code_generator.py

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Indentation levels used in the generated script
_L1 = "    "   # inside async def run_test()
_L2 = "        "  # inside async with async_playwright()
_L3 = "            "  # inside try block


def _escape(value: str) -> str:
    """Escape a string value for safe embedding in a double-quoted Python string."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


class CodeGenerator:
    """
    Converts parsed actions into a Playwright Python async test script.

    Supported action types:
        goto         — navigate to a URL
        click        — click a selector
        type         — fill a form field
        assert_text  — assert visible text exists on the page
        screenshot   — save a screenshot to a file
    """

    def generate_script(self, actions: list[dict[str, Any]]) -> str:
        header = [
            "from playwright.async_api import async_playwright",
            "import asyncio",
            "",
            "",
            "async def run_test():",
            f"{_L1}async with async_playwright() as p:",
            f"{_L2}browser = await p.chromium.launch(headless=True)",
            f"{_L2}page = await browser.new_page()",
            f"{_L2}try:",
        ]

        body = []
        for act in actions:
            lines = self._generate_action(act)
            if lines is None:
                # Unknown action — warn and emit a comment so the script still runs
                action_name = act.get("action", "<missing>")
                logger.warning("Unknown action type: %r — skipping", action_name)
                body.append(f'{_L3}# WARNING: unknown action type {action_name!r} was skipped')
            else:
                body.extend(lines)

        footer = [
            f"{_L2}finally:",
            f"{_L3}await browser.close()",
            "",
            "",
            "asyncio.run(run_test())",
        ]

        return "\n".join(header + body + footer)

    # ------------------------------------------------------------------
    # Per-action code generation
    # ------------------------------------------------------------------

    def _generate_action(self, act: dict[str, Any]) -> list[str] | None:
        """
        Return a list of source lines for one action, or None if the
        action type is unrecognised.
        """
        action = act.get("action")

        if action == "goto":
            url = _escape(act["value"])
            return [
                f'{_L3}await page.goto("{url}")',
                f'{_L3}await page.wait_for_load_state("networkidle")',
            ]

        if action == "click":
            selector = _escape(act["value"])
            return [f'{_L3}await page.click("{selector}")']

        if action == "type":
            field = _escape(act["field"])
            value = _escape(act["value"])
            return [f'{_L3}await page.fill("{field}", "{value}")']

        if action == "assert_text":
            text = _escape(act["value"])
            return [
                f'{_L3}body_text = await page.inner_text("body")',
                f'{_L3}assert "{text}" in body_text, (',
                f'{_L3}    f"Assertion failed: expected {{repr({repr(act["value"])})}} in page text"',
                f'{_L3})',
            ]

        if action == "screenshot":
            path = _escape(act.get("path", "screenshot.png"))
            return [f'{_L3}await page.screenshot(path="{path}")']

        return None  # unknown action