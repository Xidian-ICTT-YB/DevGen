#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import subprocess
import signal
import shutil
import time
from threading import Timer, Thread
from copy import deepcopy

# =========================
# config path
# =========================
FUZZ_PATH = "config/gpt-5.1-reproduce.json"
ENABLE_SYSCALL_PATH = "config/enable_syscalls.json"

DIR_A = "syzkaller_syzbot_nodev"
DIR_B = "syzkaller_syzbot_dev"
DIR_C = "syzkaller_defconfig_nodev"
DIR_D = "syzkaller_defconfig_dev"

SYZBOT_OUT_DIR = "fuzz_result/gpt5-1_reproduce_syz"
NON_SYZBOT_OUT_DIR = "fuzz_result/gpt5-1_reproduce_def"

TIMEOUT = 60 * 60          
DEVICE_SLEEP = 10        

def kill_process_group(proc):
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        print(f"[+] Killed process group {proc.pid}")
    except Exception as e:
        print(f"[!] Kill failed: {e}")


def run_syz(cfg_name, workdir, bench_path):
    old_cwd = os.getcwd()
    os.chdir(workdir)

    cmd = f"./bin/syz-manager -config={cfg_name} -bench={bench_path}"
    print(f"[CMD] ({workdir}) {cmd}")

    proc = subprocess.Popen(
        cmd,
        shell=True,
        preexec_fn=os.setsid,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    timer = Timer(TIMEOUT, kill_process_group, [proc])
    timer.start()

    try:
        out, err = proc.communicate()
        if out:
            print(out.decode(errors="ignore"))
        if err:
            print(err.decode(errors="ignore"))
    finally:
        timer.cancel()
        os.chdir(old_cwd)


def run_syz_task(cfg_name, workdir, bench_path):
    try:
        run_syz(cfg_name, workdir, bench_path)
    except Exception as e:
        print(f"[!] syz-manager failed ({cfg_name}): {e}")


def collect_enable_syscalls_sequential(device_path, enable_syscall_db):
    """
Strict sequential search:
- Traverse to the end of the file in the original order specified in enable_syscalls.json
- Append syscalls whenever any driver is hit
- Do not prematurely terminate
- Maintain the original order
    """
    result = []
    seen = set()

    for entry in enable_syscall_db.values():
        drivers = entry.get("drivers", [])
        syscalls = entry.get("syscalls", [])

        for drv in drivers:
            if drv and drv in device_path:
                for sc in syscalls:
                    if sc not in seen:
                        result.append(sc)
                        seen.add(sc)
                break

    return result


with open(FUZZ_PATH, "r") as f:
    fuzz_cfg = json.load(f)

with open(ENABLE_SYSCALL_PATH, "r") as f:
    enable_syscall_db = json.load(f)

os.makedirs(SYZBOT_OUT_DIR, exist_ok=True)
os.makedirs(NON_SYZBOT_OUT_DIR, exist_ok=True)

for device, info in fuzz_cfg.items():
    print("\n========================================")
    print(f"[DEVICE] {device}")
    print("========================================")

    if info.get("enable_syscalls"):
        print(f"[SKIP] {device}: enable_syscalls already populated")
        continue

    flag = info.get("in_syzbot_config", "").lower()
    device_path = info.get("path", "")

    enable_syscalls = collect_enable_syscalls_sequential(
        device_path,
        enable_syscall_db
    )

    info["enable_syscalls"] = enable_syscalls

    if flag == "y":
        targets = [
            (DIR_A, False, SYZBOT_OUT_DIR),
            (DIR_B, True,  SYZBOT_OUT_DIR),
        ]
    elif flag == "n":
        targets = [
            (DIR_C, False, NON_SYZBOT_OUT_DIR),
            (DIR_D, True,  NON_SYZBOT_OUT_DIR),
        ]
    else:
        print(f"[!] Skip {device}: invalid in_syzbot_config")
        continue

    threads = []

    for workdir, add_device, bench_root in targets:
        base_cfg_path = os.path.join(workdir, "cfg.json")
        if not os.path.exists(base_cfg_path):
            print(f"[!] cfg.json not found in {workdir}, skip")
            continue

        with open(base_cfg_path, "r") as f:
            cfg = deepcopy(json.load(f))

        cfg["enable_syscalls"] = enable_syscalls

        if add_device:
            cfg["vm"]["qemu_args"] += f" -device {device}_pci"

        cfg_name = f"cfg_{device}.json"
        cfg_path = os.path.join(workdir, cfg_name)

        with open(cfg_path, "w") as f:
            json.dump(cfg, f, indent=4)

        bench_name = f"{device}.bench" if add_device else f"{device}_no.bench"
        bench_path = os.path.join(bench_root, bench_name)

        t = Thread(
            target=run_syz_task,
            args=(cfg_name, workdir, bench_path),
            daemon=True
        )
        t.start()
        threads.append((t, cfg_path, bench_root))

    for t, cfg_path, bench_root in threads:
        t.join()
        shutil.move(cfg_path, os.path.join(bench_root, os.path.basename(cfg_path)))
        print(f"[+] cfg archived: {bench_root}/{os.path.basename(cfg_path)}")

    print(f"[INFO] device {device} done, sleeping {DEVICE_SLEEP}s")
    time.sleep(DEVICE_SLEEP)

# =========================
# write back fuzz.json
# =========================
with open(FUZZ_PATH, "w") as f:
    json.dump(fuzz_cfg, f, indent=4)

print("[+] fuzz.json updated")

