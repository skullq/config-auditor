"""
tests/test_audit_e2e_playwright.py
Playwright 기반 E2E UI 및 기능 자동화 테스트

실행 방법:
  1) VSCode Test Explorer(Testing 탭)에서 재생(▶) 버튼 클릭
  2) 터미널 실행:
     uv run pytest tests/test_audit_e2e_playwright.py -v
     uv run pytest tests/test_audit_e2e_playwright.py --headed  (브라우저 화면 보면서 실행)
"""

import os
import re
import json
import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")


@pytest.fixture(scope="session")
def setup_test_golden_template():
    """테스트용 골든 템플릿을 API로 사전 등록하고 테스트 후 정리."""
    import httpx
    
    golden_cfg = """!
hostname Standard-Core01
version 17.3
ntp server 10.0.0.1
username admin privilege 15 secret adminpass
interface GigabitEthernet1/0/1
 description ## ACCESS PORT ##
 switchport mode access
 switchport access vlan 10
!
"""
    # 1. 업로드
    r = httpx.post(f"{BASE_URL}/api/golden/upload?os=iosxe", files={"file": ("std_golden.cfg", golden_cfg, "text/plain")})
    assert r.status_code == 200, f"Upload failed: {r.text}"
    up_data = r.json()

    # 2. 템플릿 저장
    save_payload = {
        "name": "E2E-Playwright-Standard",
        "hostname_regex": ".*",
        "description": "Playwright 자동 검증용 골든 템플릿",
        "os_type": "iosxe",
        "selected_items": up_data["general_items"],
        "conditional_rules": [],
        "golden_parsed": up_data["parsed"]
    }
    r = httpx.post(f"{BASE_URL}/api/golden/save", json=save_payload)
    assert r.status_code == 200
    tid = r.json()["template_id"]

    yield tid

    # 정리
    try:
        httpx.delete(f"{BASE_URL}/api/golden/templates/{tid}")
    except Exception:
        pass


def test_homepage_and_navigation(page: Page):
    """홈페이지 접근 및 탭 전환 검증."""
    page.goto(BASE_URL)
    expect(page).to_have_title("Network Config Auditor")

    # 탭 네비게이션 버튼 확인
    golden_tab = page.locator('button[data-tab="tab-golden"]')
    compare_tab = page.locator('button[data-tab="tab-compare"]')
    report_tab = page.locator('button[data-tab="tab-report"]')

    expect(golden_tab).to_be_visible()
    expect(compare_tab).to_be_visible()
    expect(report_tab).to_be_visible()

    # Compare 탭 클릭
    compare_tab.click()
    expect(page.locator("#tab-compare")).to_be_visible()


