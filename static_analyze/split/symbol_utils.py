import re
import os

from config import (
    COMMENT_PATTERN, NAME_FIELD_PATTERN, NAME_VAR_PATTERN, 
    DEFINE_STRING_PATTERN, VARIABLE_STRING_PATTERN, C_KEYWORDS
)
from file_utils import (
    get_file_path_without_line_number, 
    get_base_directory_by_includes_simple, 
    select_by_path_similarity,
    calculate_path_similarity
)
def remove_comments(source_code):
    """移除C语言注释"""
    return COMMENT_PATTERN.sub('', source_code)

def sanitize_driver_name(driver_name):
    """处理驱动名称中的特殊字符，将'/'替换为'+++'"""
    if '/' in driver_name:
        sanitized_name = driver_name.replace('/', '+++')
        print(f"注意: 驱动名称中的'/'已替换为'+++': {driver_name} -> {sanitized_name}")
        return sanitized_name
    return driver_name

def extract_final_driver_name(driver_source, symbols, driver_path):
    """提取驱动名称：从pci_driver结构体初始化变量下的.name字段的最终引用"""
    # 去除注释以避免干扰
    clean_source = remove_comments(driver_source)
    
    # 查找.name字段的值
    # 情况1: .name = "直接字符串"
    name_match = NAME_FIELD_PATTERN.search(clean_source)
    if name_match:
        return name_match.group(1)
    
    # 情况2: .name = 宏定义或变量
    name_match = NAME_VAR_PATTERN.search(clean_source)
    if name_match:
        var_name = name_match.group(1)
        
        print(f"调试: 提取驱动名称，找到变量引用: {var_name}")
        
        # 1. 首先尝试在同文件中查找该变量/宏
        same_file_symbols = collect_same_file_symbols(driver_path, symbols)
        if var_name in same_file_symbols:
            var_data = same_file_symbols[var_name]
            print(f"调试: 从同文件中找到变量定义: {var_name}")
        else:
            # 2. 如果在同文件中没有找到，尝试在基础路径下查找
            base_dir = get_base_directory_by_includes_simple(driver_path)
            var_data = find_symbol_in_base_dir(var_name, symbols, base_dir, driver_path)
            if var_data:
                print(f"调试: 从基础路径 {base_dir} 中找到变量定义: {var_name}")
            else:
                # 3. 如果基础路径中也没有找到，尝试全局查找
                var_data = find_symbol(var_name, symbols, None, driver_path)
                if var_data:
                    print(f"调试: 从全局符号中找到变量定义: {var_name}")
        
        if var_data:
            # 尝试从定义中提取字符串值
            
            # 情况2.1: 宏定义 #define DRIVER_NAME "virtio_gpu"
            if var_data['source'].startswith('#define'):
                str_match = DEFINE_STRING_PATTERN.search(var_data['source'])
                if str_match:
                    print(f"调试: 从宏定义中提取驱动名称: {str_match.group(1)}")
                    return str_match.group(1)
            
            # 情况2.2: 变量定义 char e1000e_driver_name[] = "e1000e"
            str_match = VARIABLE_STRING_PATTERN.search(var_data['source'])
            if str_match:
                print(f"调试: 从变量定义中提取驱动名称: {str_match.group(1)}")
                return str_match.group(1)
            
            # 情况2.3: 变量声明 extern char e1000e_driver_name[]
            # 这种情况下我们需要继续查找实际定义
            if 'extern' in var_data['source']:
                # 查找非extern的定义
                for symbol_type in ['var', 'define']:
                    if var_name in symbols[symbol_type]:
                        symbol_data = symbols[symbol_type][var_name]
                        if isinstance(symbol_data, list):
                            for data in symbol_data:
                                if 'extern' not in data['source']:
                                    str_match = VARIABLE_STRING_PATTERN.search(data['source'])
                                    if str_match:
                                        print(f"调试: 从非extern定义中提取驱动名称: {str_match.group(1)}")
                                        return str_match.group(1)
                        else:
                            if 'extern' not in symbol_data['source']:
                                str_match = VARIABLE_STRING_PATTERN.search(symbol_data['source'])
                                if str_match:
                                    print(f"调试: 从非extern定义中提取驱动名称: {str_match.group(1)}")
                                    return str_match.group(1)
    
    return None

def collect_same_file_symbols(driver_path, symbols):
    """获得该变量所在文件下的所有符号"""
    same_file_symbols = {}
    driver_path_no_line = get_file_path_without_line_number(driver_path)
    
    # 遍历所有符号类型
    for symbol_type in symbols:
        for symbol_name, symbol_data in symbols[symbol_type].items():
            # 处理单个定义和多个定义的情况
            if isinstance(symbol_data, list):
                for data in symbol_data:
                    # 获取不带行号的符号文件路径
                    symbol_path_no_line = get_file_path_without_line_number(data["filename"])
                    if symbol_path_no_line == driver_path_no_line:
                        same_file_symbols[symbol_name] = data
                        break  # 只取第一个同文件定义
            else:
                # 获取不带行号的符号文件路径
                symbol_path_no_line = get_file_path_without_line_number(symbol_data["filename"])
                if symbol_path_no_line == driver_path_no_line:
                    same_file_symbols[symbol_name] = symbol_data
    
    return same_file_symbols

