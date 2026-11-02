import os
import json
from playwright.sync_api import sync_playwright

def parse_cookies(raw_str):
    raw_str = raw_str.strip()
    if raw_str.startswith("["):
        raw_cookies = json.loads(raw_str)
        clean = []
        for c in raw_cookies:
            clean.append({
                "name": c["name"],
                "value": c["value"],
                "domain": c["domain"],
                "path": c.get("path", "/"),
                "secure": c.get("secure", False),
                "httpOnly": c.get("httpOnly", False),
            })
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

def update_profile():
    cookies_raw = os.environ.get("NAUKRI_COOKIES")
    if not cookies_raw:
        raise ValueError("NAUKRI_COOKIES environment variable is missing!")
    
    cookies = parse_cookies(cookies_raw)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768}
        )
        
        context.add_cookies(cookies)
        page = context.new_page()
        
        # Hide webdriver property
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        print("Navigating to Naukri profile...")
        page.goto("https://www.naukri.com/mnjuser/profile", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        
        print(f"Loaded URL: {page.url}")
        print(f"Page Title: {page.title()}")
        
        if "login" in page.url.lower() or "access denied" in page.title().lower():
            print("Page snippet:", page.content()[:500])
            raise Exception("Blocked by firewall or redirected to login!")

        try:
            print("Looking for Resume Headline edit button...")
            # Try multiple selectors that Naukri uses for the Resume Headline edit icon
            edit_btn = page.locator("#lazyResumeHead span.edit, .resumeHeadline span.edit, span.edit:has-text('editOneTheme')").first
            edit_btn.wait_for(state="visible", timeout=15000)
            edit_btn.click()
            
            page.wait_for_selector("#resumeHeadlineTxt", timeout=10000)
            textarea = page.locator("#resumeHeadlineTxt")
            current_text = textarea.input_value().strip()

            if current_text.endswith("."):
                new_text = current_text[:-1]
            else:
                new_text = current_text + "."

            textarea.fill(new_text)
            
            save_btn = page.locator("button.btn-dark-ot:has-text('Save'), form[name='resumeHeadlineForm'] button[type='submit'], button:has-text('Save')").first
            save_btn.click()
            page.wait_for_timeout(3000)
            print("Successfully updated Naukri profile headline!")

        except Exception as e:
            print(f"Failed to update headline: {e}")
            print("Visible page text snippet:", page.locator("body").inner_text()[:600])
            raise e
        finally:
            browser.close()

if __name__ == "__main__":
    update_profile()
