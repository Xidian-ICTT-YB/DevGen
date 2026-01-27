import re
from vdm.services.config_loader import ConfigLoader
def fill_qemu_run_template(driver_name):
    config_loader = ConfigLoader()
    config = config_loader.load()

    with open(config['paths']['qemu_rum_template_path'], 'r') as f:
        qemu_run_template = f.read()

    replacements = {
        'qemu-system-x86_64_path': config['paths']['qemu-system-x86_64_path'],
        'qemu_kernel_bzImage_path': config['paths']['qemu_kernel_bzImage_path'],
        'qemu_image_path': config['paths']['qemu_image_path'],
        'DRIVER_NAME': driver_name,
        'qemu_out_share_path': config['paths']['qemu_out_share_path'],
        'qemu_log_path': config['paths']['qemu_log_path']
    }
    
    def replace_match(match):
        key = match.group(1)
        return replacements.get(key, match.group(0))

    qemu_run = re.sub(r'\{([^}]+)\}', replace_match, qemu_run_template)

    with open(f"{config['paths']['qemu_run_dir']}/run.sh", "w") as f:
        f.write(qemu_run)