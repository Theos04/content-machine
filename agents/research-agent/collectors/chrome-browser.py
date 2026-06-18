from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path="/data/data/com.termux/files/usr/bin/chromium-browser",
        headless=False,
        args=["--no-sandbox"]
    )

    page = browser.new_page()
    page.goto("https://google.com")
    print(page.title())
