import os
import sys
import asyncio
import pathlib
from playwright.async_api import async_playwright

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ARTIFACT_DIR = r"C:\Users\skullq\.gemini\antigravity-ide\brain\d2bb69c2-a3a5-4163-a411-28309037e688"

async def test_compare_tab_improvements():
    sample_file = next(pathlib.Path("samples").glob("*CE1*.txt"))
    errors_logged = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 980})
        page = await context.new_page()

        page.on("console", lambda msg: print(f"  [CONSOLE {msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: errors_logged.append(str(err)))

        print("\n=======================================================")
        print("🚀 [TEST 1] Navigate to Compare Tab & Check UI Requirements")
        print("=======================================================")
        await page.goto("http://127.0.0.1:8000/#compare", wait_until="networkidle")
        await page.locator("button[data-tab='tab-compare']").click()
        await page.wait_for_timeout(500)

        # 1. OS Select Check
        os_select = page.locator("#compare-os-select")
        assert await os_select.is_visible(), "OS selection dropdown must be visible"
        await os_select.select_option("iosxe")
        print("  ✓ OS type 'iosxe' selectable")

        # 2. Check '자동매칭 (Hostname 기반)' is REMOVED
        tpl_options = await page.locator("#compare-template-select option").all_inner_texts()
        print(f"  Template dropdown options: {tpl_options}")
        assert not any("자동매칭" in opt for opt in tpl_options), "'자동매칭 (Hostname 기반)' text must be removed!"
        assert not any("hostname 기반" in opt.lower() for opt in tpl_options), "'Hostname 기반' must be removed!"
        print("  ✓ '자동매칭 (Hostname 기반)' text successfully removed")

        # 3. Check '비교 실행' and '목록 비우기' buttons are REMOVED
        run_btn_count = await page.locator("#compare-run-btn").count()
        clear_btn_count = await page.locator("#compare-clear-btn").count()
        print(f"  #compare-run-btn count: {run_btn_count}, #compare-clear-btn count: {clear_btn_count}")
        assert run_btn_count == 0, "'비교 실행' button must be removed"
        assert clear_btn_count == 0, "'목록 비우기' button must be removed"
        print("  ✓ Buttons '비교 실행' and '목록 비우기' successfully removed")

        # 4. Check title is '비교 결과'
        card_titles = await page.locator("#tab-compare .card-title").all_inner_texts()
        print(f"  Card titles: {card_titles}")
        assert any("비교 결과" in t for t in card_titles), "Section title must contain '비교 결과'"
        assert not any("비교 진행 현황" in t for t in card_titles), "Title must NOT contain '비교 진행 현황'"
        print("  ✓ Section renamed to '비교 결과'")

        print("\n=======================================================")
        print("🚀 [TEST 2] Drag/Upload File & Verify Instant Real-Time Comparison")
        print("=======================================================")
        # Select first template
        await page.locator("#compare-template-select").select_option(index=0)
        selected_tpl_text = await page.locator("#compare-template-select option:checked").inner_text()
        print(f"  Using Golden Template: {selected_tpl_text}")

        # Upload file directly to drop zone
        file_input = await page.wait_for_selector("#compare-file-input", state="attached")
        await file_input.set_input_files(str(sample_file.resolve()))

        # Wait for real-time comparison to finish (without clicking any button!)
        print("  Waiting for real-time comparison to complete...")
        await page.wait_for_selector("#compare-history-body tr:has-text('완료')", timeout=15000)
        await page.wait_for_timeout(1000)

        # Verify row in table
        first_row = page.locator("#compare-history-body tr").first
        first_row_text = await first_row.inner_text()
        print(f"  Result row text: {first_row_text}")
        assert "완료" in first_row_text, "Comparison must complete immediately"
        assert "%" in first_row_text, "Score must be present"

        # Verify detailed view opened automatically
        detail_area = page.locator("#compare-result-area")
        assert await detail_area.is_visible(), "Detailed result area must be immediately visible without clicking!"
        detail_text = await detail_area.inner_text()
        print(f"  Detail area snippet: {detail_text[:150]}...")
        assert "항목 통과" in detail_text or "점수" in detail_text or "%" in detail_text

        print("  ✓ Real-time comparison executed & detailed view rendered immediately!")

        print("\n=======================================================")
        print("🚀 [TEST 3] Verify Individual Result Deletion")
        print("=======================================================")
        # Count rows before deletion
        rows_before = await page.locator("#compare-history-body tr").count()
        print(f"  Rows before deletion: {rows_before}")

        # Setup dialog handler to accept confirm
        page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))

        # Click delete button on first row
        delete_btn = first_row.locator("button:has-text('삭제')")
        assert await delete_btn.is_visible(), "Individual delete button must be visible in action column"
        print("  Clicking '🗑️ 삭제' button on result row...")
        await delete_btn.click()
        await page.wait_for_timeout(1000)

        # Count rows after deletion
        rows_after = await page.locator("#compare-history-body tr").count()
        print(f"  Rows after deletion: {rows_after}")
        assert rows_after < rows_before or "표시됩니다" in await page.locator("#compare-history-body").inner_text()

        # Verify detail area cleared
        detail_visible = await detail_area.is_visible()
        print(f"  Detail area visible after deletion: {detail_visible}")
        assert not detail_visible, "Detail area must be closed/cleared when current result is deleted"

        # Capture screenshot
        shot_path = os.path.join(ARTIFACT_DIR, "compare_instant_verified.png")
        await page.screenshot(path=shot_path, full_page=False)
        print(f"  Saved verification screenshot: {shot_path}")

        assert len(errors_logged) == 0, f"Page errors logged: {errors_logged}"
        print("\n=======================================================")
        print("🎉 ALL 5 COMPARE TAB REQUIREMENTS TESTED & PASSED! 🎉")
        print("=======================================================")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_compare_tab_improvements())
