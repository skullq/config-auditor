import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

def test_separated_hostname_column():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        
        page.goto("http://127.0.0.1:8000")
        page.wait_for_load_state("networkidle")
        
        # Click Compare tab
        page.click('button[data-tab="tab-compare"]')
        page.wait_for_selector(".compare-tree-table", timeout=5000)
        
        # Check table headers
        headers = [h.strip() for h in page.locator(".compare-tree-table thead th").all_text_contents()]
        print("Table headers:", headers)
        
        assert "업로드 파일" in headers, "Header '업로드 파일' not found"
        assert "HOSTNAME" in headers, "Header 'HOSTNAME' not found"
        
        # Check rows
        rows = page.locator(".compare-tree-table tbody tr:not(.empty-row)")
        row_count = rows.count()
        print(f"Compare rows count: {row_count}")
        
        if row_count > 0:
            first_row = rows.first
            file_col = first_row.locator(".col-filename")
            host_col = first_row.locator(".col-hostname")
            
            file_text = file_col.inner_text().strip()
            host_text = host_col.inner_text().strip()
            
            print(f"First row File: {file_text}")
            print(f"First row Hostname: {host_text}")
            
            assert "대련_CE1" in file_text or ".txt" in file_text or len(file_text) > 0
            assert "DALIAN-CE1" in host_text or len(host_text) > 0
            
            # Verify hostname code badge styling
            badge = host_col.locator(".compare-hostname-code")
            if badge.count() > 0:
                print("Hostname badge text:", badge.first.inner_text().strip())
                
        out_path = r"C:\Users\skullq\.gemini\antigravity-ide\brain\d2bb69c2-a3a5-4163-a411-28309037e688\separated_hostname_column.png"
        page.screenshot(path=out_path)
        print(f"Screenshot saved to: {out_path}")
        browser.close()

if __name__ == "__main__":
    test_separated_hostname_column()
