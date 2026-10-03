import os
import time
from playwright.sync_api import sync_playwright

def test_compact_layout_and_delete_btn():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        
        # Load page
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")
        
        # Switch to Compare tab
        page.click('button[data-tab="tab-compare"]')
        page.wait_for_selector(".compare-tree-table", timeout=5000)
        
        # Inspect rows
        rows = page.locator(".compare-tree-table tbody tr:not(.empty-row)")
        row_count = rows.count()
        print(f"Compare rows found: {row_count}")
        
        if row_count > 0:
            first_row = rows.first
            time_col = first_row.locator(".col-time")
            status_col = first_row.locator(".col-status")
            score_col = first_row.locator(".col-score")
            action_col = first_row.locator(".col-action")
            del_btn = first_row.locator(".compare-delete-btn")
            view_btn = first_row.locator(".compare-view-btn")
            
            t_box = time_col.bounding_box()
            s_box = status_col.bounding_box()
            sc_box = score_col.bounding_box()
            a_box = action_col.bounding_box()
            d_box = del_btn.bounding_box()
            v_box = view_btn.bounding_box()
            
            print(f"Col Time: {t_box}")
            print(f"Col Status: {s_box}")
            print(f"Col Score: {sc_box}")
            print(f"Col Action: {a_box}")
            print(f"Delete Btn: {d_box}")
            print(f"View Btn: {v_box}")
            
            # Assert delete button is horizontal (height <= 32, width > height)
            assert d_box["height"] <= 32, f"Delete button height is too tall: {d_box['height']}"
            assert d_box["width"] > d_box["height"], f"Delete button should be wider than tall: {d_box['width']}x{d_box['height']}"
            
            # Assert action buttons are aligned on roughly the same Y coordinate
            assert abs(d_box["y"] - v_box["y"]) < 5, "Buttons should be on the same horizontal line"
            
            print("Layout checks PASSED!")
            
        # Take screenshot of compare section
        out_path = r"C:\Users\skullq\.gemini\antigravity-ide\brain\d2bb69c2-a3a5-4163-a411-28309037e688\compact_table_and_horizontal_delete.png"
        page.screenshot(path=out_path)
        print(f"Saved screenshot to {out_path}")
        browser.close()

if __name__ == "__main__":
    test_compact_layout_and_delete_btn()
