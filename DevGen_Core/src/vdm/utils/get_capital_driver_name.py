import json
from vdm.services.config_loader import ConfigLoader
def get_capital_driver_name(driver_name) -> str:
    config_loader = ConfigLoader()
    config = config_loader.load()

    with open(config["paths"]["driver_name_case_mapping_path"], "r") as f:
        case_mapping = json.load(f)
        return case_mapping[driver_name]


if __name__ == "__main__":
    print(get_capital_driver_name("RDC321x Southbridge"))