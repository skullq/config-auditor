import asyncio
import sys
from playwright.async_api import async_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def inspect():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.on("console", lambda msg: print(f"[Browser Console {msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: print(f"[Browser PageError] {err}"))

        await page.goto("http://127.0.0.1:8000/")
        await page.locator('[data-tab="tab-compare"]').click()
        await page.wait_for_timeout(1000)

        btn = page.locator('button[onclick*="viewResult"]').nth(0)
        await btn.click()
        await page.wait_for_selector("#compare-drawer.open")
        await page.wait_for_timeout(500) # 애니메이션 완료 대기!

        drawer = page.locator("#compare-drawer")
        d_box = await drawer.bounding_box()
        print("drawer bounding box AFTER transition:", d_box)

        close_btn = page.locator(".drawer-close-btn")
        c_box = await close_btn.bounding_box()
        print("close_btn bounding box AFTER transition:", c_box)
        await page.screenshot(path="C:/Users/skullq/.gemini/antigravity-ide/brain/d2bb69c2-a3a5-4163-a411-28309037e688/drawer_stable.png")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect())
