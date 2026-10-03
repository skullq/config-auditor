import asyncio
import sys
import json
import urllib.request
from playwright.async_api import async_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def test_danger_modal():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1400, 'height': 900})
        page = await context.new_page()

        print("[Step 1] 테스트용 골든 템플릿 생성")
        tpl_req = urllib.request.Request(
            "http://127.0.0.1:8000/api/golden/save",
            data=json.dumps({
                "name": "Production_Critical_Template",
                "description": "중요 보안 정책 템플릿",
                "os_type": "iosxe",
                "selected_items": [{"id": "hostname", "label": "hostname", "expected": "PROD", "section": "global", "match_type": "exact"}],
                "conditional_rules": [],
                "golden_parsed": {}
            }).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(tpl_req) as resp:
            tpl_data = json.loads(resp.read().decode())
        tid = tpl_data["template_id"]
        print(f"  -> 템플릿 생성 완료 (id: {tid})")

        print("[Step 2] Golden 탭으로 이동 및 템플릿 목록 로드")
        await page.goto("http://127.0.0.1:8000/")
        await page.wait_for_load_state("networkidle")
        await page.locator('[data-tab="tab-golden"]').click()
        await page.wait_for_timeout(600)

        # 삭제 버튼 탐색
        del_btn = page.locator(f'button[onclick*="{tid}"][onclick*="deleteTemplate"]')
        assert await del_btn.count() > 0, "Delete button must exist in table"
        print("  -> 삭제 대상 템플릿 버튼 발견")

        print("[Step 3] 삭제 버튼 클릭 시 강력한 경고 모달 팝업 검증")
        await del_btn.click()
        await page.wait_for_selector('#danger-confirm-modal', state="visible", timeout=3000)

        modal = page.locator('#danger-confirm-modal')
        title = await page.locator('.danger-modal-title').text_content()
        target_name = await page.locator('#danger-modal-target-name').text_content()
        alert_box = page.locator('.danger-alert-box')

        print(f"  -> 경고 모달 제목: '{title}'")
        print(f"  -> 삭제 대상 이름: {target_name}")
        assert "영구 삭제" in title, "Modal title must warn permanent deletion"
        assert "Production_Critical_Template" in target_name, "Target name must be clearly shown"
        assert await alert_box.is_visible(), "Danger alert box must be visible"

        # 스크린샷 캡처
        await page.screenshot(path="C:/Users/skullq/.gemini/antigravity-ide/brain/d2bb69c2-a3a5-4163-a411-28309037e688/danger_warning_modal_verified.png")
        print("  -> danger_warning_modal_verified.png 캡처 완료")

        print("[Step 4] [취소 (유지)] 클릭 시 템플릿 유지 및 모달 닫힘 검증")
        cancel_btn = modal.locator('button:has-text("취소")')
        await cancel_btn.click()
        await page.wait_for_timeout(300)
        assert not await modal.is_visible(), "Modal should be closed after cancel"
        
        # 목록에 템플릿이 여전히 존재하는지 확인
        assert await del_btn.count() > 0, "Template must NOT be deleted after cancel"
        print("  -> 취소 시 모달 정상 닫힘 및 템플릿 안전 유지 확인")

        print("[Step 5] [🚨 영구 삭제 진행] 클릭 시 삭제 및 연동 완료 검증")
        await del_btn.click()
        await page.wait_for_selector('#danger-confirm-modal', state="visible")
        
        confirm_btn = page.locator('#danger-modal-confirm-btn')
        await confirm_btn.click()
        await page.wait_for_timeout(800)

        # 모달 닫힘 확인
        assert not await modal.is_visible(), "Modal should be closed after confirm"
        
        # 목록에서 삭제되었는지 확인
        del_btn_after = page.locator(f'button[onclick*="{tid}"][onclick*="deleteTemplate"]')
        assert await del_btn_after.count() == 0, "Template must be deleted from table"
        print("  -> 영구 삭제 진행 후 목록에서 정상 제거 확인")

        print("=== 강력한 경고 모달 E2E 테스트 100% 성공! ===")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_danger_modal())
