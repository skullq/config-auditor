
import sys
import os

# Add webapp to path to import detect_os and parsers
sys.path.append(os.path.join(os.getcwd(), 'webapp'))

from core.parser import _load_parsers_for_os

def test_genie_iosxe():
    config = """
version 17.3
hostname TestDevice
!
interface GigabitEthernet1
 description LAN
 ip address 10.1.1.1 255.255.255.0
!
spanning-tree extend system-id
spanning-tree pathcost method short
spanning-tree vlan 1-4094 priority 0
!
line console 0
 logging synchronous
line vty 0 4
 logging synchronous
!
end
"""
    os_type = 'iosxe'
    os_parsers = _load_parsers_for_os(os_type)
    
    if 'all' not in os_parsers:
        print("Error: 'all' parser (ShowRunningConfig) not loaded.")
        return

    ParserClass = os_parsers['all']
    try:
        parser_inst = ParserClass(device=None)
        parsed = parser_inst.parse(output=config.strip())
        print("Parsed Keys:", parsed.keys())
        if 'line' in parsed:
            print("Line Data:", parsed['line'])
        if 'spanning-tree' in parsed:
            print("Spanning-Tree Data:", parsed['spanning-tree'])
        if 'logging' in parsed:
            print("Logging Data:", parsed['logging'])
    except Exception as e:
        print(f"Genie Parsing Failed: {e}")

if __name__ == "__main__":
    test_genie_iosxe()
