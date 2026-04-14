# agent/ai_selector.py

import logging
import os
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .selector_cache import SelectorCache

logger = logging.getLogger(__name__)

GROK_URL = "https://api.x.ai/v1/chat/completions"

# Basic sanity-check pattern: must start with a CSS-valid character
_VALID_SELECTOR_RE = re.compile(r'^[#.\[\w:*]')


class AISelectorHealer:
    """
    AI-powered selector healing with caching, semantic fallback,
    and selector validation.
    """

    def __init__(self, use_cache: bool = True):
        self.cache = SelectorCache() if use_cache else None
        self.healing_history = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def heal(
        self,
        html_content: str,
        failed_selector: str,
        action_hint: str,
        page_url: str = "",
        page_title: str = "",
    ) -> Optional[str]:
        """
        Attempt to find a working replacement for *failed_selector*.

        Returns the healed selector on success, or None if every strategy
        failed (callers can then decide whether to fall back to the original
        or raise an error).
        """
        # Lazy API key check — supports load_dotenv called after import
        api_key = os.getenv("GROK_API_KEY")
        if not api_key:
            logger.warning("GROK_API_KEY not set — skipping AI healing.")
            return None

        # Cache hit
        if self.cache:
            cached = self.cache.get(page_url, failed_selector, action_hint)
            if cached:
                logger.debug("Cache hit: %s", cached)
                self._record(failed_selector, cached, action_hint, success=True)
                return cached

        healed: Optional[str] = None

        # Strategy 1 — AI with enriched context
        healed = self._heal_with_ai_enhanced(
            html_content, failed_selector, action_hint, page_url, page_title, api_key
        )

        # Strategy 2 — lightweight semantic analysis (no API call)
        if not healed:
            healed = self._heal_with_semantic_analysis(
                html_content, failed_selector, action_hint
            )

        success = bool(healed and healed != failed_selector)

        if success and self.cache:
            self.cache.set(
                page_url, failed_selector, action_hint, healed, "AI"
            )

        self._record(failed_selector, healed, action_hint, success=success)
        return healed if success else None

    def get_healing_stats(self) -> dict:
        """Return cumulative healing statistics."""
        total = len(self.healing_history)
        if total == 0:
            return {"total": 0, "success_rate": 0}
        successful = sum(1 for h in self.healing_history if h["success"])
        return {
            "total_healings": total,
            "successful": successful,
            "success_rate": round((successful / total) * 100, 1),
            "cache_stats": self.cache.get_stats() if self.cache else None,
        }

    # ------------------------------------------------------------------
    # Strategy 1 — AI healing
    # ------------------------------------------------------------------

    def _heal_with_ai_enhanced(
        self,
        html_content: str,
        failed_selector: str,
        action_hint: str,
        page_url: str,
        page_title: str,
        api_key: str,
    ) -> Optional[str]:
        relevant_html = self._extract_relevant_html(html_content, action_hint)

        prompt = f"""You are an expert CSS selector generator for web automation.

CONTEXT:
- Page URL: {page_url or 'Unknown'}
- Page Title: {page_title or 'Unknown'}
- Failed Selector: {failed_selector}
- Intended Action: {action_hint}

HTML SNIPPET (interactive elements only):
{relevant_html[:8000]}

TASK:
Generate the MOST STABLE CSS selector for the element that matches the intended action.

SELECTOR PRIORITY (use in this order):
1. ID attributes — #submit-button
2. Unique data-* attributes — [data-testid="login"]
3. Unique name attributes — input[name="email"]
4. Unique class combinations — .btn.btn-primary
5. Text-based — button:has-text("Login")
6. Structural — form > button[type="submit"]

RULES:
- Return ONLY the selector, no explanation, no markdown.
- Prefer shorter, more stable selectors.
- Avoid nth-child unless nothing else works.
- Selector must match exactly one element.

SELECTOR:"""

        try:
            response = requests.post(
                GROK_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "grok-beta",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a CSS selector expert. "
                                "Return only the raw selector string, nothing else."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                },
                timeout=15,
            )
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"].strip()
            selector = self._clean_selector(raw)

            if not self._is_valid_selector(selector):
                logger.warning("AI returned an invalid-looking selector: %r", selector)
                return None

            return selector

        except requests.exceptions.Timeout:
            logger.warning("AI healing timed out after 15s for selector: %r", failed_selector)
            return None
        except Exception:
            logger.exception("AI healing error")
            return None

    # ------------------------------------------------------------------
    # Strategy 2 — Semantic analysis (BeautifulSoup, no API)
    # ------------------------------------------------------------------

    def _heal_with_semantic_analysis(
        self, html_content: str, failed_selector: str, action_hint: str
    ) -> Optional[str]:
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            hint = action_hint.lower()

            if "click" in hint:
                tag_filter = ["button", "a", "input"]
            elif "type" in hint or "fill" in hint:
                tag_filter = ["input", "textarea"]
            elif "select" in hint:
                tag_filter = ["select"]
            else:
                tag_filter = ["button", "a", "input", "textarea", "select"]

            candidates = soup.find_all(tag_filter)

            best_selector: Optional[str] = None
            best_score = -1

            for element in candidates[:20]:
                score, selector = self._score_element(element, hint)
                if selector and score > best_score:
                    best_score = score
                    best_selector = selector

            return best_selector

        except Exception:
            logger.exception("Semantic analysis error")
            return None

    def _score_element(self, element, action_hint: str = "") -> tuple:
        """Return (score, selector) for a BeautifulSoup element.
        Boosts score when element text/id/name matches keywords in action_hint.
        """
        hint_words = set(action_hint.lower().split())
        element_text = element.get_text(strip=True).lower()
        element_id = (element.get("id") or "").lower()
        element_name = (element.get("name") or "").lower()

        # Keyword relevance bonus — boosts elements that match the action hint
        relevance = 0
        for word in hint_words:
            if len(word) > 3:  # skip short words like "the", "click"
                if word in element_text or word in element_id or word in element_name:
                    relevance += 3

        if element.get("id"):
            return 10 + relevance, f"#{element['id']}"

        data_attrs = [a for a in element.attrs if a.startswith("data-")]
        if data_attrs:
            attr = data_attrs[0]
            return 8 + relevance, f"[{attr}='{element[attr]}']"

        if element.get("name"):
            return 7 + relevance, f"{element.name}[name='{element['name']}']"

        text = element.get_text(strip=True)
        if element.name in ("button", "a") and text:
            return 6 + relevance, f"{element.name}:has-text('{text[:30]}')"

        classes = element.get("class")
        if classes:
            cls = ".".join(classes[:2])
            return 5 + relevance, f"{element.name}.{cls}"

        return 1 + relevance, element.name

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_relevant_html(self, html_content: str, action_hint: str) -> str:
        """Strip noise and return interactive-element HTML only."""
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()

            interactive = soup.find_all(
                ["button", "a", "input", "textarea", "select", "form"]
            )
            parts = []
            for elem in interactive[:50]:
                # Send the element itself, not the parent, to avoid oversized/malformed HTML
                parts.append(str(elem)[:300])
            return "\n".join(parts)

        except Exception:
            logger.exception("HTML extraction error")
            return html_content[:10000]

    @staticmethod
    def _clean_selector(raw: str) -> str:
        """
        Strip markdown fences, surrounding quotes, and extra lines from an
        AI-generated selector string.
        """
        if "```" in raw:
            parts = raw.split("```")
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    cleaned = part.strip()
                    if "\n" in cleaned:
                        cleaned = cleaned.split("\n", 1)[1].strip()
                    if cleaned:
                        raw = cleaned
                        break

        for line in raw.splitlines():
            line = line.strip().strip("\"'")
            if line:
                return line.replace('"', "'")

        return raw.strip().strip("\"'").replace('"', "'")

    @staticmethod
    def _is_valid_selector(selector: str) -> bool:
        """Lightweight check that the selector string looks plausible."""
        if not selector or len(selector) > 500:
            return False
        return bool(_VALID_SELECTOR_RE.match(selector))

    def _record(
        self,
        failed: str,
        healed: Optional[str],
        action: str,
        success: bool,
    ) -> None:
        self.healing_history.append(
            {
                "failed": failed,
                "healed": healed,
                "action": action,
                "success": success,
            }
        )