import json
import asyncio
from vdm.utils.logger import setup_logger
from vdm.utils.save_logs import default_logger
from vdm.core.llm_client import client
from vdm.core.prompt_manager import prompt_manager
from vdm.core.context import get_app_start_time, get_driver_name
from vdm.core.driver_info import driver_info
from vdm.services.config_loader import ConfigLoader
from vdm.utils.file_op import write_to_file
from vdm.services.clangd_checker import check_c_syntax

logger = setup_logger('STEP 3')

config_loader = ConfigLoader()
config = config_loader.load()

def get_syntax_error_messages():
    """
    检查生成的PCI驱动文件的C语法错误和警告，并返回格式化的错误信息。
    
    该函数会：
    1. 构造生成的PCI驱动文件路径
    2. 使用C语法检查工具检查该文件
    3. 收集并格式化所有语法错误和警告信息
    
    Returns:
        str: 包含语法错误、警告或无错误信息的格式化字符串
    """
    generated_file = f"{config['paths']['qemu_hw_fack_pci_path']}/{get_driver_name()}_pci.c"
    
    result = check_c_syntax(
        source_file=generated_file,
        build_dir=config['paths']['qemu_build_static_path'],
    )

    flag = 0
    res = ""
    if result.has_errors():
        flag += 1
        res += "**Syntax errors found:**\n"
        for error in result.errors:
            res += f"\n===========================================================\nLine {error.range.start.line + 1}: {error.message}\n snippet:{error.snippet}\n"
    
    # 检查并收集语法警告信息
    if result.has_warnings():
        flag += 1
        res += "**Syntax warnings found:**\n"
        for warning in result.warnings:
            res += f"\n===========================================================\nLine {warning.range.start.line + 1}: {warning.message}\nsnippet:\n{warning.snippet}\n"

    # 如果没有发现任何错误或警告，返回成功信息
    if flag == 0:
        res += "No syntax errors or warnings found."

    return res

def step3_run(device_code: str, logs_path: str = None) -> str:
    """
    执行第三步处理流程，根据部分驱动代码（包含函数定义、struct-init定义等），生成补充好函数实现的qemu设备代码，返回设备代码
    """
    logger.info('============================= STEP 3 RUN =============================')
    device_code, needed_sources = step3(device_code, logs_path)   

    # 如若返回的needed_sources不为空，则进行step3的迭代补全
    device_code = step3_iterations(device_code, needed_sources, logs_path)
    
    logger.info('============================= STEP 3 RUN END =============================')

    # 保存device_code
    if logs_path == None:
        save_device_code_path = f"{get_app_start_time()}_{get_driver_name()}/step3/device_code.txt"
        default_logger.save_content(device_code, save_device_code_path)
    else:
        save_device_code_path = f"{logs_path}/syntax_check/device_code.txt"
        default_logger.save_content(device_code, save_device_code_path)

    return device_code

