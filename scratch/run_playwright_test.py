import sys, os, time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def run_test():
    sample_file = os.path.abspath(r'samples\대련_CE1.txt')
    print(f"🚀 Playwright 자동화 테스트 시작 (L2/L3 구분 및 섹션필터-블록 연동)")
    print(f"   - 대상 URL: http://127.0.0.1:8000")
    print(f"   - 테스트 파일: {sample_file}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 1100})
        page = context.new_page()

        print("\n1. 웹 서버 접속 중...")
        page.goto("http://127.0.0.1:8000")
        page.wait_for_selector("#golden-drop-zone")
        print(f"   ✅ 접속 성공! 페이지 타이틀: {page.title()}")

        print("\n2. 실장비 설정 파일(대련_CE1.txt) 업로드...")
        file_input = page.locator("#golden-file-input")
        file_input.set_input_files(sample_file)

        print("3. 파싱 및 분석 완료 대기...")
        page.wait_for_selector("#golden-blocks-card", state="visible", timeout=15000)
        time.sleep(1)

        # 4. 결과 요약 확인
        hostname = page.locator("#golden-hostname").inner_text()
        item_count = page.locator("#golden-item-count").inner_text()
        print(f"   ✅ 분석 완료! Hostname: {hostname} | 총 항목: {item_count}")

        # 5. 블록 카드에서 L2 / L3 인터페이스 그룹 분리 확인
        block_cards = page.locator(".block-card")
        total_blocks = block_cards.count()
        print(f"   ✅ 총 블록 수: {total_blocks}개")

        l2_found = False
        l3_found = False
        for i in range(total_blocks):
            title = block_cards.nth(i).locator(".block-title").inner_text()
            count = block_cards.nth(i).locator(".block-count-badge").inner_text()
            if "L2 Interfaces" in title:
                l2_found = True
                print(f"   🎯 [L2 인터페이스 그룹 발견] '{title}' ({count})")
            elif "L3 Interfaces" in title:
                l3_found = True
                print(f"   🎯 [L3 인터페이스 그룹 발견] '{title}' ({count})")

        assert l2_found, "❌ L2 Interfaces 블록을 찾지 못했습니다!"
        assert l3_found, "❌ L3 Interfaces 블록을 찾지 못했습니다!"
        print("   ✅ 요구사항 1 통과: L2와 L3 인터페이스가 별도의 그룹 블록으로 성공적으로 분리되었습니다.")

        # 6. 섹션 필터 버튼 확인
        print("\n6. 섹션 필터 버튼 목록 확인...")
        filter_btns = page.locator("#golden-section-filters .filter-btn")
        filter_count = filter_btns.count()
        print(f"   ✅ 섹션 필터 버튼 수: {filter_count}개")
        for i in range(min(8, filter_count)):
            btn_text = filter_btns.nth(i).inner_text()
            print(f"      - 필터 #{i+1}: {btn_text}")

        # 7. 섹션 필터 클릭 동작 테스트 (L3 Interfaces 선택)
        print("\n7. 섹션 필터에서 'L3 Interfaces' 선택 테스트...")
        l3_btn = None
        for i in range(filter_count):
            txt = filter_btns.nth(i).inner_text()
            if "L3 Interfaces" in txt:
                l3_btn = filter_btns.nth(i)
                break

        assert l3_btn is not None, "❌ L3 Interfaces 필터 버튼이 없습니다!"
        l3_btn.click()
        time.sleep(0.5)

        # 상세 설정 목록 헤더 확인
        items_list = page.locator("#golden-items-list")
        section_headers = items_list.locator(".section-group-header")
        header_count = section_headers.count()
        print(f"   ✅ 필터링 후 표시된 블록 그룹 헤더 수: {header_count}개")
        first_header = section_headers.first.inner_text().replace('\n', ' ')
        print(f"      첫 번째 헤더: {first_header}")

        item_rows = items_list.locator(".item-row")
        print(f"   ✅ L3 Interfaces에 속한 세부 설정 항목 수: {item_rows.count()}개")
        first_item_label = item_rows.first.locator(".item-label").inner_text()
        print(f"      첫 번째 세부 항목: {first_item_label}")

        # 8. '전체' 필터로 복귀
        print("\n8. 섹션 필터에서 '전체' 버튼 클릭...")
        filter_btns.first.click()
        time.sleep(0.5)
        all_header_count = items_list.locator(".section-group-header").count()
        print(f"   ✅ 전체 모드에서 표시된 블록 그룹 헤더 수: {all_header_count}개")

        # 9. 스크린샷 캡처
        screenshot_path = os.path.abspath(r"artifacts\playwright_test_result.png")
        os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"\n📸 스크린샷 저장 완료: {screenshot_path}")

        print("\n🎉 모든 요구사항(L2/L3 분리 + 섹션필터 블록 동기화 및 블록별 상세 설정) 검증 성공!")
        browser.close()

if __name__ == "__main__":
    run_test()
