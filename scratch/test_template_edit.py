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

async def test_template_edit_and_cleanup():
    sample_file = next(pathlib.Path("samples").glob("*CE1*.txt"))
    errors_logged = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 980})
        page = await context.new_page()

        page.on("console", lambda msg: print(f"  [CONSOLE {msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: errors_logged.append(str(err)))

        print("\n=======================================================")
        print("🚀 [TEST 1] Verify Hostname Regex & Conditional Rules Removal")
        print("=======================================================")
        await page.goto("http://127.0.0.1:8000/#golden", wait_until="networkidle")

        # 1. Verify hostname regex and conditional rules elements are removed
        has_hostname_regex = await page.locator("#golden-hostname-regex").count()
        has_conditional_container = await page.locator("#golden-conditional-container").count()
        has_add_rule_btn = await page.locator("#golden-add-rule-btn").count()
        print(f"  #golden-hostname-regex count: {has_hostname_regex} (expected 0)")
        print(f"  #golden-conditional-container count: {has_conditional_container} (expected 0)")
        print(f"  #golden-add-rule-btn count: {has_add_rule_btn} (expected 0)")

        assert has_hostname_regex == 0, "Hostname regex input must be removed"
        assert has_conditional_container == 0, "Conditional container must be removed"
        assert has_add_rule_btn == 0, "Add rule button must be removed"

        # 2. Verify saved templates table header has '설명'
        table_headers = await page.locator("#golden-templates-list th").all_inner_texts()
        print(f"  Saved templates table headers: {table_headers}")
        assert "설명" in table_headers, "Table header must contain '설명'"
        assert not any("hostname" in h.lower() for h in table_headers), "Table header must not contain Hostname"

        print("\n=======================================================")
        print("🚀 [TEST 2] Upload & Save New Golden Template")
        print("=======================================================")
        file_input = await page.wait_for_selector("#golden-file-input", state="attached")
        await file_input.set_input_files(str(sample_file.resolve()))
        await page.wait_for_selector("#golden-results-area", state="visible", timeout=10000)
        await page.wait_for_timeout(1000)

        # Enter template info
        tpl_name = "Golden-Edit-Test-V1"
        tpl_desc = "Testing template edit and update without errors"
        await page.locator("#golden-template-name").fill(tpl_name)
        await page.locator("#golden-description").fill(tpl_desc)

        # Click save
        await page.locator("#golden-save-btn").click()
        await page.wait_for_timeout(1000)
        print(f"  Saved template '{tpl_name}' successfully")

        print("\n=======================================================")
        print("🚀 [TEST 3] Click Edit (수정) on Saved Template")
        print("=======================================================")
        # Find the row in #golden-templates-list
        template_rows = page.locator("#golden-templates-list tbody tr")
        row_count = await template_rows.count()
        print(f"  Total templates in table: {row_count}")
        assert row_count > 0, "At least one template must exist"

        target_row = None
        for i in range(row_count):
            row = template_rows.nth(i)
            text = await row.inner_text()
            if tpl_name in text:
                target_row = row
                break

        assert target_row is not None, f"Should find row for template '{tpl_name}'"

        # Click '✏️ 수정' button
        edit_btn = target_row.locator("button:has-text('수정')")
        print("  Clicking '✏️ 수정' button...")
        await edit_btn.click()
        await page.wait_for_timeout(1000)

        # Check errors
        print(f"  Page errors during edit: {errors_logged}")
        assert len(errors_logged) == 0, f"No page errors should occur during editTemplate! Got: {errors_logged}"

        # Verify fields populated
        loaded_name = await page.locator("#golden-template-name").input_value()
        loaded_desc = await page.locator("#golden-description").input_value()
        print(f"  Loaded name: '{loaded_name}', loaded desc: '{loaded_desc}'")
        assert loaded_name == tpl_name, f"Template name should be '{tpl_name}'"
        assert loaded_desc == tpl_desc, f"Template desc should be '{tpl_desc}'"

        # Verify cancel button is visible
        cancel_btn = page.locator("#golden-cancel-btn")
        assert await cancel_btn.is_visible(), "Cancel button must be visible in edit mode"

        # Verify tree elements rendered
        groups = page.locator(".tree-block-group")
        group_count = await groups.count()
        print(f"  Rendered block groups in edit mode: {group_count}")
        assert group_count > 0, "Tree block groups must be rendered in edit mode"
        first_group_box = await groups.first.bounding_box()
        assert first_group_box is not None and first_group_box["height"] >= 36.0, "Block must have valid height in edit mode"

        # Verify Live Preview is populated
        preview_text = await page.locator("#golden-live-preview-code").inner_text()
        assert len(preview_text.strip()) > 50, "Live preview must be populated in edit mode"
        print("  Live Preview populated in edit mode successfully")

        # Verify drop zone title indicates edit mode
        drop_zone_text = await page.locator("#golden-drop-zone").inner_text()
        assert "[템플릿 수정]" in drop_zone_text, f"Drop zone should indicate edit mode: {drop_zone_text}"

        print("\n=======================================================")
        print("🚀 [TEST 4] Modify Loaded Template and Re-Save")
        print("=======================================================")
        # Modify description
        updated_desc = "Updated description in edit mode"
        await page.locator("#golden-description").fill(updated_desc)

        # Click save
        await page.locator("#golden-save-btn").click()
        await page.wait_for_timeout(1000)

        # Verify table has updated description
        updated_row_text = await target_row.inner_text()
        print(f"  Updated row text: {updated_row_text}")
        assert updated_desc in updated_row_text, "Table should reflect updated description"

        # Verify cancel button is hidden after save
        assert not await cancel_btn.is_visible(), "Cancel button should be hidden after save"

        # Capture screenshot
        shot_path = os.path.join(ARTIFACT_DIR, "template_edit_verified.png")
        await page.screenshot(path=shot_path, full_page=False)
        print(f"  Saved screenshot: {shot_path}")

        print("\n=======================================================")
        print("🎉 ALL TEMPLATE EDIT & CLEANUP TESTS PASSED! 100% SUCCESS")
        print("=======================================================")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_template_edit_and_cleanup())