def find_symbol_in_base_dir(symbol_name, symbols, base_dir, driver_path):
    """在基础路径下查找符号定义"""
    symbol_types = [
        'func', 'struct', 'struct_typedef', 'enum', 
        'enum_typedef', 'define', 'struct_init', 'var'
    ]
    
    all_definitions = []
    
    for symbol_type in symbol_types:
        if symbol_name in symbols[symbol_type]:
            symbol_data = symbols[symbol_type][symbol_name]
            if isinstance(symbol_data, list):
                for data in symbol_data:
                    # 检查符号是否在基础目录中
                    symbol_path_no_line = get_file_path_without_line_number(data["filename"])
                    if symbol_path_no_line.startswith(base_dir):
                        all_definitions.append(data)
            else:
                # 检查符号是否在基础目录中
                symbol_path_no_line = get_file_path_without_line_number(symbol_data["filename"])
                if symbol_path_no_line.startswith(base_dir):
                    all_definitions.append(symbol_data)
    
    if not all_definitions:
        return None
    
    if len(all_definitions) == 1:
        return all_definitions[0]
    
    # 多个定义：按照优先级选择最佳定义
    return select_best_definition(all_definitions, base_dir, driver_path, symbol_name)

def find_symbol(symbol_name, symbols, base_dir=None, driver_path=None):
    """查找符号定义：如果没有找到定义返回None；如果找到一个定义返回该定义；如果找到多个定义，根据优先级选择最佳的定义"""
    symbol_types = [
        'func', 'struct', 'struct_typedef', 'enum', 
        'enum_typedef', 'define', 'struct_init', 'var'
    ]
    
    all_definitions = []
    
    for symbol_type in symbol_types:
        if symbol_name in symbols[symbol_type]:
            symbol_data = symbols[symbol_type][symbol_name]
            if isinstance(symbol_data, list):
                all_definitions.extend(symbol_data)
            else:
                all_definitions.append(symbol_data)
    
    if not all_definitions:
        return None
    
    if len(all_definitions) == 1:
        return all_definitions[0]
    
    # 多个定义：按照优先级选择最佳定义
    return select_best_definition(all_definitions, base_dir, driver_path, symbol_name)

def select_best_definition(definitions, base_dir, driver_path, symbol_name):
    """从多个定义中根据优先级选择最佳的定义"""
    if not definitions:
        return None
    
    # 获取不带行号的驱动文件路径
    driver_path_no_line = get_file_path_without_line_number(driver_path) if driver_path else None
    
    # 按照优先级选择
    best_definition = None
    
    # 优先级1: 同文件定义
    if driver_path_no_line:
        for definition in definitions:
            def_path_no_line = get_file_path_without_line_number(definition["filename"])
            if def_path_no_line == driver_path_no_line:
                best_definition = definition
                break
    
    # 优先级2: 同名头文件定义
    if not best_definition and driver_path_no_line:
        # 获取驱动文件的目录和基本名称
        driver_dir = os.path.dirname(driver_path_no_line)
        driver_basename = os.path.basename(driver_path_no_line)
        driver_name_without_ext = os.path.splitext(driver_basename)[0]
        
        # 构建对应的头文件名
        header_filename = f"{driver_name_without_ext}.h"
        
        for definition in definitions:
            def_path_no_line = get_file_path_without_line_number(definition["filename"])
            def_basename = os.path.basename(def_path_no_line)
            
            # 检查是否是同名头文件
            if def_basename == header_filename and os.path.dirname(def_path_no_line) == driver_dir:
                best_definition = definition
                break
    
    # 优先级3: 路径相似度最高的定义
    if not best_definition:
        best_definition = select_by_path_similarity(definitions, base_dir)
    
    return best_definition

def select_by_path_similarity(definitions, base_dir):
    """通过路径相似度选择最佳定义"""
    best_definition = None
    best_similarity = -1
    
    for definition in definitions:
        definition_path = get_file_path_without_line_number(definition["filename"])
        similarity = calculate_path_similarity(definition_path, base_dir)
        
        if similarity > best_similarity:
            best_similarity = similarity
            best_definition = definition
    
    return best_definition

def get_symbol_type(symbol_name, symbols):
    """确定符号的类型 - 简单直接的方法"""
    symbol_types = [
        ('func', 'func'),
        ('struct', 'struct'),
        ('struct_typedef', 'struct_typedef'),
        ('enum', 'enum'),
        ('enum_typedef', 'enum_typedef'),
        ('define', 'define'),
        ('struct_init', 'struct_init'),
        ('var', 'var')
    ]
    
    for symbol_type, key in symbol_types:
        if symbol_name in symbols[key]:
            return symbol_type
    
    return "unknown"

