"""PCI驱动依赖分析主模块"""

import os
import json

# 导入自定义模块
from config import (
    FILE_MAPPINGS, OUTPUT_DIR, MAX_ITERATIONS
)
from file_utils import (
    get_file_path_without_line_number,
    get_base_directory_by_includes
)
from symbol_utils import (
    sanitize_driver_name,
    extract_final_driver_name,
    collect_same_file_symbols,
    find_symbol,
    verify_and_correct_symbol_type,
)
from dependency_analysis import (
    extract_dependencies,
    find_call_chain_ends
)
from output_utils import (
    add_symbol_to_driver_data,
    remove_duplicates,
    generate_declarations,
    create_driver_json_structure
)


def create_pci_driver_analysis():
    """主函数：创建PCI驱动分析"""
    # 1. 创建文件夹new_my_pci_driver（如果存在则不创建）
    output_dir = OUTPUT_DIR
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"创建输出目录: {output_dir}")
    else:
        print(f"输出目录已存在: {output_dir}")
    
    # 2. 读取所有的jsonl文件
    symbols = {
        'define': {},
        'enum': {},
        'enum_typedef': {},
        'func': {},
        'struct': {},
        'struct_typedef': {},
        'struct_init': {},
        'var': {}
    }
    
    for symbol_type, file_path in FILE_MAPPINGS.items():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    data = json.loads(line.strip())
                    
                    # 处理不同的符号格式
                    if symbol_type in ['enum_typedef', 'struct_typedef']:
                        # typedef格式：使用alias作为键，如果alias不存在则使用name
                        key = data.get('alias', data.get('name', ''))
                    else:
                        # 非typedef格式：使用name作为键
                        key = data.get('name', '')
                    
                    if key:
                        # 处理多个定义的情况
                        if key in symbols[symbol_type]:
                            if not isinstance(symbols[symbol_type][key], list):
                                symbols[symbol_type][key] = [symbols[symbol_type][key]]
                            symbols[symbol_type][key].append(data)
                        else:
                            symbols[symbol_type][key] = data
                            
            print(f"已加载 {len(symbols[symbol_type])} 个 {symbol_type}")
        except FileNotFoundError:
            print(f"警告: 找不到文件 {file_path}")
        except Exception as e:
            print(f"读取文件 {file_path} 时出错: {e}")
    
    # 3. 获取struct-init.jsonl中所有的pci_driver结构体初始化变量定义
    pci_drivers = []
    for name, data in symbols['struct_init'].items():
        if isinstance(data, list):
            for item in data:
                if "pci_driver" in item["source"]:
                    pci_drivers.append(item)
        else:
            if "pci_driver" in data["source"]:
                pci_drivers.append(data)
    
    print(f"找到 {len(pci_drivers)} 个PCI驱动初始化变量")
    
    # 添加跳过前x个驱动的功能
    skip_count = 0  # 设置要跳过的驱动数量，例如设置为5则跳过前5个驱动
    if skip_count > 0:
        print(f"跳过前 {skip_count} 个PCI驱动")
        pci_drivers = pci_drivers[skip_count:]
        print(f"剩余 {len(pci_drivers)} 个PCI驱动待分析")
    
    # 用于跟踪已使用的文件名
    used_filenames = set()
    
    # 处理每个PCI驱动
    for driver_index, driver_data in enumerate(pci_drivers):
        driver_path = driver_data["filename"]
        driver_name = driver_data["name"]
        
        # 显示当前处理的驱动索引（跳过后的实际索引）
        print(f"\n处理第 {skip_count + driver_index + 1} 个驱动 (总共 {len(pci_drivers) + skip_count} 个)")
        
        # 7. 提取驱动名称：从.name字段的最终引用
        final_driver_name = extract_final_driver_name(driver_data["source"], symbols, driver_path)
        if not final_driver_name:
            final_driver_name = driver_name
            print(f"警告: 无法提取驱动名称，使用变量名: {driver_name}")
        
        # 处理驱动名称中的"/"字符，替换为"+++"
        final_driver_name = sanitize_driver_name(final_driver_name)
        print(f"处理驱动: {final_driver_name} (变量名: {driver_name})")
        
        # 确定基础目录和头文件 - 使用新的基于#include的方法
        base_dir, header_files = get_base_directory_by_includes(driver_path)
        print(f"基础目录: {base_dir}")
        print(f"找到 {len(header_files)} 个头文件")
        
        # 创建JSON数据结构
        driver_json = create_driver_json_structure(final_driver_name, driver_path, base_dir, header_files)
        
        # 用于记录已添加的符号
        added_symbols = set()
        unknown_symbols = set()
        outside_base_dir_symbols = set()
        
        # 4. 获得该变量所在文件下的所有符号
        same_file_symbols = collect_same_file_symbols(driver_path, symbols)
        print(f"找到 {len(same_file_symbols)} 个同文件符号")
        
        # 5. 找到该pci_driver的向上调用终点
        call_chain_ends = find_call_chain_ends(driver_name, symbols, base_dir)
        print(f"找到 {len(call_chain_ends)} 个调用链终点")
        
        # 构建依赖分析队列
        queue = []
        
        # 将同文件符号加入队列
        for symbol_name in same_file_symbols:
            if symbol_name not in added_symbols and symbol_name not in queue:
                queue.append(symbol_name)
        
        # 将PCI驱动本身加入队列
        if driver_name not in added_symbols and driver_name not in queue:
            queue.append(driver_name)
        
        # 将向上调用链终点加入队列
        for end_function in call_chain_ends:
            if end_function not in added_symbols and end_function not in queue:
                queue.append(end_function)
        
        print(f"开始依赖分析，队列大小: {len(queue)}")
        
        # 6. 递归依赖分析
        processed_count = 0
        
        while queue and processed_count < MAX_ITERATIONS:
            symbol_name = queue.pop(0)
            processed_count += 1
            
            if symbol_name in added_symbols:
                continue
                
            # 查找符号定义
            symbol_data = find_symbol(symbol_name, symbols, base_dir, driver_path)
            
            if symbol_data:
                # 检查符号是否在基础目录中
                symbol_path_no_line = get_file_path_without_line_number(symbol_data["filename"])
                if symbol_path_no_line.startswith(base_dir):
                    # 在添加符号之前进行类型验证和重新定位
                    verified_symbol_data = verify_and_correct_symbol_type(symbol_name, symbol_data, symbols)
                    if verified_symbol_data:
                        added_symbols.add(symbol_name)
                        add_symbol_to_driver_data(symbol_name, verified_symbol_data, driver_json, symbols)
                        
                        # 提取依赖符号
                        new_deps = extract_dependencies(verified_symbol_data["source"])
                        for new_dep in new_deps:
                            if (new_dep not in added_symbols and 
                                new_dep not in queue and
                                new_dep not in unknown_symbols and
                                new_dep not in outside_base_dir_symbols):
                                queue.append(new_dep)
                    else:
                        print(f"警告: 无法验证符号类型: {symbol_name}")
                    
                    if processed_count % 100 == 0:
                        print(f"已处理 {processed_count} 个符号，队列剩余: {len(queue)}，已添加: {len(added_symbols)}")
                else:
                    # 符号有定义但不在基础目录中
                    outside_base_dir_symbols.add(symbol_name)
            else:
                # 未找到符号定义
                unknown_symbols.add(symbol_name)
        
        if processed_count >= MAX_ITERATIONS:
            print(f"警告: 达到最大迭代次数 {MAX_ITERATIONS}")
        
        # 8. 去重处理
        driver_json = remove_duplicates(driver_json)
        
        # 添加未知符号
        driver_json["UNKNOWN"] = list(unknown_symbols)
        
        # 添加不属于基础路径的符号
        driver_json["不属于基础路径的字符"] = list(outside_base_dir_symbols)
        
        # 9. 为struct-init定义和func定义创建声明
        generate_declarations(driver_json)
        
        # 10. 创建JSON文件 - 处理同名驱动
        base_filename = f"{final_driver_name}.json"
        filename = base_filename
        counter = 1
        
        # 检查文件名是否已存在，如果存在则添加数字后缀
        while filename in used_filenames:
            filename = f"{final_driver_name}{counter}.json"
            counter += 1
        
        # 添加到已使用文件名集合
        used_filenames.add(filename)
        
        filepath = os.path.join(output_dir, filename)
        
        # 如果文件已存在，删除它
        if os.path.exists(filepath):
            os.remove(filepath)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(driver_json, f, ensure_ascii=False, indent=2)
        
        print(f"已创建文件: {filename}")
        print(f"统计: {len(added_symbols)} 个符号, {len(unknown_symbols)} 个未知符号, {len(outside_base_dir_symbols)} 个不属于基础路径的符号")
        print("-" * 50)


if __name__ == "__main__":
    create_pci_driver_analysis()
    print("PCI驱动依赖分析完成！")
