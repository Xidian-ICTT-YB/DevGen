import json
from vdm.utils.logger import setup_logger
from vdm.utils.save_logs import default_logger
from vdm.core.llm_client import client
from vdm.core.prompt_manager import prompt_manager
from vdm.core.context import get_app_start_time, get_driver_name
from vdm.core.driver_info import driver_info

logger = setup_logger('STEP 2')

def step2_run(device_code: str) -> str:
    """
    执行第二步处理流程，根据部分驱动代码（包含函数定义、struct-init定义等），生成补充好函数实现的qemu设备代码，返回设备代码
    """
    logger.info('============================= STEP 2 RUN =============================')
    device_code, needed_sources = step2(device_code)   

    # 如若返回的needed_sources不为空，则进行step2的迭代补全
    if needed_sources != []:
        device_code = step2_iterations(device_code, needed_sources)
    
    logger.info('============================= STEP 2 RUN END =============================')

    # 保存device_code
    save_device_code_path = f"{get_app_start_time()}_{get_driver_name()}/step2/device_code.txt"
    default_logger.save_content(device_code, save_device_code_path)

    return device_code

def step2(device_code: str) -> tuple[str, list]:
    """
    执行第二步处理流程，根据部分驱动代码（包含函数定义、struct-init定义等），生成补充好函数实现的qemu设备代码，返回设备代码，执行一次
    """
    logger.info('============================= STEP 2 main =============================')

    # 获取step2的prompt
    step2_prompt = prompt_manager.get_prompt("step2", 
                                             DRIVER_PATH=driver_info.get_driver_path_by_driver_name(), 
                                             Relevant_Source=get_driver_code_detail(), 
                                             QEMU_CODE=device_code
                                            )

    # 构造历史记录
    step2_history_messages = [
        {"role": "system", "content": prompt_manager.get_prompt("system")},
        {"role": "user", "content": prompt_manager.get_prompt("step0")},
        {"role": "assistant", "content": "OK"},
        {"role": "user", "content": prompt_manager.get_prompt("two_examples")},
        {"role": "assistant", "content": "OK"},
    ]

    # 构造step2的message
    step2_messages = step2_history_messages + [
        {"role": "user", "content": step2_prompt}
    ]

    # 保存step2的message
    save_step2_messages_path = f"{get_app_start_time()}_{get_driver_name()}/step2/messages"
    default_logger.save_messages(step2_messages, save_step2_messages_path)

    # 调用LLM
    response, finish_reason = client.chat_completion_json(step2_messages)

    # 处理输出超限的情况，多次回复
    continue_cnt = 1
    while finish_reason == "length":
        if continue_cnt >= 5:
            break
        # 构造继续获取完整输出的message
        step2_continue_messages = step2_messages + [
            {"role": "assistant", "content": response}, 
            {"role": "user", "content": prompt_manager.get_prompt("full_output")},
        ]

        # 保存step2_continue的message
        save_step2_continue_messages_path = f"{get_app_start_time()}_{get_driver_name()}/step2/continue/{continue_cnt}/messages"
        default_logger.save_messages(step2_continue_messages, save_step2_continue_messages_path)

        # 调用LLM
        response_continue, finish_reason = client.chat_completion_json(step2_continue_messages)

        # 保存回复内容
        save_step2_continue_response_path = f"{get_app_start_time()}_{get_driver_name()}/step2/continue/{continue_cnt}/response.txt"
        default_logger.save_content(response_continue, save_step2_continue_response_path)

        # 处理输出超限的情况，多次回复，拼接多次回复
        response += response_continue

        continue_cnt += 1

    # 保存step2的回复内容
    save_step2_response_path = f"{get_app_start_time()}_{get_driver_name()}/step2/response.txt"
    default_logger.save_content(response, save_step2_response_path)
    save_step2_response_path = f"{get_app_start_time()}_{get_driver_name()}/step2/response_visual.txt"
    default_logger.save_response(json.loads(response), save_step2_response_path)

    # 处理LLM返回的json
    response_json = json.loads(response)
    device_code = response_json["code"]
    needed_sources = response_json["needed_sources"]

    logger.info('============================= STEP 2 main END =============================')

    return device_code, needed_sources

