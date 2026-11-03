import os
import json
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

def parse_cookies(raw_str):
    raw_str = raw_str.strip()
    if raw_str.startswith("["):
        raw_cookies = json.loads(raw_str)
        clean = []
        for c in raw_cookies:
            cookie_dict = {
                "name": c["name"],
                "value": c["value"],
                "domain": c["domain"],
                "path": c.get("path", "/"),
                "secure": c.get("secure", False),
                "httpOnly": c.get("httpOnly", False),
            }
            if "sameSite" in c and c["sameSite"] in ["Strict", "Lax", "None"]:
                cookie_dict["sameSite"] = c["sameSite"]
            clean.append(cookie_dict)
        return clean

    cookies = []
    for line in raw_str.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            cookies.append({
                "domain": parts[0],
                "path": parts[2],
                "secure": parts[3].upper() == "TRUE",
                "expires": int(parts[4]) if parts[4].isdigit() else -1,
                "name": parts[5],
                "value": parts[6].strip()
            })
    return cookies

def dismiss_overlays(page):
    """Closes random Naukri chat drawers, promo modals, or cross buttons."""
    overlay_Close_selectors = [
        ".crossIcon",
        ".chatBot-ic-cross",
        "div.drawer-wrapper .crossIcon",
        "button[aria-label='Close']"
    ]
    for sel in overlay_Close_selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=500):
                loc.click(timeout=1000)
        except Exception:
            pass

def run_attempt(p, cookies, attempt_num):
    browser = p.chromium.launch(
        channel="chrome",
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--window-size=1366,768"
        ]
    )
    context = browser.new_context(
        viewport={"width": 1366, "height": 768},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    )
    context.add_cookies(cookies)
    page = context.new_page()

    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    try:
        print(f"[Attempt {attempt_num}] Navigating to Naukri profile...")
        page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=60000)

        # Wait for network activity to settle so React widgets finish hydrating
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeoutError:
            print("Networkidle timed out (background tracking scripts active), continuing...")

        page.wait_for_timeout(4000)

        print(f"Loaded URL: {page.url}")
        print(f"Page Title: {page.title()}")

        # Detect both hard redirects and soft logged-out states on the profile URL
        if (
            "login" in page.url.lower()
            or "access denied" in page.title().lower()
            or page.locator("input#usernameField, a#login_Layer").first.is_visible(timeout=1500)
        ):
            page.screenshot(path="debug_failure.png", full_page=True)
            raise RuntimeError("Session expired or blocked by firewall! Please refresh NAUKRI_COOKIES in GitHub Secrets.")

        dismiss_overlays(page)

        # Scroll down in steps to trigger Naukri's IntersectionObserver lazy loading
        print("Scrolling page to trigger lazy-loaded profile sections...")
        for scroll_y in [250, 500, 200]:
            page.mouse.wheel(0, scroll_y)
            page.wait_for_timeout(800)

        dismiss_overlays(page)

        print("Looking for Resume Headline edit button...")
        edit_btn = page.locator(
            "#lazyResumeHead span.edit, "
            ".resumeHeadline span.edit, "
            "div.resumeHeadline .edit, "
            "div:has(> div > span:has-text('Resume headline')) span.edit, "
            "span.edit:has-text('Edit')"
        ).first

        edit_btn.scroll_into_view_if_needed(timeout=10000)
        edit_btn.wait_for(state="visible", timeout=15000)
        edit_btn.click()

        page.wait_for_selector("#resumeHeadlineTxt", state="visible", timeout=10000)
        textarea = page.locator("#resumeHeadlineTxt")
        current_text = textarea.input_value().strip()

        if current_text.endswith("."):
            new_text = current_text[:-1]
        else:
            new_text = current_text + "."

        textarea.fill(new_text)
        page.wait_for_timeout(1000)

        print("Saving resume headline...")
        save_btn = page.locator("form:has(#resumeHeadlineTxt) button:has-text('Save'), div.resumeHeadlineEdit button:has-text('Save')").first
        save_btn.wait_for(state="visible", timeout=5000)
        save_btn.click()

        # Wait for the edit modal (#resumeHeadlineTxt) to disappear, confirming the save succeeded
        page.locator("#resumeHeadlineTxt").wait_for(state="hidden", timeout=10000)
        page.wait_for_timeout(3000)
        print(f"Successfully updated Naukri profile headline! New length: {len(new_text)} chars.")

    except Exception as e:
        print(f"[Attempt {attempt_num}] Failed: {e}")
        try:
            page.screenshot(path="debug_failure.png", full_page=True)
            print("Saved screenshot to debug_failure.png")
        except Exception:
            pass
        raise e
    finally:
        browser.close()

def update_profile():
    cookies_raw = os.environ.get("NAUKRI_COOKIES")
    if not cookies_raw:
        raise ValueError("NAUKRI_COOKIES environment variable is missing!")

    cookies = parse_cookies(cookies_raw)

    with sync_playwright() as p:
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                run_attempt(p, cookies, attempt)
                return
            except Exception as e:
                if attempt == max_attempts:
                    raise e
                print("Retrying in 5 seconds...")
                time.sleep(5)

if __name__ == "__main__":
    update_profile()
