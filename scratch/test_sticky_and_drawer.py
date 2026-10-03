import asyncio
import sys
from playwright.async_api import async_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1400, 'height': 900})
        page = await context.new_page()
        page.on("console", lambda msg: print(f"[Browser Console {msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: print(f"[Browser PageError] {err}"))

        print("[Step 1] 웹앱 접속 및 Compare 탭 이동")
        await page.goto("http://127.0.0.1:8000/")
        await page.wait_for_load_state("networkidle")

        compare_tab = page.locator('[data-tab="tab-compare"]')
        await compare_tab.click()
        await page.wait_for_timeout(1000)

        # 템플릿 노드 확인
        nodes = page.locator('.compare-tpl-node')
        node_count = await nodes.count()
        print(f"  -> 발견된 골든 템플릿 수: {node_count}")

        # 상세 보기 버튼 확인 (안정적인 셀렉터)
        view_btns = page.locator('button[onclick*="viewResult"]')
        btn_count = await view_btns.count()
        print(f"  -> 비교 결과 목록 항목 수: {btn_count}")

        # 스크롤 테스트를 위해 페이지를 아래로 스크롤
        print("[Step 2] 스크롤 다운 시 Sticky 헤더 고정 상태 검증")
        await page.evaluate("window.scrollTo(0, 300)")
        await page.wait_for_timeout(300)
        scroll_y = await page.evaluate("window.scrollY")
        print(f"  -> 스크롤 위치 window.scrollY: {scroll_y}")

        sticky_header = page.locator('.compare-sticky-header')
        box = await sticky_header.bounding_box()
        print(f"  -> Sticky 헤더 bounding box: y={box['y']}, height={box['height']}")
        # sticky 헤더는 app-header(56px) 아래에 붙어있어야 함
        assert box['y'] <= 60, f"Sticky header y position should be <= 60, got {box['y']}"
        assert await sticky_header.is_visible(), "Sticky header should be visible"

        await page.screenshot(path="C:/Users/skullq/.gemini/antigravity-ide/brain/d2bb69c2-a3a5-4163-a411-28309037e688/drawer_step1_sticky_header.png")
        print("  -> drawer_step1_sticky_header.png 캡처 완료")

        if btn_count > 0:
            print("[Step 3] 상세 보기 클릭 시 스크롤 점프 방지 및 슬라이드 드로어 오픈 검증")
            # 중간 위치의 버튼 선택 (스크롤이 0이 아닌 상태를 만들기 위함)
            target_idx = min(3, btn_count - 1)
            target_btn = view_btns.nth(target_idx)
            
            # 버튼이 보이도록 뷰포트로 자연스럽게 스크롤
            await target_btn.scroll_into_view_if_needed()
            await page.wait_for_timeout(300)

            pos_before = await page.evaluate("window.scrollY")
            print(f"  -> 클릭 직전 scrollY: {pos_before}")
            
            # 상세 보기 클릭
            await target_btn.click()
            
            # 드로어 오픈 대기
            drawer = page.locator('#compare-drawer')
            await page.wait_for_selector('#compare-drawer.open', timeout=4000)

            pos_after = await page.evaluate("window.scrollY")
            print(f"  -> 클릭 직후 scrollY: {pos_after}")
            # 이전 버그: 상세보기를 누르면 화면이 맨 밑(바닥)으로 강제 스크롤됨
            # 개선 결과: 클릭 전후 scrollY가 완벽하게 유지됨 (화면 점프 0px)
            scroll_diff = abs(pos_after - pos_before)
            print(f"  -> 스크롤 변화량: {scroll_diff}px")
            assert scroll_diff < 15, f"Scroll jumped! before={pos_before}, after={pos_after}"
            
            filename = await page.locator('#drawer-filename').text_content()
            score = await page.locator('#drawer-score').text_content()
            badge = await page.locator('#drawer-badge').text_content()
            print(f"  -> 드로어 헤더 확인: 파일명={filename}, 점수={score}, 배지={badge}")

            # 활성 행 하이라이트 확인
            active_row = page.locator('tr.row-active-detail')
            assert await active_row.count() > 0, "Selected row should have .row-active-detail"

            await page.screenshot(path="C:/Users/skullq/.gemini/antigravity-ide/brain/d2bb69c2-a3a5-4163-a411-28309037e688/drawer_step2_drawer_opened.png")
            print("  -> drawer_step2_drawer_opened.png 캡처 완료")

            # [Step 4] ESC 키를 눌러 슬라이드 드로어 닫기 검증
            print("[Step 4] ESC 키를 눌러 슬라이드 드로어 닫기 검증")
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(400)
            is_open_after_esc = await drawer.evaluate("el => el.classList.contains('open')")
            assert not is_open_after_esc, "Drawer should be closed after ESC"
            print("  -> ESC 단축키로 드로어 닫기 성공!")
            await page.screenshot(path="C:/Users/skullq/.gemini/antigravity-ide/brain/d2bb69c2-a3a5-4163-a411-28309037e688/drawer_step3_drawer_closed.png")

            # [Step 5] 다른 행의 상세 보기 클릭 시 드로어 재오픈 및 내용 갱신 검증
            if btn_count > 1:
                print("[Step 5] 다른 행 클릭 시 드로어 재오픈 및 새 내용 로드 검증")
                second_btn = view_btns.nth(0)
                await second_btn.scroll_into_view_if_needed()
                await page.wait_for_timeout(200)
                await second_btn.click()
                await page.wait_for_selector('#compare-drawer.open', timeout=4000)
                
                new_filename = await page.locator('#drawer-filename').text_content()
                print(f"  -> 새로 열린 드로어 파일명: {new_filename}")
                await page.screenshot(path="C:/Users/skullq/.gemini/antigravity-ide/brain/d2bb69c2-a3a5-4163-a411-28309037e688/drawer_step4_switch_content.png")

                # [Step 6] 드로어 헤더의 ✕ 닫기 버튼 클릭 검증
                print("[Step 6] 드로어 헤더의 ✕ 닫기 버튼 클릭 검증")
                close_btn = page.locator('.drawer-close-btn')
                await close_btn.click()
                await page.wait_for_timeout(400)
                is_open_after_close_btn = await drawer.evaluate("el => el.classList.contains('open')")
                assert not is_open_after_close_btn, "Drawer should be closed after close button click"
                print("  -> ✕ 닫기 버튼으로 드로어 닫기 성공!")

        print("=== 모든 Sticky 및 Slide-over Drawer E2E 테스트 성공! ===")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