def step2_iterations(device_code: str, needed_sources: list) -> str:
    """
    进行step2的多次迭代补全，直到needed_sources为空或者达到最大迭代次数
    """
    iteration = 0
    max_iterations = 3

    while needed_sources != [] and iteration < max_iterations: 
        logger.info(f'============================= STEP 2 iteration {iteration} =============================')

        is_searched, device_code, needed_sources = step2_iteration(iteration, device_code, needed_sources)

        # 如若无法继续搜索则退出迭代，无法找到needed_sources对应的资源
        if not is_searched:
            break

        iteration += 1

        logger.info(f'============================= STEP 2 iteration {iteration} END =============================')

    return device_code
        

def step2_iteration(cnt: int, device_code: str, needed_sources: list) -> tuple[bool, str, list]:
    """
    进行step2的一次迭代补全，返回补全后的设备代码和所需资源列表，如果无法补全则返回原始设备代码和所需资源列表，同时返回标志位（True表示可以完成搜索,False为反）
    """
    # 处理needed_sources
    relevant_source = handle_needed_resources(needed_sources)
    if relevant_source == "None":
        return False, device_code, needed_sources
    
    # 获取step2-iteration的prompt
    step2_iteration_prompt = prompt_manager.get_prompt("step2_iteration", 
                                                       DRIVER_PATH=driver_info.get_driver_path_by_driver_name(), 
                                                       Relevant_Source=relevant_source, 
                                                       QEMU_CODE=device_code
                                                      )

    # 构造step2-iteration的历史记录
    step2_iteration_history_messages = [
        {"role": "system", "content": prompt_manager.get_prompt("system")},
        {"role": "user", "content": prompt_manager.get_prompt("step0")},
        {"role": "assistant", "content": "OK"},
        {"role": "user", "content": prompt_manager.get_prompt("two_examples")},
        {"role": "assistant", "content": "OK"},
    ]
     
    # 构造step2-iteration的message
    step2_iteration_messages = step2_iteration_history_messages + [
        {"role": "user", "content": step2_iteration_prompt}
    ]

    # 保存step2-iteration的message
    save_step2_iteration_messages_path = f"{get_app_start_time()}_{get_driver_name()}/step2/iteration/{cnt}/messages"
    default_logger.save_messages(step2_iteration_messages, save_step2_iteration_messages_path)

    # 调用LLM
    response, finish_reason = client.chat_completion_json(step2_iteration_messages)

    # 处理输出超限的情况，多次回复
    continue_cnt = 1
    while finish_reason == "length" or finish_reason == "None":
        if continue_cnt >= 3:
            break
        # 构造继续获取完整输出的message
        step2_iteration_continue_messages = step2_iteration_messages + [
            {"role": "assistant", "content": response}, 
            {"role": "user", "content": prompt_manager.get_prompt("full_output")},
        ]

        # 保存step2-iteration_continue的message
        save_step2_iteration_continue_messages_path = f"{get_app_start_time()}_{get_driver_name()}/step2/iteration/{cnt}/continue/{continue_cnt}/messages"
        default_logger.save_messages(step2_iteration_continue_messages, save_step2_iteration_continue_messages_path)

        # 调用LLM
        response_continue, finish_reason = client.chat_completion_json(step2_iteration_continue_messages)

        # 保存回复内容
        save_step2_iteration_continue_response_path = f"{get_app_start_time()}_{get_driver_name()}/step2/iteration/{cnt}/continue/{continue_cnt}/response.txt"
        default_logger.save_content(response_continue, save_step2_iteration_continue_response_path)
            
        # 处理输出超限的情况，多次回复，拼接多次回复
        response += response_continue

        continue_cnt += 1
    
    # 保存step2-iteration的回复内容
    save_step2_iteration_response_path = f"{get_app_start_time()}_{get_driver_name()}/step2/iteration/{cnt}/response.txt"
    default_logger.save_response(json.loads(response), save_step2_iteration_response_path)
    
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

def get_driver_code_detail() -> str:
    """
    获取驱动代码，完整的驱动代码
    """
    return driver_info.get_function_implementations()

    