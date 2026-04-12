from genie.libs.parser.iosxe.show_run import ShowRunInterface
parser = ShowRunInterface(device=None)
config = """
interface TenGigabitEthernet1/0/4
 description ## FC_ANS5_1F_R06-L2A-01_130.22 ##
 switchport trunk allowed vlan 130,158
 switchport mode trunk
 load-interval 30
 udld port aggressive
"""
try:
    res = parser.parse(output=config)
    import json
    print(json.dumps(res, indent=2))
except Exception as e:
    print(e)
