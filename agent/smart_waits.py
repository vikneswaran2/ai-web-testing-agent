# agent/smart_waits.py

import time
from typing import Optional, Callable
from playwright.sync_api import Page


class SmartWait:
    """
    Enhanced smart wait strategies for reliable test execution
    """

    def wait_dom_ready(self, page: Page, timeout: int = 5000) -> bool:
        """Wait until document.readyState == 'complete'"""
        start = time.time() * 1000
        while (time.time() * 1000) - start < timeout:
            try:
                state = page.evaluate("document.readyState")
                if state == "complete":
                    return True
            except Exception as e:
                print(f"[wait_dom_ready] Error: {e}")
            time.sleep(0.2)
        return False

    def wait_network_idle(self, page: Page, timeout: int = 5000, idle_time: int = 500) -> bool:
        """Wait until network has no new requests for specified idle time"""
        start = time.time() * 1000
        try:
            prev_count = page.evaluate("() => window.performance.getEntries().length")
        except Exception as e:
            print(f"[wait_network_idle] Initial count error: {e}")
            return False

        while (time.time() * 1000) - start < timeout:
            time.sleep(idle_time / 1000)
            try:
                new_count = page.evaluate("() => window.performance.getEntries().length")
                if new_count == prev_count:
                    return True
                prev_count = new_count
            except Exception as e:
                print(f"[wait_network_idle] Error: {e}")

        return False

    def wait_for_element(self, page: Page, selector: str, timeout: int = 5000,
                         visible: bool = True) -> bool:
        """Wait for element to exist and optionally be visible"""
        start = time.time() * 1000

        while (time.time() * 1000) - start < timeout:
            try:
                element = page.query_selector(selector)
                if element:
                    if visible:
                        if element.is_visible():
                            return True
                    else:
                        return True
            except Exception as e:
                print(f"[wait_for_element] Error: {e}")
            time.sleep(0.3)

        return False

    def wait_for_element_clickable(self, page: Page, selector: str, timeout: int = 5000) -> bool:
        """Wait for element to be clickable (visible and enabled)"""
        start = time.time() * 1000

        while (time.time() * 1000) - start < timeout:
            try:
                element = page.query_selector(selector)
                if element:
                    if element.is_visible() and element.is_enabled():
                        return True
            except Exception as e:
                print(f"[wait_for_element_clickable] Error: {e}")
            time.sleep(0.3)

        return False

    def wait_for_text(self, page: Page, text: str, timeout: int = 5000,
                      exact: bool = False) -> bool:
        """Wait for specific text to appear on page.
        exact=True: all words in text must appear in page (word match).
        exact=False: text as a substring must appear in page (partial match).
        """
        start = time.time() * 1000

        while (time.time() * 1000) - start < timeout:
            try:
                content = page.content().lower()
                search_text = text.lower()

                if exact:
                    # Word-level match: every word must appear somewhere
                    words = search_text.split()
                    if all(word in content for word in words):
                        return True
                else:
                    # Substring match
                    if search_text in content:
                        return True
            except Exception as e:
                print(f"[wait_for_text] Error: {e}")
            time.sleep(0.3)

        return False

    def wait_for_text_to_disappear(self, page: Page, text: str, timeout: int = 5000) -> bool:
        """Wait for specific text to disappear from page"""
        start = time.time() * 1000

        while (time.time() * 1000) - start < timeout:
            try:
                content = page.content().lower()
                if text.lower() not in content:
                    return True
            except Exception as e:
                print(f"[wait_for_text_to_disappear] Error: {e}")
            time.sleep(0.3)

        return False

    def wait_for_element_count(self, page: Page, selector: str, count: int,
                               timeout: int = 5000) -> bool:
        """Wait for specific number of elements matching selector"""
        start = time.time() * 1000

        while (time.time() * 1000) - start < timeout:
            try:
                elements = page.query_selector_all(selector)
                if len(elements) == count:
                    return True
            except Exception as e:
                print(f"[wait_for_element_count] Error: {e}")
            time.sleep(0.3)

        return False

    def wait_for_attribute(self, page: Page, selector: str, attribute: str,
                           value: str, timeout: int = 5000) -> bool:
        """Wait for element attribute to have specific value"""
        start = time.time() * 1000

        while (time.time() * 1000) - start < timeout:
            try:
                element = page.query_selector(selector)
                if element:
                    attr_value = element.get_attribute(attribute)
                    if attr_value == value:
                        return True
            except Exception as e:
                print(f"[wait_for_attribute] Error: {e}")
            time.sleep(0.3)

        return False

    def wait_for_animations(self, page: Page, timeout: int = 3000) -> bool:
        """Wait for CSS animations and transitions to complete"""
        try:
            page.evaluate("""
                () => {
                    return new Promise((resolve) => {
                        const elements = document.querySelectorAll('*');
                        let animating = false;

                        elements.forEach(el => {
                            const style = window.getComputedStyle(el);
                            if (style.animationName !== 'none' || style.transitionProperty !== 'none') {
                                animating = true;
                            }
                        });

                        if (!animating) {
                            resolve();
                        } else {
                            setTimeout(resolve, 500);
                        }
                    });
                }
            """)
            return True
        except Exception as e:
            print(f"[wait_for_animations] Error: {e}")
            return False

    def wait_for_ajax(self, page: Page, timeout: int = 5000) -> bool:
        """Wait for AJAX requests to complete (jQuery or fetch)"""
        start = time.time() * 1000

        while (time.time() * 1000) - start < timeout:
            try:
                # Check jQuery AJAX if available
                jquery_idle = page.evaluate("""
                    () => {
                        if (typeof jQuery !== 'undefined') {
                            return jQuery.active === 0;
                        }
                        return true;
                    }
                """)

                # Check pending fetch requests via injected counter (if available)
                fetch_idle = page.evaluate("""
                    () => {
                        if (typeof window.__fetchPending !== 'undefined') {
                            return window.__fetchPending === 0;
                        }
                        return true; // assume idle if not tracked
                    }
                """)

                if jquery_idle and fetch_idle:
                    return True
            except Exception as e:
                print(f"[wait_for_ajax] Error: {e}")
            time.sleep(0.3)

        return False

    def wait_for_condition(self, page: Page, condition: Callable[[], bool],
                           timeout: int = 5000, poll_interval: int = 300) -> bool:
        """Wait for custom condition function to return True"""
        start = time.time() * 1000

        while (time.time() * 1000) - start < timeout:
            try:
                if condition():
                    return True
            except Exception as e:
                print(f"[wait_for_condition] Error: {e}")
            time.sleep(poll_interval / 1000)

        return False

    def wait_for_url_change(self, page: Page, initial_url: str, timeout: int = 5000) -> bool:
        """Wait for URL to change from initial URL"""
        start = time.time() * 1000

        while (time.time() * 1000) - start < timeout:
            try:
                if page.url != initial_url:
                    return True
            except Exception as e:
                print(f"[wait_for_url_change] Error: {e}")
            time.sleep(0.3)

        return False

    def smart_wait_after_action(self, page: Page, action_type: str):
        """Intelligent wait after specific action types"""
        if action_type in ["goto", "click"]:
            self.wait_dom_ready(page, timeout=3000)
            self.wait_network_idle(page, timeout=2000)
        elif action_type in ["type", "select"]:
            time.sleep(0.2)
        elif action_type == "scroll":
            time.sleep(0.5)
            self.wait_network_idle(page, timeout=2000)
        else:
            print(f"[smart_wait_after_action] No wait strategy for action_type: '{action_type}'")