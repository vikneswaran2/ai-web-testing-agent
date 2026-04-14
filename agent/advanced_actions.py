# agent/advanced_actions.py

import logging
import os
import time
from typing import Any, Dict, List, Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)


class IframeHandler:
    """Handle iframe interactions."""

    @staticmethod
    def find_and_switch_to_iframe(
        page: Page, iframe_selector: Optional[str] = None
    ) -> Optional[Any]:
        """Find and switch to iframe context."""
        try:
            if iframe_selector:
                return page.frame_locator(iframe_selector)
            frames = page.frames
            if len(frames) > 1:
                return frames[1]  # First non-main frame
            return None
        except Exception:
            logger.exception("Iframe switch error")
            return None

    @staticmethod
    def execute_in_iframe(page: Page, iframe_selector: str, action_callback):
        """Execute action within iframe context."""
        try:
            frame_locator = page.frame_locator(iframe_selector)
            return action_callback(frame_locator)
        except Exception:
            logger.exception("Iframe execution error")
            return None


class FileHandler:
    """Handle file uploads and downloads."""

    @staticmethod
    def upload_file(
        page: Page, selector: str, file_path: str, timeout: int = 5000
    ) -> bool:
        """Upload file to input element."""
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            page.wait_for_selector(selector, timeout=timeout)
            page.set_input_files(selector, file_path)
            return True
        except Exception:
            logger.exception("File upload error")
            return False

    @staticmethod
    def download_file(
        page: Page, trigger_selector: str, timeout: int = 30000
    ) -> Optional[str]:
        """Trigger download and wait for completion."""
        try:
            with page.expect_download(timeout=timeout) as download_info:
                page.click(trigger_selector)
            download = download_info.value
            download_path = f"tests/downloads/{download.suggested_filename}"
            os.makedirs(os.path.dirname(download_path), exist_ok=True)
            download.save_as(download_path)
            return download_path
        except Exception:
            logger.exception("File download error")
            return None


class TabManager:
    """Manage multiple tabs and windows."""

    def __init__(self):
        self.tabs: Dict[str, Page] = {}
        self.current_tab_id: Optional[str] = None

    def open_new_tab(
        self, context, url: Optional[str] = None, tab_id: Optional[str] = None
    ) -> str:
        """Open new tab and optionally navigate to URL."""
        new_page = context.new_page()
        if not tab_id:
            tab_id = f"tab_{len(self.tabs) + 1}"
        self.tabs[tab_id] = new_page
        self.current_tab_id = tab_id
        if url:
            new_page.goto(url)
        return tab_id

    def switch_to_tab(self, tab_id: str) -> Optional[Page]:
        """Switch to specific tab."""
        if tab_id in self.tabs:
            self.current_tab_id = tab_id
            page = self.tabs[tab_id]
            page.bring_to_front()
            return page
        logger.warning("Tab '%s' not found", tab_id)
        return None

    def close_tab(self, tab_id: str) -> None:
        """Close specific tab."""
        if tab_id not in self.tabs:
            logger.warning("Tab '%s' not found", tab_id)
            return

        self.tabs[tab_id].close()
        del self.tabs[tab_id]

        if self.current_tab_id == tab_id:
            # Fall back to the first remaining tab, or None if all closed
            remaining = list(self.tabs.keys())
            self.current_tab_id = remaining[0] if remaining else None
            if self.current_tab_id:
                self.tabs[self.current_tab_id].bring_to_front()

    def get_current_tab(self) -> Optional[Page]:
        """Get current active tab."""
        if self.current_tab_id and self.current_tab_id in self.tabs:
            return self.tabs[self.current_tab_id]
        return None


class DataExtractor:
    """Extract data from web pages."""

    @staticmethod
    def extract_text(page: Page, selector: str) -> Optional[str]:
        """Extract text from element."""
        try:
            element = page.query_selector(selector)
            return element.inner_text() if element else None
        except Exception:
            logger.exception("Text extraction error")
            return None

    @staticmethod
    def extract_attribute(
        page: Page, selector: str, attribute: str
    ) -> Optional[str]:
        """Extract attribute value from element."""
        try:
            element = page.query_selector(selector)
            return element.get_attribute(attribute) if element else None
        except Exception:
            logger.exception("Attribute extraction error")
            return None

    @staticmethod
    def extract_multiple(
        page: Page, selector: str, attribute: Optional[str] = None
    ) -> List[str]:
        """Extract data from multiple elements."""
        try:
            elements = page.query_selector_all(selector)
            results = []
            for element in elements:
                value = (
                    element.get_attribute(attribute)
                    if attribute
                    else element.inner_text()
                )
                if value:
                    results.append(value)
            return results
        except Exception:
            logger.exception("Multiple extraction error")
            return []

    @staticmethod
    def extract_table(page: Page, table_selector: str) -> List[Dict[str, str]]:
        """Extract data from HTML table."""
        try:
            headers = [
                h.inner_text().strip()
                for h in page.query_selector_all(f"{table_selector} th")
            ]
            rows = []
            for row_element in page.query_selector_all(
                f"{table_selector} tbody tr"
            ):
                cells = row_element.query_selector_all("td")
                row_data = {
                    (headers[i] if i < len(headers) else f"column_{i}"): cell.inner_text().strip()
                    for i, cell in enumerate(cells)
                }
                rows.append(row_data)
            return rows
        except Exception:
            logger.exception("Table extraction error")
            return []