def step3(device_code: str, logs_path: str = None) -> tuple[str, list]:
    """
    执行第三步处理流程
    """
    logger.info('============================= STEP 3 main =============================')

    
    # 将生成的QEMU设备代码结果拷贝（或者覆盖）到hw/fake_pci下
    write_to_file(f"{config['paths']['qemu_hw_fack_pci_path']}/{get_driver_name()}_pci.c", device_code)
    logger.info(f"代码，成功保存至{config['paths']['qemu_hw_fack_pci_path']}/{get_driver_name()}_pci.c")

    logger.info("开始检查代码语法错误")
    syntax_error_message = get_syntax_error_messages()
    logger.info(f"语法错误检查结束：{syntax_error_message}")

    if syntax_error_message == "No syntax errors or warnings found.":
        logger.info("无语法错误，不进行step3")
        return device_code, []

    # 获取step3的prompt
    step3_prompt = prompt_manager.get_prompt("step3", 
                                             DRIVER_PATH=driver_info.get_driver_path_by_driver_name(), 
                                             QEMU_CODE=device_code,
                                             SYNTAX_ERROR_MESSAGE=syntax_error_message,
                                             Relevant_Source=""
                                            )

    # 构造历史记录
    step3_history_messages = [
        {"role": "system", "content": prompt_manager.get_prompt("system")},
        {"role": "user", "content": prompt_manager.get_prompt("step0")},
        {"role": "assistant", "content": "OK"},
        {"role": "user", "content": prompt_manager.get_prompt("two_examples")},
        {"role": "assistant", "content": "OK"},
    ]

    # 构造step3的message
    step3_messages = step3_history_messages + [
        {"role": "user", "content": step3_prompt}
    ]

    # 保存step3的message
    if logs_path == None:
        save_step3_messages_path = f"{get_app_start_time()}_{get_driver_name()}/step3/messages"
        default_logger.save_messages(step3_messages, save_step3_messages_path)
    else:
        save_step3_messages_path = f"{logs_path}/syntax_check/messages"
        default_logger.save_messages(step3_messages, save_step3_messages_path)

    # 调用LLM
    response, finish_reason = client.chat_completion_json(step3_messages)

    # 处理输出超限的情况，多次回复
    continue_cnt = 1
    while finish_reason == "length" or finish_reason == "None":
        if continue_cnt >= 5:
            break
        # 构造继续获取完整输出的message
        step3_continue_messages = step3_messages + [
            {"role": "assistant", "content": response}, 
            {"role": "user", "content": prompt_manager.get_prompt("full_output")},
        ]

        # 保存step3_continue的message
        if logs_path == None:
            save_step3_continue_messages_path = f"{get_app_start_time()}_{get_driver_name()}/step3/continue/{continue_cnt}/messages"
            default_logger.save_messages(step3_continue_messages, save_step3_continue_messages_path)
        else:
            save_step3_continue_messages_path = f"{logs_path}/syntax_check/continue/{continue_cnt}/messages"
            default_logger.save_messages(step3_continue_messages, save_step3_continue_messages_path)

        # 调用LLM
        response_continue, finish_reason = client.chat_completion_json(step3_continue_messages)

        # 保存回复内容
        if logs_path == None:
            save_step3_continue_response_path = f"{get_app_start_time()}_{get_driver_name()}/step3/continue/{continue_cnt}/response.txt"
            default_logger.save_content(response_continue, save_step3_continue_response_path)
        else:
            save_step3_continue_response_path = f"{logs_path}/syntax_check/continue/{continue_cnt}/response.txt"
            default_logger.save_content(response_continue, save_step3_continue_response_path)

        # 处理输出超限的情况，多次回复，拼接多次回复
        response += response_continue

        continue_cnt += 1

    # 保存step3的回复内容
    if logs_path == None:
        save_step3_response_path = f"{get_app_start_time()}_{get_driver_name()}/step3/response.txt"
        default_logger.save_content(response, save_step3_response_path)
        save_step3_response_path = f"{get_app_start_time()}_{get_driver_name()}/step3/response_visual.txt"
        default_logger.save_response(json.loads(response), save_step3_response_path)
    else:
        save_step3_response_path = f"{logs_path}/syntax_check/response.txt"
        default_logger.save_content(response, save_step3_response_path)
        save_step3_response_path = f"{logs_path}/syntax_check/response_visual.txt"
        default_logger.save_response(json.loads(response), save_step3_response_path)

    # 处理LLM返回的json
    response_json = json.loads(response)
    device_code = response_json["code"]
    needed_sources = response_json["needed_sources"]

    logger.info('============================= STEP 3 main END =============================')

    return device_code, needed_sources

def step3_iterations(device_code: str, needed_sources: list, logs_path: str = None) -> str:
    """
    进行step3的多次迭代补全，直到needed_sources为空或者达到最大迭代次数
    """
    iteration = 0
    # 最大迭代次数
    max_iterations = 3

    while iteration < max_iterations: 
        logger.info(f'============================= STEP 3 iteration {iteration} =============================')

        is_searched, device_code, needed_sources = step3_iteration(iteration, device_code, needed_sources, logs_path)

        # 如若无法继续搜索则退出迭代，无法找到needed_sources对应的资源
        if not is_searched:
            break

        iteration += 1

        logger.info(f'============================= STEP 3 iteration {iteration} END =============================')

    return device_code
        

