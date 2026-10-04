// @ts-check
const { test, expect } = require('@playwright/test');

test.describe('Network Config Auditor E2E Tests', () => {

  test('01. 홈페이지 접근 및 기본 탭 확인', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/Network Config Auditor/);

    await expect(page.locator('button[data-tab="tab-golden"]')).toBeVisible();
    await expect(page.locator('button[data-tab="tab-compare"]')).toBeVisible();
    await expect(page.locator('button[data-tab="tab-report"]')).toBeVisible();

    await page.locator('button[data-tab="tab-compare"]').click();
    await expect(page.locator('#tab-compare')).toBeVisible();
  });

  test('02. 골든 룰 100% 준수 + 미인가 추가 설정(Diff) 및 롤백 UI 검증', async ({ page, request }) => {
    // 1. 테스트용 골든 템플릿 사전 생성
    const goldenCfg = `!
hostname Core-Playwright-01
version 17.3
ntp server 10.0.0.1
username admin privilege 15 secret adminpass
interface GigabitEthernet1/0/1
 description ## ACCESS PORT ##
 switchport mode access
 switchport access vlan 10
!
`;
    const upRes = await request.post('/api/golden/upload?os=iosxe', {
      multipart: {
        file: {
          name: 'golden.cfg',
          mimeType: 'text/plain',
          buffer: Buffer.from(goldenCfg),
        }
      }
    });
    expect(upRes.ok()).toBeTruthy();
    const upData = await upRes.json();

    const saveRes = await request.post('/api/golden/save', {
      data: {
        name: 'Playwright-Golden-Spec',
        hostname_regex: '.*',
        description: 'VSCode Playwright Extension 검증용',
        os_type: 'iosxe',
        selected_items: upData.general_items,
        conditional_rules: [],
        golden_parsed: upData.parsed
      }
    });
    expect(saveRes.ok()).toBeTruthy();
    const { template_id } = await saveRes.json();

    try {
      // 2. 브라우저에서 Compare 탭 접근
      await page.goto('/');
      await page.locator('button[data-tab="tab-compare"]').click();
      await page.waitForSelector(`#tpl-node-${template_id}`);

      // 3. 타겟 설정 (100% 충족 + 비인가 관리자 계정 + 위험 SNMP + 미인가 OSPF 99) 업로드
      const targetCfg = `!
hostname Core-Playwright-01
version 17.3
ntp server 10.0.0.1
username admin privilege 15 secret adminpass
username backdoor_root privilege 15 secret dangerous
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
`;
      await page.locator(`#file-input-${template_id}`).setInputFiles({
        name: 'Target-Device-Extra.cfg',
        mimeType: 'text/plain',
        buffer: Buffer.from(targetCfg),
      });

      // 4. 결과 행 노출 및 100% 점수 확인
      await page.waitForSelector('.compare-view-btn');
      await expect(page.locator('td.col-score').first()).toContainText('100%');

      // 5. 상세 보기 클릭 -> 드로어 열기
      await page.locator('.compare-view-btn').first().click();
      const drawer = page.locator('#compare-drawer');
      await expect(drawer).toHaveClass(/open/);

      // 6. 메타 안내 확인 (미인가/추가 설정 감지 문구)
      await expect(page.locator('#drawer-score')).toHaveText('100%');
      await expect(page.locator('#drawer-meta')).toContainText('미인가/추가 설정');

      // 7. 3개 탭 확인
      const goldenTab = page.locator('button.result-tab-btn[data-tab="golden"]');
      const extraTab = page.locator('button.result-tab-btn[data-tab="extra"]');
      const rollbackTab = page.locator('button.result-tab-btn[data-tab="rollback"]');
      await expect(goldenTab).toBeVisible();
      await expect(extraTab).toBeVisible();
      await expect(rollbackTab).toBeVisible();

      // 8. 추가된 설정 Diff 탭 클릭
      await extraTab.click();
      await expect(page.locator('#tab-content-extra')).toBeVisible();
      await expect(page.locator('.extra-item-card.danger').first()).toBeVisible();
      await expect(page.locator('.extra-diff-line').first()).toContainText('+');
      await expect(page.locator('.extra-rollback-cmd').first()).toContainText('no ');

      // 9. 롤백 CLI 스크립트 탭 클릭
      await rollbackTab.click();
      await expect(page.locator('#tab-content-rollback')).toBeVisible();
      const pre = page.locator('#rollback-script-content');
      await expect(pre).toContainText('configure terminal');
      await expect(pre).toContainText('no username backdoor_root');
      await expect(pre).toContainText('no snmp-server community public');
      await expect(pre).toContainText('no router ospf 99');
      await expect(pre).toContainText('write memory');

      // 10. Clean Config 다운로드 버튼 확인 및 드로어 닫기
      await expect(page.locator('button:has-text("Clean Config 다운로드")')).toBeVisible();
      await page.locator('.drawer-close-btn').click();
      await expect(drawer).not.toHaveClass(/open/);

    } finally {
      // 정리
      await request.delete(`/api/golden/templates/${template_id}`);
    }
  });

});