def test_compare_flow_with_extra_configs_diff(page: Page, setup_test_golden_template):
    """
    골든 준수율 100%이지만 추가된 미인가/보안 위협 설정이 있는 파일 비교 & Diff 및 롤백 UI 검증
    """
    tid = setup_test_golden_template
    page.goto(BASE_URL)

    # 1. Compare 탭으로 이동
    page.locator('button[data-tab="tab-compare"]').click()
    page.wait_for_selector(f"#tpl-node-{tid}", timeout=10000)

    # 2. 골든 룰 100% + 비인가 계정/SNMP/라우팅 추가 설정 파일 생성
    target_config_content = """!
hostname Standard-Core01
version 17.3
ntp server 10.0.0.1
username admin privilege 15 secret adminpass
username backdoor_user privilege 15 secret hack123
snmp-server community public RW
interface GigabitEthernet1/0/1
 description ## ACCESS PORT ##
 switchport mode access
 switchport access vlan 10
 no switchport port-security
!
router ospf 99
 network 10.99.0.0 0.0.0.255 area 0
!
"""
    file_input = page.locator(f"#file-input-{tid}")
    file_input.set_input_files({
        "name": "Target-Switch-Extra.cfg",
        "mimeType": "text/plain",
        "buffer": target_config_content.encode("utf-8")
    })

    # 3. 비교 결과 행(Tr) 생성 대기
    page.wait_for_selector(".compare-view-btn", timeout=15000)

    # 준수율 100% 점수 표시 확인
    expect(page.locator("td.col-score").first).to_contain_text("100%")

    # 4. 상세 보기(🔍) 버튼 클릭 -> 드로어 오픈
    page.locator(".compare-view-btn").first.click()
    drawer = page.locator("#compare-drawer")
    import re
    expect(drawer).to_have_class(re.compile(r"\bopen\b"))

    # 5. 헤더 메타 영역 확인: 100% Pass 및 '⚠️ 미인가/추가 설정 N건 감지' 문구 확인
    expect(page.locator("#drawer-score")).to_have_text("100%")
    expect(page.locator("#drawer-meta")).to_contain_text("미인가/추가 설정")

    # 6. 3-Tab 시스템 렌더링 확인
    golden_tab_btn = page.locator('button.result-tab-btn[data-tab="golden"]')
    extra_tab_btn = page.locator('button.result-tab-btn[data-tab="extra"]')
    rollback_tab_btn = page.locator('button.result-tab-btn[data-tab="rollback"]')

    expect(golden_tab_btn).to_be_visible()
    expect(extra_tab_btn).to_be_visible()
    expect(rollback_tab_btn).to_be_visible()

    # 7. '⚠️ 추가된 설정 Diff' 탭 클릭 및 상세 카드 검증
    extra_tab_btn.click()
    expect(page.locator("#tab-content-extra")).to_be_visible()

    # 위험도 배지 및 diff 라인 노출 확인
    expect(page.locator(".extra-alert-banner")).to_be_visible()
    expect(page.locator(".extra-item-card.danger").first).to_be_visible()

    # Diff 표시(+ 기호) 및 실제 추가 라인 검증
    expect(page.locator(".extra-diff-line").first).to_contain_text("+")

    # 개별 롤백 명령어 확인
    expect(page.locator(".extra-rollback-cmd").first).to_contain_text("no ")

    # 8. '⚡ 롤백 CLI 스크립트' 탭 클릭 및 전문 확인
    rollback_tab_btn.click()
    expect(page.locator("#tab-content-rollback")).to_be_visible()
    script_pre = page.locator("#rollback-script-content")
    expect(script_pre).to_be_visible()
    expect(script_pre).to_contain_text("configure terminal")
    expect(script_pre).to_contain_text("no username backdoor_user")
    expect(script_pre).to_contain_text("no snmp-server community public")
    expect(script_pre).to_contain_text("no router ospf 99")
    expect(script_pre).to_contain_text("write memory")

    # 9. Clean Config 다운로드 버튼 확인
    clean_btn = page.locator('button:has-text("Clean Config 다운로드")')
    expect(clean_btn).to_be_visible()

    # 드로어 닫기
    page.locator(".drawer-close-btn").click()
    expect(drawer).not_to_have_class(re.compile(r"\bopen\b"))


def test_golden_drawer_ui_modernized(page: Page, setup_test_golden_template):
    """
    모던화된 Golden 탭의 카드 그리드 및 우측 슬라이드오버 드로어(Side Drawer) 동작 검증
    """
    tid = setup_test_golden_template
    page.goto(BASE_URL)

    # 1. Golden 탭으로 이동
    golden_tab_btn = page.locator('button[data-tab="tab-golden"]')
    golden_tab_btn.click()
    expect(page.locator("#tab-golden")).to_be_visible()

    # 2. 템플릿 카드 목록 컨테이너 확인
    cards_container = page.locator("#golden-templates-list")
    expect(cards_container).to_be_visible()

    # fixture로 생성된 템플릿 카드 탐색
    card = page.locator(f"#golden-card-{tid}")
    expect(card).to_be_visible(timeout=5000)
    expect(card).to_contain_text("E2E-Playwright-Standard")

    # 3. 우측 드로어 요소 확인 (초기에는 닫힘 상태)
    drawer = page.locator("#golden-drawer")
    expect(drawer).not_to_have_class(re.compile(r"\bopen\b"))

    # 4. 카드 내 [✏️ 편집] 버튼 클릭 -> 우측 드로어가 스르륵 열림
    edit_btn = card.locator('button:has-text("편집")')
    edit_btn.click()

    # 드로어가 open 클래스를 갖는지 검증
    expect(drawer).to_have_class(re.compile(r"\bopen\b"), timeout=5000)

    # 템플릿 이름 및 헤더 메타데이터가 드로어 폼에 로드되었는지 확인
    name_input = page.locator("#golden-template-name")
    expect(name_input).to_have_value("E2E-Playwright-Standard")

    # 5. 서브 탭 전환 인터랙션 검증
    # 탭 1: 계층형 룰 편집기
    rules_pane = page.locator("#drawer-tab-rules")
    expect(rules_pane).to_be_visible()
    expect(page.locator("#golden-items-list")).to_be_visible()

    # 탭 2: 실시간 CLI 미리보기
    preview_tab_btn = page.locator('button[data-tab="preview"]')
    preview_tab_btn.click()
    preview_pane = page.locator("#drawer-tab-preview")
    expect(preview_pane).to_be_visible()
    expect(page.locator("#golden-live-preview-code")).to_be_visible()

    # 탭 3: 매칭 방식 가이드
    guide_tab_btn = page.locator('button[data-tab="guide"]')
    guide_tab_btn.click()
    guide_pane = page.locator("#drawer-tab-guide")
    expect(guide_pane).to_be_visible()

    # 6. 드로어 닫기 버튼 클릭 -> 드로어 닫힘 확인
    close_btn = drawer.locator('button:has-text("닫기")').first
    close_btn.click()
    expect(drawer).not_to_have_class(re.compile(r"\bopen\b"))