def step3_iteration(cnt: int, device_code: str, needed_sources: list, logs_path: str = None) -> tuple[bool, str, list]:
    """
    进行step3的一次迭代补全，返回补全后的设备代码和所需资源列表，如果无法补全则返回原始设备代码和所需资源列表，同时返回标志位（True表示可以完成搜索,False为反）
    """
    # 处理needed_sources
    relevant_source = handle_needed_resources(needed_sources)
    
    # 将生成的QEMU设备代码结果拷贝（或者覆盖）到hw/fake_pci下
    write_to_file(f"{config['paths']['qemu_hw_fack_pci_path']}/{get_driver_name()}_pci.c", device_code)
    logger.info(f"代码，成功保存至{config['paths']['qemu_hw_fack_pci_path']}/{get_driver_name()}_pci.c")

    logger.info("开始检查代码语法错误")
    syntax_error_message = get_syntax_error_messages()
    logger.info(f"语法错误检查结束：{syntax_error_message}")

    if syntax_error_message == "No syntax errors or warnings found." and relevant_source == "None":
        if syntax_error_message == "No syntax errors or warnings found.":
            logger.info("无语法错误或warnning，不进行step3的迭代")
        
        if needed_sources == []:
            logger.info("无所需资源，不进行step3的迭代")

        return False, device_code, []

    # 获取step3-iteration的prompt
    step3_iteration_prompt = prompt_manager.get_prompt("step3_iteration", 
                                                       DRIVER_PATH=driver_info.get_driver_path_by_driver_name(), 
                                                       Relevant_Source=relevant_source, 
                                                       QEMU_CODE=device_code,
                                                       SYNTAX_ERROR_MESSAGE=syntax_error_message
                                                      )

    # 构造step3-iteration的历史记录
    step3_iteration_history_messages = [
        {"role": "system", "content": prompt_manager.get_prompt("system")},
        {"role": "user", "content": prompt_manager.get_prompt("step0")},
        {"role": "assistant", "content": "OK"},
        {"role": "user", "content": prompt_manager.get_prompt("two_examples")},
        {"role": "assistant", "content": "OK"},
    ]

    # 构造step3-iteration的message
    step3_iteration_messages = step3_iteration_history_messages + [
        {"role": "user", "content": step3_iteration_prompt}
    ]

    # 保存step3-iteration的message
    if logs_path == None:
        save_step3_iteration_messages_path = f"{get_app_start_time()}_{get_driver_name()}/step3/iteration/{cnt}/messages"
        default_logger.save_messages(step3_iteration_messages, save_step3_iteration_messages_path)
    else:
        save_step3_iteration_messages_path = f"{logs_path}/syntax_check/iteration/{cnt}/messages"
        default_logger.save_messages(step3_iteration_messages, save_step3_iteration_messages_path)

    # 调用LLM
    response, finish_reason = client.chat_completion_json(step3_iteration_messages)

    # 处理输出超限的情况，多次回复
    continue_cnt = 1
    while finish_reason == "length" or finish_reason == "None":
        if continue_cnt >= 5:
            break
        # 构造继续获取完整输出的message
        step3_iteration_continue_messages = step3_iteration_messages + [
            {"role": "assistant", "content": response}, 
            {"role": "user", "content": prompt_manager.get_prompt("full_output")},
        ]

        # 保存step3-iteration_continue的message
        if logs_path == None:
            save_step3_iteration_continue_messages_path = f"{get_app_start_time()}_{get_driver_name()}/step3/iteration/{cnt}/continue/{continue_cnt}/messages"
            default_logger.save_messages(step3_iteration_continue_messages, save_step3_iteration_continue_messages_path)
        else:
            save_step3_iteration_continue_messages_path = f"{logs_path}/syntax_check/iteration/{cnt}/continue/{continue_cnt}/messages"
            default_logger.save_messages(step3_iteration_continue_messages, save_step3_iteration_continue_messages_path)

        # 调用LLM
        response_continue, finish_reason = client.chat_completion_json(step3_iteration_continue_messages)

        # 保存回复内容
        if logs_path == None:
            save_step3_iteration_continue_response_path = f"{get_app_start_time()}_{get_driver_name()}/step3/iteration/{cnt}/continue/{continue_cnt}/response.txt"
            default_logger.save_content(response_continue, save_step3_iteration_continue_response_path)
        else:
            save_step3_iteration_continue_response_path = f"{logs_path}/syntax_check/iteration/{cnt}/continue/{continue_cnt}/response.txt"
            default_logger.save_content(response_continue, save_step3_iteration_continue_response_path)

        # 处理输出超限的情况，多次回复，拼接多次回复
        response += response_continue

        continue_cnt += 1
    
    # 保存step3-iteration的回复内容
    if logs_path == None:
        save_step3_iteration_response_path = f"{get_app_start_time()}_{get_driver_name()}/step3/iteration/{cnt}/response.txt"
        default_logger.save_response(json.loads(response), save_step3_iteration_response_path)
    else:
        save_step3_iteration_response_path = f"{logs_path}/syntax_check/iteration/{cnt}/response.txt"
        default_logger.save_response(json.loads(response), save_step3_iteration_response_path)

    # 处理LLM返回的json
    response_json = json.loads(response)
    device_code = response_json["code"]
    needed_sources = response_json["needed_sources"]

    return True, device_code, needed_sources

def handle_needed_resources(needed_sources: list) -> str:
    """
    处理所需资源
    """
    # 通过调用driver_info模块中的get_symbol_by_name方法获取所需资源,返回所需资源的详细内容,如果没有所需资源，则返回空字符串
    res = "None"
    cnt = 0
    suc_cnt = 0
    for source in needed_sources:
        cnt += 1
        
        if source.count(":") > 1:
            continue
        
        if ":" in source:
            type, name = source.split(":")
        else:
            name = source
            type = "all"

        logger.info(f'Try getting {name} from {type}')
        tmp = driver_info.get_symbol_by_name(name, type)
        if tmp is None:
            if type != "all":
                tmp = driver_info.get_symbol_by_name(name, "all")
            if tmp is None:
                logger.info(f'Get {name} from {type} failed')
            else:
                logger.info(f'Get {name} from all successfully')
                if res == "None":
                    res = ""
                res += tmp + '\n'
                suc_cnt += 1
        else:
            if res == "None":
                res = ""
            logger.info(f'Get {name} from {type} successfully')
            res += tmp + '\n'
            suc_cnt += 1

    logger.info(f'Get needed_source successfully. Total: {cnt}, Success: {suc_cnt}')

    return res