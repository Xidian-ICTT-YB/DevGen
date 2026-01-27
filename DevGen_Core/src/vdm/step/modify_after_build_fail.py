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

logger = setup_logger('modify_after_build_fail')

config_loader = ConfigLoader()
config = config_loader.load()

def get_syntax_error_messages():
    """
    检查生成的PCI驱动文件的C语法错误和警告，并返回格式化的错误信息。
    
    该函数会构建一个PCI驱动源文件路径，检查其语法错误和警告，
    并将结果格式化为字符串返回。
    
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
    # 处理语法错误信息
    if result.has_errors():
        flag += 1
        res += "**Syntax errors found:**\n"
        for error in result.errors:
            res += f"===========================================================\nLine {error.range.start.line + 1}: {error.message}\n snippet:{error.snippet}"
    
    # 处理语法警告信息
    if result.has_warnings():
        flag += 1
        res += "**Syntax warnings found:**\n"
        for warning in result.warnings:
            res += f"===========================================================\nLine {warning.range.start.line + 1}: {warning.message}\nsnippet:\n{warning.snippet}"

    # 当没有错误和警告时的处理
    if flag == 0:
        res += "No syntax errors or warnings found."

    return res

def modify_after_build_fail_run(device_code: str, fail_logs: str = None) -> str:
    """
    执行第三步处理流程，根据部分驱动代码（包含函数定义、struct-init定义等），生成补充好函数实现的qemu设备代码，返回设备代码
    """
    logger.info('============================= MODIFY_AFTER_BUILD_FAIL RUN =============================')
    device_code, needed_sources = modify_after_build_fail(device_code, fail_logs)   

    # 如若返回的needed_sources不为空，则进行modify_after_build_fail的迭代补全
    device_code = modify_after_build_fail_iterations(device_code, needed_sources, fail_logs)
    
    logger.info('============================= MODIFY_AFTER_BUILD_FAIL RUN END =============================')

    # 保存device_code
    save_device_code_path = f"{get_app_start_time()}_{get_driver_name()}/modify_after_build_fail/device_code.txt"
    default_logger.save_content(device_code, save_device_code_path)


    return device_code

def modify_after_build_fail(device_code: str, fail_logs: str = None) -> tuple[str, list]:
    """
    执行第三步处理流程
    """
    logger.info('============================= MODIFY_AFTER_BUILD_FAIL main =============================')

    
    # 将生成的QEMU设备代码结果拷贝（或者覆盖）到hw/fake_pci下
    write_to_file(f"{config['paths']['qemu_hw_fack_pci_path']}/{get_driver_name()}_pci.c", device_code)
    logger.info(f"代码，成功保存至{config['paths']['qemu_hw_fack_pci_path']}/{get_driver_name()}_pci.c")

    logger.info("开始检查代码语法错误")
    syntax_error_message = get_syntax_error_messages()
    logger.info(f"语法错误检查结束：{syntax_error_message}")

    # 第一次执行modify_after_build_fail时，无论是否存在语法错误，因为有fail_logs，则说明有编译错误，需要修复。

    # 获取modify_after_build_fail的prompt
    modify_after_build_fail_prompt = prompt_manager.get_prompt("modify_after_build_fail", 
                                             DRIVER_PATH=driver_info.get_driver_path_by_driver_name(), 
                                             QEMU_CODE=device_code,
                                             SYNTAX_ERROR_MESSAGE=syntax_error_message,
                                             Relevant_Source="",
                                             FAIL_LOGS=fail_logs
                                            )

    # 构造历史记录
    modify_after_build_fail_history_messages = [
        {"role": "system", "content": prompt_manager.get_prompt("system")},
        {"role": "user", "content": prompt_manager.get_prompt("step0")},
        {"role": "assistant", "content": "OK"},
        {"role": "user", "content": prompt_manager.get_prompt("two_examples")},
        {"role": "assistant", "content": "OK"},
    ]

    # 构造modify_after_build_fail的message
    modify_after_build_fail_messages = modify_after_build_fail_history_messages + [
        {"role": "user", "content": modify_after_build_fail_prompt}
    ]

    # 保存modify_after_build_fail的message
    save_modify_after_build_fail_messages_path = f"{get_app_start_time()}_{get_driver_name()}/modify_after_build_fail/messages"
    default_logger.save_messages(modify_after_build_fail_messages, save_modify_after_build_fail_messages_path)


    # 调用LLM
    response, finish_reason = client.chat_completion_json(modify_after_build_fail_messages)

    # 处理输出超限的情况，多次回复
    continue_cnt = 1
    while finish_reason == "length" or finish_reason == "None":
        if continue_cnt >= 5:
            break
        # 构造继续获取完整输出的message
        modify_after_build_fail_continue_messages = modify_after_build_fail_messages + [
            {"role": "assistant", "content": response}, 
            {"role": "user", "content": prompt_manager.get_prompt("full_output")},
        ]

        # 保存modify_after_build_fail_continue的message
        save_modify_after_build_fail_continue_messages_path = f"{get_app_start_time()}_{get_driver_name()}/modify_after_build_fail/continue/{continue_cnt}/messages"
        default_logger.save_messages(modify_after_build_fail_continue_messages, save_modify_after_build_fail_continue_messages_path)

        # 调用LLM
        response_continue, finish_reason = client.chat_completion_json(modify_after_build_fail_continue_messages)

        # 保存回复内容
        save_modify_after_build_fail_continue_response_path = f"{get_app_start_time()}_{get_driver_name()}/modify_after_build_fail/continue/{continue_cnt}/response.txt"
        default_logger.save_content(response_continue, save_modify_after_build_fail_continue_response_path)

        # 处理输出超限的情况，多次回复，拼接多次回复
        response += response_continue

        continue_cnt += 1

    # 保存modify_after_build_fail的回复内容
    save_modify_after_build_fail_response_path = f"{get_app_start_time()}_{get_driver_name()}/modify_after_build_fail/response.txt"
    default_logger.save_content(response, save_modify_after_build_fail_response_path)
    save_modify_after_build_fail_response_path = f"{get_app_start_time()}_{get_driver_name()}/modify_after_build_fail/response_visual.txt"
    default_logger.save_response(json.loads(response), save_modify_after_build_fail_response_path)

    # 处理LLM返回的json
    response_json = json.loads(response)
    device_code = response_json["code"]
    needed_sources = response_json["needed_sources"]

    logger.info('============================= MODIFY_AFTER_BUILD_FAIL main END =============================')

    return device_code, needed_sources

def modify_after_build_fail_iterations(device_code: str, needed_sources: list, fail_logs: str = None) -> str:
    """
    进行modify_after_build_fail的多次迭代补全，直到needed_sources为空或者达到最大迭代次数
    """
    iteration = 0
    # 最大迭代次数
    max_iterations = 5

    while iteration < max_iterations: 
        logger.info(f'============================= MODIFY_AFTER_BUILD_FAIL iteration {iteration} =============================')

        is_searched, device_code, needed_sources = modify_after_build_fail_iteration(iteration, device_code, needed_sources, fail_logs)

        # 如若无法继续搜索则退出迭代，无法找到needed_sources对应的资源
        if not is_searched:
            break

        iteration += 1

        logger.info(f'============================= MODIFY_AFTER_BUILD_FAIL iteration {iteration} END =============================')

    return device_code
        

def modify_after_build_fail_iteration(cnt: int, device_code: str, needed_sources: list, fail_logs: str = None) -> tuple[bool, str, list]:
    """
    进行modify_after_build_fail的一次迭代补全，返回补全后的设备代码和所需资源列表，如果无法补全则返回原始设备代码和所需资源列表，同时返回标志位（True表示可以完成搜索,False为反）
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
            logger.info("无语法错误或warnning，不进行modify_after_build_fail的迭代")
        
        if needed_sources == []:
            logger.info("无所需资源，不进行modify_after_build_fail的迭代")

        return False, device_code, []

    # 获取modify_after_build_fail-iteration的prompt
    modify_after_build_fail_iteration_prompt = prompt_manager.get_prompt("modify_after_build_fail_iteration", 
                                                       DRIVER_PATH=driver_info.get_driver_path_by_driver_name(), 
                                                       Relevant_Source=relevant_source, 
                                                       QEMU_CODE=device_code,
                                                       SYNTAX_ERROR_MESSAGE=syntax_error_message,
                                                       FAIL_LOGS=fail_logs
                                                      )

    # 构造modify_after_build_fail-iteration的历史记录
    modify_after_build_fail_iteration_history_messages = [
        {"role": "system", "content": prompt_manager.get_prompt("system")},
        {"role": "user", "content": prompt_manager.get_prompt("step0")},
        {"role": "assistant", "content": "OK"},
        {"role": "user", "content": prompt_manager.get_prompt("two_examples")},
        {"role": "assistant", "content": "OK"},
    ]

    # 构造modify_after_build_fail-iteration的message
    modify_after_build_fail_iteration_messages = modify_after_build_fail_iteration_history_messages + [
        {"role": "user", "content": modify_after_build_fail_iteration_prompt}
    ]

    # 保存modify_after_build_fail-iteration的message
    save_modify_after_build_fail_iteration_messages_path = f"{get_app_start_time()}_{get_driver_name()}/modify_after_build_fail/iteration/{cnt}/messages"
    default_logger.save_messages(modify_after_build_fail_iteration_messages, save_modify_after_build_fail_iteration_messages_path)

    # 调用LLM
    response, finish_reason = client.chat_completion_json(modify_after_build_fail_iteration_messages)

    # 处理输出超限的情况，多次回复
    continue_cnt = 1
    while finish_reason == "length" or finish_reason == "None":
        if continue_cnt >= 5:
            break
        # 构造继续获取完整输出的message
        modify_after_build_fail_iteration_continue_messages = modify_after_build_fail_iteration_messages + [
            {"role": "assistant", "content": response}, 
            {"role": "user", "content": prompt_manager.get_prompt("full_output")},
        ]

        # 保存modify_after_build_fail-iteration_continue的message
        save_modify_after_build_fail_iteration_continue_messages_path = f"{get_app_start_time()}_{get_driver_name()}/modify_after_build_fail/iteration/{cnt}/continue/{continue_cnt}/messages"
        default_logger.save_messages(modify_after_build_fail_iteration_continue_messages, save_modify_after_build_fail_iteration_continue_messages_path)

        # 调用LLM
        response_continue, finish_reason = client.chat_completion_json(modify_after_build_fail_iteration_continue_messages)

        # 保存回复内容
        save_modify_after_build_fail_iteration_continue_response_path = f"{get_app_start_time()}_{get_driver_name()}/modify_after_build_fail/iteration/{cnt}/continue/{continue_cnt}/response.txt"
        default_logger.save_content(response_continue, save_modify_after_build_fail_iteration_continue_response_path)

        # 处理输出超限的情况，多次回复，拼接多次回复
        response += response_continue

        continue_cnt += 1
    
    # 保存modify_after_build_fail-iteration的回复内容
    save_modify_after_build_fail_iteration_response_path = f"{get_app_start_time()}_{get_driver_name()}/modify_after_build_fail/iteration/{cnt}/response.txt"
    default_logger.save_response(json.loads(response), save_modify_after_build_fail_iteration_response_path)

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