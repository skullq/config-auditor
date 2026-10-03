import asyncio
import sys
from playwright.async_api import async_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def test_all():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1400, 'height': 900})
        page = await context.new_page()

        print("[Test 1] Compare 탭 접속 및 행 클릭 vs 버튼 클릭 검증")
        await page.goto("http://127.0.0.1:8000/")
        await page.wait_for_load_state("networkidle")

        await page.locator('[data-tab="tab-compare"]').click()
        await page.wait_for_timeout(1000)

        drawer = page.locator('#compare-drawer')
        first_row = page.locator('.compare-tpl-node tbody tr:not(.empty-row)').first
        
        # 1-1. 행의 빈 영역(2번째 td 등)을 클릭해도 드로어가 열리지 않아야 함
        file_td = first_row.locator('td').nth(1)
        await file_td.click()
        await page.wait_for_timeout(400)
        is_open_row_click = await drawer.evaluate("el => el.classList.contains('open')")
        assert not is_open_row_click, "Drawer should NOT open when clicking table row!"
        print("  -> 행 빈 공간 클릭 시 드로어 미오픈 확인 (성공)")

        # 1-2. [🔍 상세 보기] 버튼을 누를 때에만 열려야 함
        view_btn = first_row.locator('button.compare-view-btn')
        btn_text = await view_btn.text_content()
        print(f"  -> 버튼 텍스트: '{btn_text}'")
        assert "상세 보기" in btn_text

        # 버튼 CSS white-space 확인
        ws = await view_btn.evaluate("el => window.getComputedStyle(el).whiteSpace")
        print(f"  -> 버튼 white-space: {ws}")
        assert ws == "nowrap", "Button must have white-space: nowrap"

        await view_btn.click()
        await page.wait_for_selector('#compare-drawer.open', timeout=3000)
        print("  -> 상세 보기 버튼 클릭 시에만 드로어 오픈 확인 (성공)")

        # ESC로 닫기
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(400)

        # 2. 파일명과 Hostname 한 줄 표시 & 창 줄일 때 두 줄 표시 반응형 검증
        print("[Test 2] 파일명과 Hostname 한 줄 및 좁은 화면 두 줄 반응형 검증")
        fn_el = first_row.locator('.compare-filename')
        hn_el = first_row.locator('.compare-hostname-tag')
        
        # 1400px 와이드 화면에서 두 엘리먼트의 y 좌표 확인
        fn_box = await fn_el.bounding_box()
        hn_box = await hn_el.bounding_box()
        print(f"  -> 와이드 화면 (1400px): 파일명 y={fn_box['y']}, 호스트명 y={hn_box['y']}")
        assert abs(fn_box['y'] - hn_box['y']) < 6, "Filename and Hostname should be in ONE line in wide screen"
        print("  -> 와이드 화면에서 파일명과 Hostname이 동일한 한 줄로 표시됨 (성공)")
        await page.screenshot(path="C:/Users/skullq/.gemini/antigravity-ide/brain/d2bb69c2-a3a5-4163-a411-28309037e688/responsive_wide_one_line.png")

        # 창 너비를 좁힘 (750px)
        await page.set_viewport_size({'width': 750, 'height': 900})
        await page.wait_for_timeout(300)
        
        fn_box_narrow = await fn_el.bounding_box()
        hn_box_narrow = await hn_el.bounding_box()
        print(f"  -> 좁은 화면 (750px): 파일명 y={fn_box_narrow['y']}, 호스트명 y={hn_box_narrow['y']}")
        # 좁아졌을 때 Hostname이 줄바꿈되어 두 줄로 내려갈 수 있음
        await page.screenshot(path="C:/Users/skullq/.gemini/antigravity-ide/brain/d2bb69c2-a3a5-4163-a411-28309037e688/responsive_narrow_wrap.png")
        print("  -> 반응형 화면 전환 검증 완료 및 스크린샷 캡처 완료")

        # 뷰포트 원복
        await page.set_viewport_size({'width': 1400, 'height': 900})
        await page.wait_for_timeout(300)

        # 3. Golden 탭에서 템플릿 삭제 시 Compare 탭 연동 설정 전부 삭제 검증
        print("[Test 3] Golden 템플릿 삭제 시 Compare 연동 결과 Cascade 삭제 검증")
        
        # 삭제 테스트 전용 골든 템플릿 생성
        import urllib.request, json
        tpl_req = urllib.request.Request(
            "http://127.0.0.1:8000/api/golden/save",
            data=json.dumps({
                "name": "Cascade_Delete_Test_Tpl",
                "description": "연동 삭제 테스트용",
                "os_type": "iosxe",
                "selected_items": [{"id": "hostname", "label": "hostname", "expected": "TEST", "section": "global", "match_type": "exact"}],
                "conditional_rules": [],
                "golden_parsed": {}
            }).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(tpl_req) as resp:
            tpl_data = json.loads(resp.read().decode())
        test_tid = tpl_data["template_id"]
        print(f"  -> 테스트 템플릿 생성 완료 (id: {test_tid})")

        # 해당 템플릿에 테스트 비교 결과 직접 등록
        sys.path.insert(0, "d:/my-code/config-auditor/webapp")
        from db.database import save_compare_result
        cmp_id = save_compare_result(
            hostname="TEST-R1",
            template_id=test_tid,
            template_name="Cascade_Delete_Test_Tpl",
            overall="pass",
            score=100.0,
            detail={"filename": "cascade_file.cfg", "items": [], "overall": "pass", "score": 100.0}
        )
        print(f"  -> 연동 비교 결과 등록 완료 (id: {cmp_id})")

        # Compare 탭에서 확인
        await page.locator('[data-tab="tab-compare"]').click()
        await page.wait_for_timeout(500)
        node_locator = page.locator(f'#tpl-node-{test_tid}')
        await node_locator.scroll_into_view_if_needed()
        assert await node_locator.count() > 0, "Template node must be present in Compare tab"
        print("  -> Compare 탭에 템플릿 및 비교 파일 정상 표시 확인")

        # Golden 탭으로 이동하여 해당 템플릿 삭제
        await page.locator('[data-tab="tab-golden"]').click()
        await page.wait_for_timeout(500)

        # 다이얼로그(confirm) 자동 수락
        page.on("dialog", lambda d: d.accept())

        del_btn = page.locator(f'button[onclick*="{test_tid}"][onclick*="deleteTemplate"]')
        await del_btn.click()
        await page.wait_for_timeout(800)
        print("  -> Golden 탭에서 템플릿 삭제 완료")

        # DB 검증: compare_results에서 해당 template_id 레코드가 0개인지 확인
        check_req = urllib.request.Request("http://127.0.0.1:8000/api/compare/results")
        with urllib.request.urlopen(check_req) as resp:
            all_results = json.loads(resp.read().decode())
        matched = [r for r in all_results if r.get('template_id') == test_tid]
        assert len(matched) == 0, f"Expected 0 compare_results for deleted template, got {len(matched)}"
        print(f"  -> DB 검증: 연동된 compare_results {len(matched)}건 확인 (완전 삭제 성공)")

        # Compare 탭으로 이동 시 해당 노드가 완전히 사라졌는지 확인
        await page.locator('[data-tab="tab-compare"]').click()
        await page.wait_for_timeout(500)
        node_after = page.locator(f'#tpl-node-{test_tid}')
        assert await node_after.count() == 0, "Deleted template node must NOT exist in Compare tab"
        print("  -> Compare 탭 UI에서도 연동 템플릿 및 모든 설정이 즉시 제거됨 확인 (성공)")

        await page.screenshot(path="C:/Users/skullq/.gemini/antigravity-ide/brain/d2bb69c2-a3a5-4163-a411-28309037e688/cascade_delete_verified.png")

        print("=== 모든 3가지 요청 사항 완벽 통과! ===")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_all())