def test_template_modification_impact_flow(page: Page, setup_test_golden_template):
    """
    골든 템플릿 수정 시 연동된 Compare 장비 영향 감지, 전역 알림, 영향 분석 모달 및 승인/롤백 워크플로우 검증
    """
    import httpx
    tid = setup_test_golden_template

    # 1. 템플릿 정보 가져오기 및 Compare 감사 결과 1건 사전 생성
    r = httpx.get(f"{BASE_URL}/api/golden/templates/{tid}")
    assert r.status_code == 200
    tpl_data = r.json()

    # 타겟 장비 1대 감사 생성
    target_cfg = """!
hostname Standard-Core01
version 17.3
ntp server 10.0.0.1
username admin privilege 15 secret adminpass
interface GigabitEthernet1/0/1
 switchport mode access
 switchport access vlan 10
!"""
    r_up = httpx.post(f"{BASE_URL}/api/compare/upload?os=iosxe", files={"file": ("target1.cfg", target_cfg, "text/plain")})
    parsed_target = r_up.json()["parsed"]

    r_run = httpx.post(f"{BASE_URL}/api/compare/run", json={
        "template_id": tid,
        "parsed": parsed_target,
        "filename": "target1.cfg",
        "save": True
    })
    assert r_run.status_code == 200

    # 2. 골든 템플릿에 새로운 규칙 1개 추가하여 수정 저장 (수정 발생)
    original_items = list(tpl_data["golden_items"])
    modified_items = list(original_items) + [{
        "id": "item_sys_logging_test",
        "block_id": "System",
        "section": "general",
        "command_line": "logging buffered 64000",
        "expected_value": "64000",
        "match_type": "exact",
        "weight": "required",
        "selected": True
    }]

    r_save = httpx.post(f"{BASE_URL}/api/golden/save", json={
        "name": tpl_data["name"],
        "description": "수정된 테스트 템플릿",
        "os_type": tpl_data.get("os", "iosxe"),
        "selected_items": modified_items,
        "golden_parsed": tpl_data["golden_parsed"],
        "template_id": tid
    })
    assert r_save.status_code == 200

    # 3. 브라우저 페이지 방문 및 전역 인지(Alert Banner & Badges) 검증
    page.goto(BASE_URL)

    # 전역 배너 노출 확인
    banner = page.locator("#global-template-impact-banner")
    expect(banner).to_be_visible(timeout=5000)
    expect(banner).to_contain_text("골든 템플릿 변경 감지")

    # 탭 네비게이션 뱃지 노출 확인
    golden_badge = page.locator("#nav-golden-pending-badge")
    compare_badge = page.locator("#nav-compare-pending-badge")
    expect(golden_badge).to_be_visible()
    expect(compare_badge).to_be_visible()

    # Compare 탭으로 이동해도 상단 배너가 계속 유지되는지 확인 (어떤 탭에서든 인지 가능)
    page.locator('button[data-tab="tab-compare"]').click()
    expect(banner).to_be_visible()

    # Compare 템플릿 노드 내 경고 배너 확인
    compare_ribbon = page.locator(f"#tpl-node-{tid} .compare-tpl-pending-ribbon")
    expect(compare_ribbon).to_be_visible()

    # 4. [변경 영향 분석 및 결정] 클릭 -> 모달 오픈
    review_btn = page.locator("#global-impact-review-btn")
    review_btn.click()

    modal = page.locator("#template-impact-modal")
    expect(modal).to_be_visible(timeout=5000)

    # 모달 내 Diff에 추가된 룰('logging buffered 64000') 표시 확인
    diff_list = page.locator("#impact-rule-diff-list")
    expect(diff_list).to_contain_text("logging buffered 64000")

    # 모달 내 영향받는 장비 목록에 'target1.cfg' 또는 'Standard-Core01' 표시 확인
    devices_table = page.locator("#impact-devices-tbody")
    expect(devices_table).to_contain_text("Standard-Core01")

    # 5. [🔄 템플릿 변경사항 롤백 (이전 버전 복원)] 클릭
    rollback_btn = page.locator("#impact-rollback-btn")
    rollback_btn.click()

    # 모달 닫힘 및 전역 알림 배너 자동 제거 확인
    expect(modal).not_to_be_visible()
    expect(banner).not_to_be_visible(timeout=5000)
    expect(golden_badge).not_to_be_visible()
    expect(compare_badge).not_to_be_visible()

    # 6. 롤백 후 템플릿 룰이 원래대로 복원되었는지 API로 재검증
    r_check = httpx.get(f"{BASE_URL}/api/golden/templates/{tid}")
    assert r_check.status_code == 200
    rolled_back_items = r_check.json()["golden_items"]
    # 추가했던 'logging buffered 64000'이 없어야 함
    assert not any(i.get("command_line") == "logging buffered 64000" for i in rolled_back_items)