class ScrollManager:
    """Handle scrolling strategies."""

    @staticmethod
    def scroll_to_element(page: Page, selector: str) -> bool:
        """Scroll element into view."""
        try:
            element = page.query_selector(selector)
            if element:
                element.scroll_into_view_if_needed()
                return True
            return False
        except Exception:
            logger.exception("Scroll to element error")
            return False

    @staticmethod
    def scroll_by_pixels(page: Page, x: int = 0, y: int = 0) -> bool:
        """Scroll by specific pixel amount."""
        try:
            page.evaluate(f"window.scrollBy({x}, {y})")
            return True
        except Exception:
            logger.exception("Scroll by pixels error")
            return False

    @staticmethod
    def scroll_to_bottom(
        page: Page, smooth: bool = True, max_iterations: int = 200
    ) -> bool:
        """
        Scroll to bottom of page.

        Args:
            page: Playwright page.
            smooth: If True, scrolls incrementally (handles lazy-loading).
            max_iterations: Safety cap to prevent infinite loops when the page
                            keeps growing (e.g., infinite-scroll feeds).
        """
        try:
            if smooth:
                step = 300
                iterations = 0
                while iterations < max_iterations:
                    current_position = page.evaluate("window.pageYOffset")
                    total_height = page.evaluate("document.body.scrollHeight")
                    if current_position + page.evaluate("window.innerHeight") >= total_height:
                        break
                    page.evaluate(f"window.scrollBy(0, {step})")
                    time.sleep(0.1)
                    iterations += 1
                if iterations >= max_iterations:
                    logger.warning(
                        "scroll_to_bottom hit max_iterations (%d); "
                        "page may be an infinite scroll.",
                        max_iterations,
                    )
            else:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            return True
        except Exception:
            logger.exception("Scroll to bottom error")
            return False

    @staticmethod
    def scroll_to_top(page: Page) -> bool:
        """Scroll to top of page."""
        try:
            page.evaluate("window.scrollTo(0, 0)")
            return True
        except Exception:
            logger.exception("Scroll to top error")
            return False


class InteractionHandler:
    """Handle complex interactions."""

    @staticmethod
    def hover(page: Page, selector: str, timeout: int = 5000) -> bool:
        """Hover over element."""
        try:
            page.hover(selector, timeout=timeout)
            return True
        except Exception:
            logger.exception("Hover error")
            return False

    @staticmethod
    def drag_and_drop(
        page: Page,
        source_selector: str,
        target_selector: str,
        timeout: int = 5000,
    ) -> bool:
        """Drag element from source to target."""
        try:
            page.drag_and_drop(source_selector, target_selector, timeout=timeout)
            return True
        except Exception:
            logger.exception("Drag and drop error")
            return False

    @staticmethod
    def select_option(
        page: Page,
        selector: str,
        value: Optional[str] = None,
        label: Optional[str] = None,
        timeout: int = 5000,
    ) -> bool:
        """
        Select option from dropdown.

        Raises:
            ValueError: If neither value nor label is provided.
        """
        if value is None and label is None:
            raise ValueError("select_option requires either 'value' or 'label'.")
        try:
            if value is not None:
                page.select_option(selector, value=value, timeout=timeout)
            else:
                page.select_option(selector, label=label, timeout=timeout)
            return True
        except Exception:
            logger.exception("Select option error")
            return False

    @staticmethod
    def press_key(
        page: Page, key: str, selector: Optional[str] = None
    ) -> bool:
        """Press keyboard key, optionally focusing an element first."""
        try:
            if selector:
                page.focus(selector)
            page.keyboard.press(key)
            return True
        except Exception:
            logger.exception("Key press error")
            return False

    @staticmethod
    def type_with_delay(
        page: Page, selector: str, text: str, delay: int = 100
    ) -> bool:
        """Type text with delay between characters (human-like)."""
        try:
            page.locator(selector).click()
            page.keyboard.type(text, delay=delay)
            return True
        except Exception:
            logger.exception("Type with delay error")
            return False