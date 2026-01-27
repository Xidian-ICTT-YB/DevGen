import os
from config import INCLUDE_PATTERN

def get_file_path_without_line_number(file_path):
    """从文件路径中移除行号部分"""
    if not file_path:
        return file_path
    
    colon_pos = file_path.rfind(':')
    if colon_pos != -1:
        line_part = file_path[colon_pos + 1:]
        if line_part.isdigit():
            return file_path[:colon_pos]
    return file_path

def resolve_include_path(include_path, current_file):
    """解析#include路径为绝对路径"""
    current_dir = os.path.dirname(current_file)
    
    # 处理相对路径
    if include_path.startswith('./'):
        resolved = os.path.join(current_dir, include_path[2:])
    elif include_path.startswith('../'):
        resolved = os.path.join(current_dir, include_path)
    else:
        # 直接在当前目录查找
        resolved = os.path.join(current_dir, include_path)
    
    # 返回规范化的绝对路径
    return os.path.abspath(resolved)

def find_common_parent_directory(directories):
    """找到所有目录的最大公共路径"""
    if not directories:
        return ""
    
    # 将路径分割为组件
    path_components = [d.split(os.sep) for d in directories]
    
    # 找到最短路径的长度
    min_length = min(len(components) for components in path_components)
    
    # 比较每个位置的组件
    common_components = []
    for i in range(min_length):
        current_component = path_components[0][i]
        if all(components[i] == current_component for components in path_components):
            common_components.append(current_component)
        else:
            break
    
    # 重建路径
    if not common_components:
        return ""
    
    return os.sep.join(common_components)

def get_base_directory_by_includes(file_path):
    """根据文件中的#include ""指令确定驱动核心路径，并收集所有头文件"""
    file_path_no_line = get_file_path_without_line_number(file_path)
    
    # 收集所有相关文件的目录
    all_dirs = set()
    # 收集所有头文件的绝对路径
    header_files = []
    
    # 处理初始文件
    all_dirs.add(os.path.dirname(file_path_no_line))
    
    # 递归处理#include ""文件
    processed_files = set()
    queue = [file_path_no_line]
    
    while queue:
        current_file = queue.pop(0)
        if current_file in processed_files:
            continue
        processed_files.add(current_file)
        
        # 读取文件内容
        try:
            with open(current_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            print(f"警告: 无法读取文件 {current_file}: {e}")
            continue
        
        # 提取所有的#include ""指令
        includes = INCLUDE_PATTERN.findall(content)
        
        for include_path in includes:
            # 解析包含路径
            resolved_path = resolve_include_path(include_path, current_file)
            if resolved_path and os.path.exists(resolved_path):
                # 添加文件所在目录
                all_dirs.add(os.path.dirname(resolved_path))
                # 将头文件添加到列表
                header_files.append(resolved_path)
                # 将文件加入队列继续处理
                queue.append(resolved_path)
    
    # 计算所有目录的最大公共路径
    if not all_dirs:
        base_dir = os.path.dirname(file_path_no_line)
    else:
        base_dir = find_common_parent_directory(list(all_dirs))
    
    return base_dir, header_files

def get_base_directory_by_includes_simple(file_path):
    """简化版的基础路径确定函数，用于驱动名称提取阶段"""
    file_path_no_line = get_file_path_without_line_number(file_path)
    return os.path.dirname(file_path_no_line)

def is_symbol_in_base_dir(symbol_path, base_dir):
    """检查符号路径是否在基础目录中"""
    symbol_path_no_line = get_file_path_without_line_number(symbol_path)
    return symbol_path_no_line.startswith(base_dir)

def calculate_path_similarity(path1, path2):
    """计算两个路径的相似度（去除行号）"""
    path1 = get_file_path_without_line_number(path1)
    path2 = get_file_path_without_line_number(path2)
    
    # 如果path2是None，返回0
    if not path2:
        return 0
    
    dirs1 = path1.split('/')
    dirs2 = path2.split('/')
    
    # 计算共同前缀的长度
    common_prefix = 0
    for i in range(min(len(dirs1), len(dirs2))):
        if dirs1[i] == dirs2[i]:
            common_prefix += 1
        else:
            break
    
    # 相似度 = 共同前缀长度 / 最大路径长度
    max_length = max(len(dirs1), len(dirs2))
    similarity = common_prefix / max_length if max_length > 0 else 0
    
    return similarity

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