def test_template_edit_unselected_items_and_footer_removal(page: Page, setup_test_golden_template):
    """
    골든 템플릿 수정 시:
    1. 하단 푸터(저장/닫기 중복 버튼)가 완전히 제거되었는지 확인.
    2. 이전에 선택되지 않았던 항목이 체크 해제 상태 및 취소선(.strikethrough / unselected)으로 표시되는지 확인.
    3. 미선택 항목을 다시 클릭하여 활성화/저장할 수 있는지 검증.
    """
    tid = setup_test_golden_template
    page.goto(BASE_URL)

    # 1. 템플릿 카드의 [편집] 버튼 클릭하여 에디터 드로어 열기
    card = page.locator(f"#golden-card-{tid}")
    expect(card).to_be_visible(timeout=5000)
    card.locator('button:has-text("편집")').click()

    drawer = page.locator("#golden-drawer")
    expect(drawer).to_be_visible()

    # 2. [요구사항 1 검증] 하단 푸터 및 하단 저장/닫기 버튼이 존재하지 않아야 함
    expect(page.locator(".golden-drawer-footer")).to_have_count(0)
    expect(page.locator("#golden-drawer-save-btn")).to_have_count(0)

    # 상단 헤더 저장/닫기 버튼은 정상 존재해야 함
    expect(page.locator("#golden-save-btn")).to_be_visible()
    expect(drawer.locator('button:has-text("닫기")')).to_be_visible()

    # 3. 항목 중 1개를 체크 해제 -> 즉시 취소선(.strikethrough) 및 unselected 클래스 적용 확인
    first_check = page.locator(".tree-leaf-row .item-check").first
    first_row = page.locator(".tree-leaf-row").first
    first_label = first_row.locator(".tree-leaf-label")
    expect(first_check).to_be_checked()
    
    # 체크 해제
    first_check.click()
    expect(first_check).not_to_be_checked()
    expect(first_row).to_have_class(re.compile(r"\bunselected\b"))
    expect(first_label).to_have_class(re.compile(r"\bstrikethrough\b"))

    # 4. 저장하기 클릭 -> 템플릿 저장 완료 후 드로어 자동 닫힘 확인
    page.locator("#golden-save-btn").click()
    expect(drawer).not_to_have_class(re.compile(r"\bopen\b"), timeout=5000)

    # 연동 Compare 장비 영향 분석 모달이 열리면 [변경사항 허용 & 일괄 재감사 반영] 클릭
    impact_modal = page.locator("#template-impact-modal")
    try:
        expect(impact_modal).to_be_visible(timeout=3000)
        page.locator("#impact-accept-btn").click()
        expect(impact_modal).not_to_be_visible(timeout=5000)
    except Exception:
        pass

    # 5. [핵심 사용자 시나리오] 템플릿을 다시 [편집]으로 열었을 때,
    # 이전에 제외(체크 해제)했던 항목이 사라지지 않고 취소선 및 미선택 상태로 보존되는지 검증
    card.locator('button:has-text("편집")').click()
    expect(drawer).to_have_class(re.compile(r"\bopen\b"), timeout=5000)

    unselected_row = page.locator(".tree-leaf-row").first
    expect(unselected_row).to_be_visible(timeout=5000)
    expect(unselected_row).to_have_class(re.compile(r"\bunselected\b"))
    unselected_label = unselected_row.locator(".tree-leaf-label")
    expect(unselected_label).to_have_class(re.compile(r"\bstrikethrough\b"))
    unselected_check = unselected_row.locator(".item-check")
    expect(unselected_check).not_to_be_checked()

    # 6. 미선택 항목을 다시 클릭하여 골든 룰에 재포함 -> 취소선 해제 및 활성화 확인
    unselected_check.click()
    expect(unselected_check).to_be_checked()
    expect(unselected_row).not_to_have_class(re.compile(r"\bunselected\b"))
    expect(unselected_label).not_to_have_class(re.compile(r"\bstrikethrough\b"))

    # 드로어 닫기
    drawer.locator('button:has-text("닫기")').first.click()
    expect(drawer).not_to_have_class(re.compile(r"\bopen\b"))