def verify_and_correct_symbol_type(symbol_name, symbol_data, symbols):
    """验证和修正符号类型 - 通过检查源码与jsonl文件中的原始定义"""
    # 获取当前符号类型
    current_type = get_symbol_type(symbol_name, symbols)
    
    # 检查符号类型是否与源码匹配
    if is_type_matched(symbol_data["source"], current_type):
        return symbol_data
    
    # 如果不匹配，尝试重新定位符号定义
    print(f"警告: 符号类型不匹配，尝试重新定位: {symbol_name} (当前类型: {current_type})")
    
    # 在所有jsonl文件中查找匹配的定义
    for symbol_type, symbol_dict in symbols.items():
        if symbol_name in symbol_dict:
            symbol_list = symbol_dict[symbol_name]
            if not isinstance(symbol_list, list):
                symbol_list = [symbol_list]
            
            for candidate in symbol_list:
                # 比较文件路径和源码
                if (candidate["filename"] == symbol_data["filename"] and 
                    candidate["source"] == symbol_data["source"]):
                    # 找到匹配的定义，返回修正后的数据
                    corrected_data = candidate.copy()
                    print(f"修正符号类型: {symbol_name} -> {symbol_type}")
                    return corrected_data
    
    # 如果找不到匹配的定义，返回原始数据
    print(f"警告: 无法重新定位符号定义: {symbol_name}")
    return symbol_data

def is_type_matched(source_code, symbol_type):
    """检查源码是否与符号类型匹配 - 简单但可靠的检查"""
    clean_source = remove_comments(source_code).strip()
    
    if symbol_type == "func":
        return is_likely_function_simple(clean_source)
    elif symbol_type == "struct":
        return is_likely_struct_simple(clean_source)
    elif symbol_type == "enum":
        return is_likely_enum_simple(clean_source)
    elif symbol_type == "define":
        return clean_source.startswith('#define')
    elif symbol_type == "var":
        return is_likely_variable_simple(clean_source)
    elif symbol_type == "struct_init":
        return is_likely_struct_init_simple(clean_source)
    
    return True  # 对于未知类型，默认匹配

def is_likely_function_simple(source_code):
    """简单但可靠的函数定义检查"""
    clean_source = source_code.strip()
    
    # 空字符串不是函数
    if not clean_source:
        return False
    
    # 检查是否是宏定义
    if clean_source.startswith('#define'):
        return False
    
    # 检查是否有花括号但没有小括号 - 这种情况一定不是函数定义
    has_braces = '{' in clean_source and '}' in clean_source
    has_parentheses = '(' in clean_source and ')' in clean_source
    
    # 如果有花括号但没有小括号，一定不是函数
    if has_braces and not has_parentheses:
        return False
    
    # 如果有小括号但没有花括号，可能是函数声明
    # 函数声明通常以分号结尾
    if has_parentheses and not has_braces:
        return clean_source.strip().endswith(';')
    
    # 如果既有括号又有花括号，可能是函数定义
    if has_parentheses and has_braces:
        return True
    
    return False

def is_likely_struct_simple(source_code):
    """简单但可靠的结构体定义检查"""
    clean_source = source_code.strip()
    return clean_source.startswith('struct ') or 'struct ' in clean_source

def is_likely_enum_simple(source_code):
    """简单但可靠的枚举定义检查"""
    clean_source = source_code.strip()
    return clean_source.startswith('enum ') or 'enum ' in clean_source

def is_likely_variable_simple(source_code):
    """简单但可靠的变量定义检查"""
    clean_source = source_code.strip()
    
    # 检查是否是变量定义（包含等号）
    if '=' in clean_source and not clean_source.startswith('#define'):
        return True
    
    # 检查是否是数组声明
    if re.search(r'\w+\s*\[.*\]', clean_source):
        return True
    
    return False

def is_likely_struct_init_simple(source_code):
    """简单但可靠的结构体初始化检查"""
    clean_source = source_code.strip()
    return '= {' in clean_source and 'struct ' in clean_source

def check_symbol_reference(source_code, symbol_name):
    """检查源代码中是否包含对指定符号的引用"""
    clean_source = remove_comments(source_code)
    
    patterns = [
        rf'pci_(register|unregister)_driver\s*\(\s*&?\s*\b{re.escape(symbol_name)}\b',
        rf'\.\s*[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*&?\s*\b{re.escape(symbol_name)}\b',
        rf'=\s*&?\s*\b{re.escape(symbol_name)}\b',
        rf'\b{re.escape(symbol_name)}\s*\(',
        rf'\b{re.escape(symbol_name)}\s*\[',
        rf'ARRAY_SIZE\s*\(\s*\b{re.escape(symbol_name)}\b\s*\)'
    ]
    
    for pattern in patterns:
        if re.search(pattern, clean_source):
            return True
    
    return False

def is_c_keyword(word):
    """检查是否是C语言关键字"""
    return word in C_KEYWORDS


