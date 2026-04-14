# agent/enhanced_parser.py

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class EnhancedInstructionParser:
    """
    Advanced instruction parser with AI-powered natural language understanding,
    variable support, conditional logic, and comprehensive action types.
    """

    def __init__(self):
        self.variables: Dict[str, Any] = {}
        self.grok_api_key = os.getenv("GROK_API_KEY")
        self.grok_url = "https://api.x.ai/v1/chat/completions"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, instruction: str, use_ai: bool = True) -> List[Dict[str, Any]]:
        """
        Parse *instruction* into a list of action dicts.

        AI parsing is attempted when both *use_ai* is True and a Grok API
        key is available.  Falls back to pattern matching on any failure.
        """
        # Substitute known variables before parsing
        instruction = self.replace_variables(instruction)

        if use_ai and self.grok_api_key:
            try:
                return self._parse_with_ai(instruction)
            except Exception as exc:
                logger.warning(
                    "AI parsing failed, falling back to pattern matching: %s", exc
                )
        elif use_ai and not self.grok_api_key:
            logger.warning(
                "use_ai=True but GROK_API_KEY is not set — using pattern matching."
            )

        return self._parse_with_patterns(instruction)

    def set_variable(self, name: str, value: Any) -> None:
        self.variables[name] = value

    def get_variable(self, name: str) -> Any:
        return self.variables.get(name)

    def replace_variables(self, text: str) -> str:
        """Replace {{variable}} placeholders with stored values."""
        if not isinstance(text, str):
            return text
        for name, value in self.variables.items():
            text = text.replace(f"{{{{{name}}}}}", str(value))
        return text

    # ------------------------------------------------------------------
    # AI parsing
    # ------------------------------------------------------------------

    def _parse_with_ai(self, instruction: str) -> List[Dict[str, Any]]:
        """Use Grok AI to parse complex instructions into action dicts."""
        prompt = f"""You are an expert web automation instruction parser. Convert the following natural language instruction into a JSON array of actions.

INSTRUCTION: {instruction}

AVAILABLE ACTIONS:
- goto: Navigate to URL (value: url)
- click: Click element (value: selector)
- type: Type text (field: selector, value: text)
- hover: Hover over element (value: selector)
- select: Select dropdown option (field: selector, value: option_value OR label: option_label)
- scroll: Scroll (direction: "up"/"down"/"to_element", value: selector or pixels)
- wait: Wait for condition (condition: "element"/"text"/"time", value: selector/text/milliseconds)
- extract: Extract data (field: selector, variable: variable_name, attribute: optional)
- assert_text: Verify text exists (value: expected_text)
- assert_element: Verify element exists (value: selector)
- upload: Upload file (field: selector, value: file_path)
- download: Download file (value: trigger_selector)
- switch_tab: Switch to tab (value: tab_id or "new")
- press_key: Press keyboard key (value: key_name, field: optional_selector)
- execute_js: Execute JavaScript (value: js_code)

RULES:
1. Return ONLY a valid JSON array of action objects — no markdown, no explanations.
2. Each action must have an "action" field.
3. Use CSS selectors (preferred); text-based like button:has-text('Login') are acceptable.
4. For variables, use {{variable_name}} syntax.
5. Be specific with selectors.

EXAMPLE:
Input: "go to google.com then search for playwright"
Output: [{{"action": "goto", "value": "https://google.com"}}, {{"action": "type", "field": "input[name='q']", "value": "playwright"}}, {{"action": "press_key", "value": "Enter"}}]

Now parse this instruction:"""

        response = requests.post(
            self.grok_url,
            headers={
                "Authorization": f"Bearer {self.grok_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "grok-beta",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a JSON-only instruction parser. "
                            "Return only valid JSON arrays, no markdown."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
            },
            timeout=10,
        )
        response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"].strip()
        content = self._strip_markdown_fences(content)

        actions = json.loads(content)
        if not isinstance(actions, list):
            raise ValueError(f"AI returned non-list JSON: {type(actions)}")

        return self._normalize_actions(actions)

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """Remove markdown code fences from AI output."""
        if "```" in text:
            parts = text.split("```")
            # Content is always at odd indices (inside fence pairs)
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    cleaned = part.strip()
                    # Drop optional language tag (e.g. "json\n[...]")
                    if "\n" in cleaned:
                        cleaned = cleaned.split("\n", 1)[1].strip()
                    if cleaned:
                        return cleaned
        return text

    # ------------------------------------------------------------------
    # Pattern-based parsing
    # ------------------------------------------------------------------

    # Step splitter: "then", ". " (sentence boundary), or ";"
    _STEP_SPLITTER = re.compile(r' then |\. |; ', re.IGNORECASE)

    def _parse_with_patterns(self, instruction: str) -> List[Dict[str, Any]]:
        """Fallback pattern-based parser."""
        # Preserve original casing for quoted values; lowercase only for matching
        steps = self._STEP_SPLITTER.split(instruction)
        actions: List[Dict[str, Any]] = []

        for step in steps:
            step = step.strip()
            if not step:
                continue
            step_lower = step.lower()

            # --- NAVIGATION ---
            if any(k in step_lower for k in ["navigate", "open", "go to", "visit"]):
                url_match = re.search(r'(https?://\S+)', step)
                if url_match:
                    url = url_match.group(1)
                else:
                    # Try bare domain
                    word_match = re.search(
                        r'\b([\w-]+\.[\w.-]+)\b', step
                    )
                    url = (
                        (
                            word_match.group(1)
                            if word_match.group(1).startswith("http")
                            else f"https://{word_match.group(1)}"
                        )
                        if word_match
                        else ""
                    )
                if url:
                    actions.append({"action": "goto", "value": url})
                continue

            # --- WAIT ---
            if "wait" in step_lower:
                time_match = re.search(
                    r'(\d+)\s*(second|sec|ms|millisecond)', step_lower
                )
                if time_match:
                    value = int(time_match.group(1))
                    if time_match.group(2) in ("second", "sec"):
                        value *= 1000
                    actions.append(
                        {"action": "wait", "condition": "time", "value": value}
                    )
                elif "for" in step_lower:
                    selector = self._extract_selector_from_text(step)
                    actions.append(
                        {"action": "wait", "condition": "element", "value": selector}
                    )
                continue

            # --- SCROLL ---
            if "scroll" in step_lower:
                if "down" in step_lower or "bottom" in step_lower:
                    actions.append(
                        {"action": "scroll", "direction": "down", "value": 500}
                    )
                elif "up" in step_lower or "top" in step_lower:
                    actions.append(
                        {"action": "scroll", "direction": "up", "value": 500}
                    )
                elif "to" in step_lower:
                    selector = self._extract_selector_from_text(step)
                    actions.append(
                        {
                            "action": "scroll",
                            "direction": "to_element",
                            "value": selector,
                        }
                    )
                continue

            # --- HOVER ---
            if "hover" in step_lower:
                selector = self._extract_selector_from_text(step)
                actions.append({"action": "hover", "value": selector})
                continue

            # --- PRESS KEY (before TYPE to avoid "press enter" → type) ---
            if "press" in step_lower:
                key_match = re.search(r'press\s+(\w+)', step_lower)
                key = key_match.group(1).capitalize() if key_match else "Enter"
                actions.append({"action": "press_key", "value": key})
                continue

            # --- TYPE / FILL ---
            if any(
                k in step_lower for k in ["type", "fill", "input into", "enter"]
            ) and "press" not in step_lower:
                # Extract quoted text from the ORIGINAL step (preserve casing)
                text_match = re.findall(r'["\']([^"\']+)["\']', step)
                typed_value = text_match[0] if text_match else ""

                if not typed_value:
                    # Nothing to type — skip
                    continue

                selector = self._extract_selector_from_text(step)
                actions.append(
                    {"action": "type", "field": selector, "value": typed_value}
                )
                continue

            # --- CLICK ---
            if "click" in step_lower:
                selector = self._extract_selector_from_text(step)
                actions.append({"action": "click", "value": selector})
                continue

            # --- SELECT (dropdown) ---
            if "select" in step_lower:
                option_match = re.findall(r'["\']([^"\']+)["\']', step)
                # Try to find a field selector distinct from the option value
                selector = self._extract_selector_from_text(step) or "select"
                if option_match:
                    actions.append(
                        {
                            "action": "select",
                            "field": selector,
                            "label": option_match[0],
                        }
                    )
                continue

            # --- EXTRACT DATA ---
            # Use "extract" and "save" only — "get" is too ambiguous
            if any(k in step_lower for k in ["extract", "save"]):
                var_match = re.search(r'as\s+\{([^}]+)\}', step_lower)
                variable = var_match.group(1) if var_match else "extracted_value"
                selector = self._extract_selector_from_text(step)
                actions.append(
                    {"action": "extract", "field": selector, "variable": variable}
                )
                continue

            # --- UPLOAD FILE ---
            if "upload" in step_lower:
                file_match = re.findall(r'["\']([^"\']+)["\']', step)
                file_path = file_match[0] if file_match else ""
                actions.append(
                    {
                        "action": "upload",
                        "field": "input[type='file']",
                        "value": file_path,
                    }
                )
                continue

            # --- VERIFY / ASSERT ---
            if any(
                k in step_lower
                for k in ["verify", "assert", "check", "ensure"]
            ):
                if "element" in step_lower or "exists" in step_lower:
                    selector = self._extract_selector_from_text(step)
                    actions.append({"action": "assert_element", "value": selector})
                else:
                    # Prefer quoted text; otherwise strip assertion words
                    quoted = re.findall(r'["\']([^"\']+)["\']', step)
                    if quoted:
                        target = quoted[0]
                    else:
                        target = step_lower
                        for phrase in [
                            "verify", "assert", "check", "ensure", "that",
                            "appears", "on the page", "on page", "is visible",
                            "is displayed", "exists", "shows", "contains",
                        ]:
                            target = target.replace(phrase, " ")
                        target = " ".join(target.split()).strip()

                    if target:
                        actions.append({"action": "assert_text", "value": target})
                continue

        return actions

    # ------------------------------------------------------------------
    # Selector extraction
    # ------------------------------------------------------------------

    # Words to strip when deriving a selector from natural language.
    # Kept deliberately short — avoid stripping words that appear in labels.
    _SELECTOR_NOISE = re.compile(
        r'\b(click|hover|scroll|wait|type|fill|upload|on|the|into)\b',
        re.IGNORECASE,
    )

    def _extract_selector_from_text(self, text: str) -> str:
        """
        Derive a CSS selector from natural-language text.

        Casing is preserved for quoted strings; the rest is lowercased for
        keyword matching only.
        """
        lower = text.lower()

        # Semantic shortcuts
        if "email" in lower:
            return "input[type='email']"
        if "password" in lower:
            return "input[type='password']"
        if "search" in lower:
            return "input[placeholder*='Search'], input[name='q'], input[type='search']"

        # Quoted text → text-based selector (preserve original casing)
        quoted = re.findall(r'["\']([^"\']+)["\']', text)
        if quoted:
            return f"*:has-text('{quoted[0]}')"

        if "button" in lower:
            subject = self._SELECTOR_NOISE.sub("", lower).replace("button", "").strip()
            if subject:
                return (
                    f"button:has-text('{subject}'), "
                    f"input[type='button'][value*='{subject}']"
                )
            return "button"

        if "link" in lower:
            subject = self._SELECTOR_NOISE.sub("", lower).replace("link", "").strip()
            return f"a:has-text('{subject}')" if subject else "a"

        # Strip noise words and use what remains
        cleaned = self._SELECTOR_NOISE.sub("", lower).strip()
        return cleaned or "body"

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    def _normalize_actions(self, actions: List[Dict]) -> List[Dict]:
        """Validate and add default fields to AI-returned actions."""
        normalized: List[Dict] = []

        for action in actions:
            if not isinstance(action, dict) or "action" not in action:
                logger.warning("Skipping invalid action: %r", action)
                continue

            action_type = action["action"]

            if action_type in ("click", "hover", "assert_element", "scroll"):
                action.setdefault("value", "body")

            if action_type in ("type", "select", "upload", "extract"):
                action.setdefault("field", "input")

            normalized.append(action)

        return normalized