def test_interface_profiles_flow(page: Page, setup_test_golden_template):
    """인터페이스 정책 프로파일(L2/L3) 서브탭 UI 및 생성/저장 플로우 검증."""
    tid = setup_test_golden_template
    page.goto(BASE_URL)

    # 1. Golden 탭으로 이동
    page.locator('button[data-tab="tab-golden"]').click()
    page.wait_for_selector(f"#golden-card-{tid}", timeout=10000)

    # 2. [편집] 클릭 -> 드로어 열기
    card = page.locator(f"#golden-card-{tid}")
    card.locator('button:has-text("편집")').click()
    drawer = page.locator("#golden-drawer")
    expect(drawer).to_have_class(re.compile(r"\bopen\b"))

    # 3. [🏷️ 인터페이스 정책 (L2/L3 Profiles)] 서브 탭 클릭
    prof_tab_btn = page.locator('button.golden-drawer-tab-btn[data-tab="profiles"]')
    expect(prof_tab_btn).to_be_visible()
    prof_tab_btn.click()
    expect(page.locator("#drawer-tab-profiles")).to_be_visible()

    # 4. [➕ 새 프로파일 추가] 버튼 클릭 -> 모달 오픈
    page.locator("#add-profile-btn").click()
    modal = page.locator("#profile-edit-modal")
    expect(modal).to_be_visible()

    # 5. 프로파일 정보 입력
    page.locator("#prof-name").fill("E2E-Uplink-Trunk-Policy")
    page.locator("#prof-target-type").select_option("l2")
    page.locator("#prof-name-mtype").select_option("exists")
    page.locator("#prof-desc-mtype").select_option("contains")
    page.locator("#prof-desc-pattern").fill("UPLINK")

    # 룰 추가
    page.locator("#prof-new-rule-cmd").fill("switchport mode trunk")
    page.locator("#prof-new-rule-mtype").select_option("exact")
    page.locator('button:has-text("➕ 추가")').click()

    # 테이블에 추가된 룰 확인
    expect(page.locator("#prof-rules-tbody")).to_contain_text("switchport mode trunk")

    # 6. [💾 프로파일 저장] 클릭 -> 모달 닫히고 프로파일 카드 렌더링 확인
    page.locator('button:has-text("💾 프로파일 저장")').click()
    expect(modal).not_to_be_visible()
    expect(page.locator("#golden-profiles-list")).to_contain_text("E2E-Uplink-Trunk-Policy")
    expect(page.locator("#golden-profiles-list")).to_contain_text("L2 스위치포트")

    # 7. 계층형 룰 편집기 서브탭으로 전환하여 인터페이스 위임 배너 확인
    rules_tab_btn = page.locator('button.golden-drawer-tab-btn[data-tab="rules"]')
    rules_tab_btn.click()
    expect(page.locator("#drawer-tab-rules")).to_be_visible()

    # 인터페이스 블록이 렌더링되어 있다면 위임 배너 확인
    intf_tip = page.locator(".intf-delegation-tip")
    if intf_tip.count() > 0:
        expect(intf_tip.first).to_be_visible()
        delegate_btn = intf_tip.first.locator(".block-delegate-profiles-btn")
        if delegate_btn.is_visible():
            delegate_btn.click()
            # 토스트 또는 선택 해제 동작 검증

    # 8. 드로어 상단 [💾 저장하기] 클릭
    page.locator("#golden-save-btn").click()
    expect(drawer).not_to_have_class(re.compile(r"\bopen\b"), timeout=5000)




