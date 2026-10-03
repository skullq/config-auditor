"""
test_parse.py - cisco-config-parser 3.0.0 1차 파싱 및 항목별 분류 검증 CLI 도구

사용법:
  python test_parse.py [설정파일경로]
"""

import sys
import os
import json

# Windows 콘솔 UTF-8 출력 보장
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# webapp 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'webapp'))
from core.parser import parse_config, extract_all_blocks, detect_platform, flatten_for_ui

SAMPLE_CONFIG = """!
version 17.3
hostname Core-SW01
ip domain name corp.local
ip name-server 8.8.8.8 8.8.4.4
ntp server 10.0.0.1
logging host 10.0.0.2
username admin privilege 15 secret 9 adminpass
!
vrf definition CORP_VRF
 rd 65000:100
!
vlan 10
 name USERS
vlan 20
 name SERVERS
!
interface GigabitEthernet1/0/1
 description ## ACCESS PORT ##
 switchport mode access
 switchport access vlan 10
 spanning-tree portfast
!
interface TenGigabitEthernet1/0/24
 description ## UPLINK TO CORE ##
 switchport mode trunk
 switchport trunk allowed vlan 10,20,30
!
interface Vlan10
 description ## GATEWAY USERS ##
 ip address 10.10.10.1 255.255.255.0
 no shutdown
!
interface Loopback0
 ip address 1.1.1.1 255.255.255.255
!
ip route 0.0.0.0 0.0.0.0 10.10.10.254
!
router ospf 1
 router-id 1.1.1.1
 network 10.10.10.0 0.0.0.255 area 0
!
router bgp 65000
 bgp router-id 1.1.1.1
 neighbor 10.10.10.254 remote-as 65001
 neighbor 10.10.10.254 description PEER-ROUTER
!
ip access-list extended MGMT_ACL
 permit tcp 10.0.0.0 0.255.255.255 any eq 22
 deny ip any any log
!
ip prefix-list DEFAULT_ONLY seq 5 permit 0.0.0.0/0
!
route-map SET_METRIC permit 10
 match ip address prefix-list DEFAULT_ONLY
 set metric 50
!
banner motd ^C
=============================================
 UNAUTHORIZED ACCESS PROHIBITED
=============================================
^C
!
line con 0
 exec-timeout 5 0
 logging synchronous
line vty 0 4
 transport input ssh
 exec-timeout 10 0
 logging synchronous
!
spanning-tree mode rapid-pvst
spanning-tree extend system-id
!
end
"""

def parse_and_display(cfg_text: str, filename: str = "기본 샘플"):
    # 1. 플랫폼 및 파싱 실행
    platform = detect_platform(cfg_text)
    parsed = parse_config(cfg_text)
    blocks = parsed.get("blocks", [])
    items = flatten_for_ui(parsed)
    noise = parsed.get("noise_info", {})

    print("=" * 80)
    print(f"🚀 [cisco-config-parser 3.0.0] 파싱 결과: {filename}")
    print(f"   - Hostname : {parsed.get('hostname')}")
    print(f"   - Platform : {platform} (OS: {parsed.get('os')})")
    print(f"   - 총 블록 수: {len(blocks)} 개 블록")
    print(f"   - 총 항목 수: {len(items)} 개 항목")
    if noise.get("has_noise"):
        print(f"   ⚠️ 비설정 노이즈 감지 및 정제:")
        print(f"      - 전체 {noise['total_lines']}줄 중 순수 설정 {noise['config_lines']}줄 추출 (제거: 상단 {noise['pre_noise_count']}줄, 하단 {noise['post_noise_count']}줄)")
        if noise.get('pre_noise_sample'):
            print(f"      - 상단 감지: {noise['pre_noise_sample']}")
        if noise.get('post_noise_sample'):
            print(f"      - 하단 감지(Show 명령어/라우팅 테이블/카운터): {noise['post_noise_sample']}")
    print("=" * 80)

    print(f"{'순서':<5} | {'블록명':<35} | {'블록 ID':<25} | {'항목수':<6}")
    print("-" * 80)

    for b in blocks:
        order = b["order"]
        name = b["name"]
        bid = b["block_id"]
        cnt = b["item_count"]
        print(f"{order:<5} | {name:<35} | {bid:<25} | {cnt:<6} 개")

    print("\n" + "=" * 80)
    print("🌲 [블록별 계층 트리(Tree View) 및 세부 설정 구조]")
    print("=" * 80)

    for b in blocks:
        tree_nodes = b.get("tree_nodes", [])
        if not tree_nodes:
            continue
        print(f"\n[{b['order']}] {b['name']} ({b['block_id']}) - {len(tree_nodes)}개 노드, {b['item_count']}개 세부 항목:")
        has_child_tree = any(n.get("children") for n in tree_nodes)
        if has_child_tree:
            for n in tree_nodes[:10]:
                ch_list = n.get("children", [])
                if ch_list:
                    print(f"    📂 {n['line']}")
                    for idx, c in enumerate(ch_list):
                        is_last = (idx == len(ch_list) - 1)
                        branch = "└──" if is_last else "├──"
                        print(f"       {branch} {c['line']}")
                else:
                    print(f"    📄 {n['line']}")
            if len(tree_nodes) > 10:
                print(f"       ... (외 {len(tree_nodes) - 10}개 노드)")
        else:
            for n in tree_nodes[:5]:
                print(f"    📄 {n['line']}")
            if len(tree_nodes) > 5:
                print(f"       ... (외 {len(tree_nodes) - 5}개 항목)")

    print("\n" + "=" * 80)
    print(f"✅ [{filename}] 파싱 및 트리 분류가 성공적으로 검증되었습니다.")
    print("=" * 80)


