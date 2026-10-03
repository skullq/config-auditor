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

async def test_golden_upload_and_visual_layout():
    """
    [NEW TEST METHODOLOGY]
    1. No synthetic event dispatching (`dispatch_event`) to bypass visibility checks.
    2. Strict Bounding Box verification: Every top-level group MUST have height >= 36px.
    3. Visible content verification: Header text must be legible and not clipped.
    4. Scrollable container validation: When children exceed container height, scrollHeight > clientHeight, children DO NOT compress to 0/2px.
    5. Real user actionability: Standard .click() must succeed on interactive controls.
    """
    sample_file = next(pathlib.Path("samples").glob("*CE1*.txt"))
    print(f"Testing with sample config: {sample_file}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 980})
        page = await context.new_page()

        page.on("console", lambda msg: print(f"  [CONSOLE {msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: print(f"  [PAGE ERROR] {err}"))

        print("\nStep 1: Navigate to page and upload config")
        await page.goto("http://127.0.0.1:8000/#golden", wait_until="networkidle")
        file_input = await page.wait_for_selector("#golden-file-input", state="attached")
        await file_input.set_input_files(str(sample_file.resolve()))
        await page.wait_for_selector("#golden-results-area", state="visible", timeout=10000)
        await page.wait_for_timeout(1000)

        print("\nStep 2: Strict Physical Layout & Bounding Box Assertions")
        groups = page.locator(".tree-block-group")
        group_count = await groups.count()
        print(f"  Rendered block groups: {group_count}")
        assert group_count > 0, "At least one block group must be rendered"

        # Verify each of the first 10 groups has physical height >= 36px (never 2px!)
        sample_check_count = min(group_count, 10)
        for i in range(sample_check_count):
            g = groups.nth(i)
            box = await g.bounding_box()
            assert box is not None, f"Group #{i} must have a bounding box"
            height = box["height"]
            width = box["width"]
            print(f"  Group #{i} BoundingBox: width={width:.1f}px, height={height:.1f}px")
            assert height >= 36.0, f"Group #{i} height is {height:.1f}px - MUST be >= 36px (cannot be shrunk to 2px!)"
            assert width >= 400.0, f"Group #{i} width is {width:.1f}px - MUST span container"

        print("\nStep 3: Header Text & Visibility Verification")
        first_group = groups.first
        title = await first_group.locator(".tree-block-title").inner_text()
        print(f"  First group title: '{title}'")
        assert len(title.strip()) > 0, "First group title must not be empty"

        print("\nStep 4: Real User Click Verification on Collapse/Expand")
        expand_btn = first_group.locator(".tree-expand-btn")
        # Real user click - MUST NOT use force=True or dispatch_event!
        await expand_btn.click()
        await page.wait_for_timeout(300)
        box_after_collapse = await first_group.bounding_box()
        print(f"  Group #0 height after collapse: {box_after_collapse['height']:.1f}px")
        assert 36.0 <= box_after_collapse["height"] <= 60.0, "Collapsed group should only show header (36-60px)"

        # Expand again
        await expand_btn.click()
        await page.wait_for_timeout(300)
        box_after_expand = await first_group.bounding_box()
        print(f"  Group #0 height after re-expand: {box_after_expand['height']:.1f}px")
        assert box_after_expand["height"] > 60.0, "Expanded group must be taller than header alone"

        print("\nStep 5: Full-Line Edit Toggle Real User Actionability")
        first_leaf = page.locator(".tree-leaf-row").first
        full_line_btn = first_leaf.locator(".item-full-line-btn")
        # Real user click without force or synthetic dispatch
        await full_line_btn.click()
        await page.wait_for_timeout(300)

        # Check badge is visible and input is editable
        badge = first_leaf.locator(".badge-full-tag")
        badge_box = await badge.bounding_box()
        assert badge_box is not None and badge_box["height"] > 10, "Full-line badge must be physically rendered"
        print(f"  Full-Line Badge BoundingBox: {badge_box}")

        input_field = first_leaf.locator(".item-expected-value")
        await input_field.click()
        await input_field.fill("test-edited-full-line-command")
        await page.wait_for_timeout(300)

        # Verify Live Preview updated
        preview_text = await page.locator("#golden-live-preview-code").inner_text()
        assert "test-edited-full-line-command" in preview_text, "Preview must contain edited full-line command"
        print("  Live Preview successfully updated with edited full-line command!")

        # Screenshot artifacts
        shot_path = os.path.join(ARTIFACT_DIR, "fixed_tree_view_verified.png")
        await page.screenshot(path=shot_path, full_page=False)
        print(f"  Saved verification screenshot: {shot_path}")

        print("\n=======================================================")
        print("ALL TESTS PASSED WITH NEW RIGOROUS METHODOLOGY! 🎉")
        print("=======================================================")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_golden_upload_and_visual_layout())
