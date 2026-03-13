"""
save_session.py
────────────────
Run this ONCE to log into LinkedIn manually and save your browser session.
The session is stored in linkedin_session.json and loaded automatically
by the LinkedInScraper on every future run.

Usage:
    cd backend
    venv\Scripts\activate
    python save_session.py

When the browser opens:
  1. Type your email and password normally
  2. Solve any CAPTCHA or 2FA if LinkedIn asks
  3. Wait until your LinkedIn FEED is fully loaded
  4. Come back to this terminal and press Enter
"""

import asyncio
import json
import pathlib
from playwright.async_api import async_playwright


SESSION_FILE = pathlib.Path("linkedin_session.json")


async def main():
    print("\n=== LinkedIn Session Saver ===\n")

    async with async_playwright() as p:
        # Launch visible browser so you can log in manually
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",  # hides bot flag
            ],
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        page = await context.new_page()
        await page.goto("https://www.linkedin.com/login")

        print("Browser opened — log in now:")
        print("  1. Enter your email and password in the browser")
        print("  2. Complete any CAPTCHA or 2FA if asked")
        print("  3. Wait until your LinkedIn FEED loads completely")
        print("  4. Press Enter HERE (not in the browser)\n")
        input("Press Enter once your feed is loaded > ")

        # Verify we're actually logged in
        current_url = page.url
        if "feed" in current_url or "mynetwork" in current_url or "jobs" in current_url:
            print("\n✓ Login confirmed.")
        else:
            print(f"\n⚠ Current URL: {current_url}")
            print("  Doesn't look like the feed — make sure you're fully logged in.")
            confirm = input("  Save anyway? (y/n) > ").strip().lower()
            if confirm != "y":
                print("Cancelled.")
                await browser.close()
                return

        # Save session state (cookies + localStorage + sessionStorage)
        await context.storage_state(path=str(SESSION_FILE))
        await browser.close()

    # Show what was saved
    data = json.loads(SESSION_FILE.read_text())
    cookie_names = [c["name"] for c in data.get("cookies", [])]
    print(f"\n✓ Session saved to {SESSION_FILE}")
    print(f"  Cookies saved: {len(cookie_names)}")

    if "li_at" in cookie_names:
        print("  ✓ li_at cookie present (main auth cookie)")
    else:
        print("  ⚠ li_at cookie NOT found — session may not be valid")

    print("\nThe scraper will use this session automatically.")
    print("Re-run this script if you get 401/403 errors (session expired).\n")


if __name__ == "__main__":
    asyncio.run(main())