def main():
    if len(sys.argv) > 1 and sys.argv[1].lower() in ('all', 'samples', '--all', '-a'):
        samples_dir = os.path.join(os.path.dirname(__file__), 'samples')
        if not os.path.exists(samples_dir):
            print("❌ samples 디렉토리가 존재하지 않습니다.")
            return
        sample_files = [f for f in os.listdir(samples_dir) if os.path.isfile(os.path.join(samples_dir, f))]
        print(f"📁 samples 디렉토리 내 {len(sample_files)}개 파일 일괄 검증을 시작합니다:\n")
        for sf in sorted(sample_files):
            spath = os.path.join(samples_dir, sf)
            with open(spath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            parsed = parse_config(content)
            blocks = parsed.get("blocks", [])
            items = flatten_for_ui(parsed)
            noise = parsed.get("noise_info", {})
            l2_block = next((b for b in blocks if b["block_id"] == "interfaces_l2"), None)
            l3_block = next((b for b in blocks if b["block_id"] == "interfaces_l3"), None)
            l2_count = len(l2_block["tree_nodes"]) if l2_block else 0
            l3_count = len(l3_block["tree_nodes"]) if l3_block else 0
            tag = "⚠️ 정제됨" if noise.get("has_noise") else "✅ 순수"
            noise_str = f"-{noise.get('pre_noise_count', 0) + noise.get('post_noise_count', 0)}줄" if noise.get("has_noise") else "0줄"
            print(f"[{tag}] {sf:<26} | Host: {str(parsed.get('hostname')):<15} | 블록: {len(blocks):<3}개 | 항목: {len(items):<4}개 | 인터페이스: L2 {l2_count:<2}개, L3 {l3_count:<2}개 (노이즈: {noise_str})")
        print("\n" + "=" * 80)
        print("🎉 samples 디렉토리 내 모든 샘플 파일 검증이 성공적으로 완료되었습니다!")
        print("=" * 80)
        return

    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        filepath = sys.argv[1]
        print(f"📄 파일 로드: {filepath}")
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            cfg_text = f.read()
        parse_and_display(cfg_text, filename=os.path.basename(filepath))
    else:
        print("💡 기본 샘플 Cisco 설정을 사용하여 1차 파싱 검증을 수행합니다.")
        print("   (특정 파일 검증: python test_parse.py [파일명])")
        print("   (samples 폴더 전체 검증: python test_parse.py samples)\n")
        parse_and_display(SAMPLE_CONFIG, filename="기본 샘플")

if __name__ == "__main__":
    main()
