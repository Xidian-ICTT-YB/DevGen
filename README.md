# Bridging Kernel Drivers and Virtual Device Models with LLM-Powered Automation

## Driver Information Collection

In the first phase of **DevGen**, the core source code of the target kernel will be extracted, and the main execution will be carried out in the `static_analyze` directory.

## LLM-Guided Device Modeling

The core stage of **DevGen** mainly involves using LLM to guide the generation of virtual device code. The specific details can be found in the `DevGen_Core` directory.

## Integration and Fuzzing

1. Simplify the static analysis part of the code and generate a JSON file,run `python3 generate_json.py`
2. Process the target driver code based on the generated JSON file.`python3 simple_code.py`
3. Modify the relevant path names and perform the fuzzing.`start_fuzz.py`

## Config and Result

1. We have placed all the configurations that **DevGen** needs during its execution in the `config` directory.
2. The `result` directory contains the results of different model simulations as well as coverage and crash information.

## Bug status
| Crash                                      | Device  | LLM-Qwen  | LLM-GPT-5.1   |   LLM-Gemini   | Status |
|--------------------------------------------|--------------|-------------|----------|----------|---------------|            
| `WARNING in drm_gem_release`                 | `bochs-drm`    | ✓           | ✓        | ☓        | CVE-2026-23149|
| `WARNING in idr_alloc`                       | `intel-qep`    | ☓           | ✓        | ✓        | CVE-2026-23149|
| `KASAN: UAF read in adf_dev_up`              | `c6xxvf`       | ✓           | ☓        | ☓        | Confirmed     |
| `general protection fault in h5_recv`        | `8250_lpss`    | ✓           | ☓        | ✓        | Confirmed     |
| `INFO: rcu detected stall in sys_mmap`       | `pci-tng`      | ✓           | ☓        | ☓        | New           |
| `INFO: rcu detected stall in do_idle`        | `wdt_pci`      | ☓           | ☓        | ✓        | New           |
| `INFO: task hung in i2c_smbus_xfer`          | `bttv`         | ✓           | ✓        | ✓        | New           |