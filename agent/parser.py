import re

class InstructionParser:

    def detect_selector(self, text):
        # --- FULL NAME ---
        if any(k in text for k in ["full name", "fullname", "your name"]):
            return "input[id='userName'], input[name='userName'], input[placeholder*='Full Name'], input[placeholder*='Name']"

        # --- USERNAME ---
        if any(k in text for k in ["username", "user name", "user-name"]):
            return "input[id='user-name'], input[name='user-name'], input[name='username'], input[type='text']"

        # --- EMAIL ---
        if "email" in text:
            return "input[type='email'], input[name='email'], input[id='email'], input[id='userEmail']"

        # --- PASSWORD ---
        if "password" in text:
            return "input[type='password']"

        # --- SEARCH ---
        if "search" in text:
            return "input[placeholder*='Search'], input[name='q'], input[type='search']"

        # --- FIRST NAME ---
        if "first name" in text:
            return "input[id='first-name'], input[id='firstName'], input[name='firstName'], input[placeholder*='First']"

        # --- LAST NAME ---
        if "last name" in text:
            return "input[id='last-name'], input[id='lastName'], input[name='lastName'], input[placeholder*='Last']"

        # --- PHONE / MOBILE ---
        if any(k in text for k in ["phone", "mobile", "contact number"]):
            return "input[id='userNumber'], input[name='phone'], input[type='tel'], input[placeholder*='Mobile']"

        # --- CURRENT ADDRESS ---
        if "current address" in text:
            return "textarea[id='currentAddress'], textarea[placeholder*='Current Address'], textarea[name='currentAddress']"

        # --- PERMANENT ADDRESS ---
        if "permanent address" in text:
            return "textarea[id='permanentAddress'], textarea[placeholder*='Permanent'], textarea[name='permanentAddress']"

        # --- ADDRESS (generic, after specific ones) ---
        if "address" in text:
            return "input[name='address'], input[placeholder*='Address'], textarea[placeholder*='Address']"

        # --- ZIP / POSTAL ---
        if any(k in text for k in ["zip", "postal", "postcode"]):
            return "input[id='postal-code'], input[name='zip'], input[placeholder*='Zip']"

        # --- SUBJECT ---
        if "subject" in text:
            return "input[id='subject'], input[name='subject'], input[placeholder*='Subject']"

        # --- MESSAGE / COMMENT ---
        if any(k in text for k in ["message", "comment", "description"]):
            return "textarea[id='message'], textarea[name='message'], textarea[placeholder*='Message'], textarea[placeholder*='Comment']"

        # --- LOGIN BUTTON (before generic button handler) ---
        if any(k in text for k in ["login button", "log in button", "signin button", "sign in button"]):
            return "input[type='submit'][id='login-button'], button[id='login-button'], button:has-text('Login'), button:has-text('Sign in')"

        # --- CHECKOUT BUTTON ---
        if "checkout button" in text:
            return "button[id='checkout'], .checkout_button, button:has-text('Checkout'), a:has-text('Checkout')"

        # --- CONTINUE BUTTON ---
        if "continue button" in text:
            return "input[id='continue'], button:has-text('Continue'), input[type='submit'][value*='Continue']"

        # --- FINISH BUTTON ---
        if any(k in text for k in ["finish button", "place order", "complete order"]):
            return "button[id='finish'], button:has-text('Finish'), a:has-text('Finish')"

        # --- CART BUTTON ---
        if any(k in text for k in ["cart button", "shopping cart", "basket"]):
            return "a.shopping_cart_link, .shopping_cart_badge, a[href*='cart'], button:has-text('Cart')"

        # --- ADD TO CART ---
        if "add to cart" in text:
            return "button[id*='add-to-cart'], button.btn_inventory, button:has-text('Add to cart')"

        # --- SUBMIT BUTTON ---
        if any(k in text for k in ["submit button", "submit"]):
            return "button[id='submit'], input[type='submit'], button[type='submit'], button:has-text('Submit')"

        # --- REGISTER / SIGNUP BUTTON ---
        if any(k in text for k in ["register button", "signup button", "sign up button", "create account"]):
            return "button:has-text('Register'), button:has-text('Sign up'), button:has-text('Create Account'), input[type='submit'][value*='Register']"

        # --- GENERIC BUTTON with subject extraction ---
        if "button" in text:
            match = re.search(r'click(?:\s+the)?\s+(.+?)\s+button', text)
            subject = match.group(1).strip() if match else text.replace("click", "").replace("button", "").strip()
            if subject:
                return f"button:has-text('{subject}'), input[type='submit'][value*='{subject}'], .btn:has-text('{subject}')"
            return "button"

        selector = text.strip()
        # Block non-interactive tags if they appear alone
        if selector.lower() in ["script", "style", "head", "meta", "link", "html", "body"]:
            return "button, input, a"

        return selector

    def parse(self, instruction: str):
        # Split by both 'then' and periods to allow natural sentencing
        steps = re.split(r' then |\. ', instruction)  # keep original casing
        actions = []

        for step in steps:
            step_lower = step.lower().strip()  # use only for keyword matching
            step = step.strip()
            if not step:
                continue

            # --- NAVIGATION ---
            if any(k in step_lower for k in ["navigate", "open", "go to"]):
                url = re.findall(r'(https?://[^\s.,;]+)', step)
                if url:
                    actions.append({"action": "goto", "value": url[0]})
                continue

            # --- CLICK ---
            if "click" in step_lower:
                selector = self.detect_selector(step_lower)
                actions.append({"action": "click", "value": selector})
                continue

            # --- TYPE / ENTER ---
            if any(k in step_lower for k in ["type", "enter", "fill"]):
                # Extract quoted text (preserve original casing)
                text_match = re.findall(r'"(.*?)"', step)
                typed_value = text_match[0] if text_match else ""

                # If no quotes, try to find text after action keywords
                if not typed_value:
                    as_match = re.findall(r'(?:type|enter|fill)\s+(\S+)\s+(?:in|into|as)', step_lower)
                    if as_match:
                        typed_value = as_match[0]

                selector = self.detect_selector(step_lower)
                actions.append({
                    "action": "type",
                    "field": selector,
                    "value": typed_value
                })
                continue

            # --- VERIFY TEXT ---
            if any(k in step_lower for k in ["verify", "assert", "check"]):
                target = step_lower.replace("verify", "").replace("assert", "").replace("check", "").strip()
                target = re.sub(r'^(that|if|contains|is)\s+', '', target)
                actions.append({"action": "assert_text", "value": target})
                continue

            # --- UNRECOGNISED ---
            actions.append({"action": "unknown", "value": step})

        return actions