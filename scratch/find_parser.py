from pyats.topology import Device
from genie.libs.parser.utils import get_parser_commands

device = Device('r1', os='iosxe', platform='cat9k', type='router')

commands = get_parser_commands(device)
for cmd in commands:
    if 'show' in cmd and 'run' in cmd:
        print(f"Command: {cmd}")
