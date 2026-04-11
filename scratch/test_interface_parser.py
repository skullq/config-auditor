from genie.libs.parser.iosxe.show_run import ShowRunInterface
import pprint

with open("r1.cfg", "r") as f:
    config_output = f.read()

parser = ShowRunInterface(device=None)
try:
    structured_config = parser.parse(output=config_output)
    pprint.pprint(structured_config)
except Exception as e:
    print(f"Error: {e}")
