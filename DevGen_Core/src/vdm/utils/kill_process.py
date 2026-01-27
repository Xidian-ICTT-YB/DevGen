import subprocess
import shlex # 用于安全地分割命令字符串

def kill_qemu_with_subprocess():
    """
    使用 subprocess 模拟 'ps aux | grep qemu' 并杀死进程。
    """
    print("--- 任务准备阶段 (使用subprocess) ---")
    
    # 1. 执行 'ps aux' 命令
    try:
        # 使用 shell=False 是更安全的做法，但需要手动分割命令
        # ps_command = ['ps', 'aux']
        # ps_output = subprocess.check_output(ps_command, text=True)
        
        # 为了模拟管道，我们可以用 shell=True，但要确保输入可信
        ps_command = "ps aux | grep '[q]emu'"
        # grep '[q]emu' 是一个防止grep进程自身被匹配到的小技巧
        ps_output = subprocess.check_output(ps_command, shell=True, text=True)
        
    except subprocess.CalledProcessError:
        # 如果 grep 没找到任何东西，它会返回非零退出码，导致异常
        print("未发现正在运行的 QEMU 进程。")
        print("--- QEMU 环境清理完毕，开始执行核心任务 ---")
        return 

    # 2. 解析输出并提取PID
    pids_to_kill = []
    for line in ps_output.strip().split('\n'):
        if line:
            # ps aux 的输出，PID是第二列
            parts = line.split()
            pid = parts[1]
            pids_to_kill.append(pid)
            print(f"发现 QEMU 进程: PID={pid}")

    # 3. 杀死找到的PID
    if pids_to_kill:
        for pid in pids_to_kill:
            try:
                kill_command = ['sudo', 'kill', '-9', pid] # -9 表示强制杀死
                subprocess.run(kill_command, check=True)
                print(f"已成功杀死 PID {pid}")
            except subprocess.CalledProcessError as e:
                print(f"杀死 PID {pid} 失败: {e}")
    
    print("--- QEMU 环境清理完毕，开始执行核心任务 ---")


# --- 使用示例 ---
def my_main_task():
    """
    核心业务函数。
    """
    print("正在执行核心任务...")
    print("核心任务完成！")
    return "任务成功"

if __name__ == "__main__":
    print("准备调用 my_main_task()...")
    # 在调用函数前，手动执行清理函数
    kill_qemu_with_subprocess()
    
    # 然后调用你的核心函数
    result = my_main_task()
    print(f"函数返回结果: {result}")
