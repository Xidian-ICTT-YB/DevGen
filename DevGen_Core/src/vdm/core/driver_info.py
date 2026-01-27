from vdm.utils.logger import setup_logger
from vdm.core.context import get_driver_name, set_driver_name
from vdm.services.config_loader import ConfigLoader
import json
from pathlib import Path
import os
import sqlite3

logger = setup_logger('DRIVER_INFO')

def query_by_name(db_path: str, table_name: str, name: str) -> list[dict]:
    """
    从指定 SQLite 表中按 name 查询记录，返回字典列表。
    
    Args:
        db_path (str): SQLite 数据库文件路径
        table_name (str): 要查询的表名（必须是合法标识符）
        name (str): 要匹配的 name 字段值
    
    Returns:
        list[dict]: 匹配的记录列表，每条记录为 {列名: 值} 的字典
                    无匹配时返回空列表 []
    
    Raises:
        sqlite3.Error: 数据库操作出错（如表不存在）
        ValueError: 表名包含非法字符（防注入）
    """

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # 关键：使 fetch 结果支持列名访问
    cursor = conn.cursor()

    try:
        # 使用参数化查询防注入，表名通过校验后拼接
        sql = f'SELECT * FROM "{table_name}" WHERE name = ?'
        cursor.execute(sql, (name,))
        rows = cursor.fetchall()
        
        # 转换为字典列表
        result = [dict(row) for row in rows]
        return result

    finally:
        conn.close()


class DriverInfo:
    """
    驱动信息类，提供结构体/宏定义和函数实现信息的访问接口
    """
    
    # 类变量，用于单例模式（可选）
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DriverInfo, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """
        初始化驱动信息类
        后续可以在这里添加JSON文件加载逻辑
        """
        # 初始化时可以留空，后续用于JSON文件路径配置等
        self._json_file_path = None
        self._json_file_path_detail = None
        self._jsonl_file_path = None
        self.symbols_jsonl = None
        self.symbols_json = None # 当前建模驱动的详细json文件内容
        self.pci_drivers = None

        # 加载配置
        config_loader = ConfigLoader()
        self.config = config_loader.load()
    
    def set_json_file_path(self):
        """
        设置当前建模驱动对应的简化json文件路径，用于step1和step2提供驱动信息
        """
        self._json_file_path = f"{self.config['paths']['data_path']}/json/{get_driver_name()}.json"
        logger.info(f"DriverInfo init with json(simple) file path: {self._json_file_path}")
    
    def set_json_file_path_detail(self):
        """
        设置当前建模驱动对应的详细json文件路径，用于step1-step4的搜索符号定义
        """
        self._json_file_path_detail = f"{self.config['paths']['data_path']}/json/detail/{get_driver_name()}.json"
        logger.info(f"DriverInfo init with json(detail) file path: {self._json_file_path_detail}")

    def set_jsonl_file_path(self):
        """
        设置jsonl文件路径，用于step1-step4的搜索符号定义
        """
        self._jsonl_file_path = f"{self.config['paths']['data_path']}/jsonl/"
        logger.info(f"DriverInfo init with jsonl file path: {self._jsonl_file_path}")

    def get_macro_struct_info(self) -> str:
        """
        返回结构体和宏定义相关信息
        Returns:
            str: 包含结构体和宏定义信息的字符串
        """
        self.set_json_file_path()
        
        with open(self._json_file_path, 'r', encoding='utf-8') as f:
            driver_info = json.load(f)
        
        logger.info(f"Get driver info from {self._json_file_path}")

        res = ""
        key_list = ["宏定义", "enum定义", "enum-typedef定义", "struct定义", "struct-typedef定义", "var声明", "struct-init声明", "func声明", "struct-init定义"]

        for key in key_list:
            for item in driver_info[key]:
                res += item["source"] + "\n"

        return res
    
    def get_function_implementations(self) -> str:
        """
        返回函数实现相关信息
        Returns:
            str: 包含函数实现信息的字符串
        """
        self.set_json_file_path()
        
        with open(self._json_file_path, 'r', encoding='utf-8') as f:
            driver_info = json.load(f)

        logger.info(f"Get driver info from {self._json_file_path}")

        res = ""
        key_list = ["struct-init定义", "func定义"]
        
        for key in key_list:
            for item in driver_info[key]:
                res += item["source"] + "\n"

        return res
    
    def get_symbol_by_name(self, name: str, type: str) -> str:
        """
        根据symbol名称获取指定的symbol信息
        Args:
            name (str): symbol名称
            type (str): symbol类型
        Returns:
            str or None: symbol信息，如果不存在则返回None
        """
        
        # 从json文件中获取symbol信息，每个json保存一个驱动全部的symbol信息
        if self.symbols_json == None:
            self.load_symbols_from_json()
        
        # 从jsonl文件中获取symbol信息，每个类型的symbol存在一个单独的jsonl中。如define.jsonl、function.jsonl、struct.jsonl等
        # 本次只加载struct_init
        if self.symbols_jsonl == None:
            self.load_symbols_from_jsonl_only_struct_init()

        self.pci_drivers = []
        for _, data in self.symbols_jsonl['struct_init'].items():
            if isinstance(data, list):
                for item in data:
                    if "pci_driver" in item["source"]:
                        self.pci_drivers.append(item)
            else:
                if "pci_driver" in data["source"]:
                    self.pci_drivers.append(data)

        # 获得驱动的路径
        driver_path = ""
        for driver_data in self.pci_drivers:
            driv_path = driver_data["filename"]
            driv_name = driver_data["name"]

            if driv_name == get_driver_name():
                driver_path = driv_path

        # 根据驱动地址，获得基地址，用于计算路径相似度
        base_dir = self.get_base_directory(driver_path)
        
        # 首先尝试从详细的json文件中搜索symbol信息
        logger.debug(f"Try to get symbol from json file: {name}, {type}")
        symbol_data = self.search_symbols_from_json(type, name)
        logger.debug(f"The result of search_symbols_from_json: {symbol_data}")

        if symbol_data == None:
            logger.debug(f"Try to get symbol from jsonl file: {name}, {type}, {base_dir}")
            symbol_data = self.find_symbol(name, type, base_dir)
            if symbol_data != None:
                symbol_data = symbol_data['source']
                logger.debug(f"The result of find_symbol from jsonl: {symbol_data}")

        return symbol_data

    def get_driver_path_by_driver_name(self) -> str:
        self.set_json_file_path()

        with open(self._json_file_path, 'r', encoding='utf-8') as f:
            driver_info = json.load(f)

        driver_path = driver_info["驱动核心路径"]

        if ":" in driver_path:
            driver_path = driver_path.split(":")[0]

        linux_path_prefix = self.config['paths']['linux_path_prefix']

        driver_path = driver_path.replace(linux_path_prefix, "")

        return driver_path


    def load_symbols_from_json(self):
        """
        加载当前建模设备的详细json文件，用于搜索symbol信息
        """
        self.symbols_json = {
            'define': {},
            'enum': {},
            'enum_typedef': {},
            'func': {},
            'struct': {},
            'struct_typedef': {},
            'struct_init': {},
        }
        
        self.set_json_file_path_detail()

        with open(self._json_file_path_detail, 'r', encoding='utf-8') as f:
            driver_info = json.load(f)

        for key, data in driver_info.items():
            if key == "宏定义":
                for item in data:
                    self.symbols_json['define'][item["name"]] = item
            elif key == "enum定义":
                for item in data:
                    self.symbols_json['enum'][item["name"]] = item
            elif key == "enum-typedef定义":
                for item in data:
                    self.symbols_json['enum_typedef'][item.get('alias', item.get('name', ''))] = item
            elif key == "struct定义":
                for item in data:
                    self.symbols_json['struct'][item["name"]] = item
            elif key == "struct-typedef定义":
                for item in data:
                    self.symbols_json['struct_typedef'][item.get('alias', item.get('name', ''))] = item
            elif key == "struct-init定义":
                for item in data:
                    self.symbols_json['struct_init'][item["name"]] = item
            elif key == "func定义":
                for item in data:
                    self.symbols_json['func'][item["name"]] = item

        logger.info(f"Load symbols from json successfully")

    def search_symbols_from_json(self, symbol_type, symbol_name):
        """
        从当前建模驱动对应的详细json文件中搜索symbol信息
        Args:
            symbol_type (str): symbol类型
            symbol_name (str): symbol名称
        Returns:
            str or None: symbol信息，如果不存在则返回None
        """
        if self.symbols_json == None:
            self.load_symbols_from_json()
        
        if symbol_type == 'struct':
            symbol_types = ['struct', 'struct_typedef', 'struct_init']
        elif symbol_type == 'enum':
            symbol_types = ['enum', 'enum_typedef']
        elif symbol_type == 'function':
            symbol_types = ['func']
        elif symbol_type == 'define':
            symbol_types = ['define']
        elif symbol_type == 'all':
            symbol_types = ['define', 'enum', 'enum_typedef', 'func', 'struct', 'struct_typedef', 'struct_init']
        else:
            return None

        res = None

        # 遍历symbol类型
        for symbol_type in symbol_types:
            # 遍历symbol类型中的所有symbol，判断和否匹配
            for name, data in self.symbols_json[symbol_type].items():
                if name == symbol_name:
                    if res == None:
                        res = str()
                    res += data['source'] + '\n'
                    break

        return res

    def load_symbols_from_jsonl_only_struct_init(self):

        self.symbols_jsonl = {
            'struct_init': {},
        }
        
        self.set_jsonl_file_path()

        self.file_mappings = {
            'struct_init': f'{self._jsonl_file_path}/struct-init.jsonl',
        }

        for symbol_type, file_path in self.file_mappings.items():
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
                            if key in self.symbols_jsonl[symbol_type]:
                                if not isinstance(self.symbols_jsonl[symbol_type][key], list):
                                    self.symbols_jsonl[symbol_type][key] = [self.symbols_jsonl[symbol_type][key]]
                                self.symbols_jsonl[symbol_type][key].append(data)
                            else:
                                self.symbols_jsonl[symbol_type][key] = data
                                
                logger.info(f"已加载 {len(self.symbols_jsonl[symbol_type])} 个 {symbol_type}")
            except FileNotFoundError:
                logger.warning(f"找不到文件 {file_path}")
            except Exception as e:
                logger.warning(f"读取文件 {file_path} 时出错: {e}")
    
    def get_file_path_without_line_number(self, file_path):
        """从文件路径中移除行号部分"""
        colon_pos = file_path.rfind(':')
        if colon_pos != -1:
            line_part = file_path[colon_pos + 1:]
            if line_part.isdigit():
                return file_path[:colon_pos]
        return file_path

    def calculate_path_similarity(self, path1, path2):
        """计算两个路径的相似度"""
        path1 = self.get_file_path_without_line_number(path1)
        path2 = self.get_file_path_without_line_number(path2)
        
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

    def select_best_definition(self, definitions, base_dir):
        """6. 从多个定义中根据路径相似度选择最佳的定义"""
        if not base_dir or not definitions:
            return definitions[0] if definitions else None
        
        best_definition = None
        best_similarity = -1
        
        for definition in definitions:
            definition_path = definition["filename"]
            similarity = self.calculate_path_similarity(definition_path, base_dir)
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_definition = definition
        
        return best_definition

    def find_symbol(self, symbol_name, symbol_type, base_dir=None):
        """6. 查找符号定义：如果没有找到定义返回None；如果找到一个定义返回该定义；如果找到多个定义，根据路径相似度选择最佳的定义"""

        if symbol_type == 'struct':
            symbol_types = ['struct', 'struct-typedef', 'struct-init', 'ioctl']
        elif symbol_type == 'enum':
            symbol_types = ['enum', 'enum-typedef']
        elif symbol_type == 'function':
            symbol_types = ['func']
        elif symbol_type == 'define':
            symbol_types = ['define']
        elif symbol_type == 'all':
            symbol_types = ['define', 'enum', 'enum-typedef', 'func', 'struct', 'struct-typedef', 'struct-init', 'ioctl']
        elif symbol_type == 'test':
            symbol_types = ['test']
        else:
            return None
        
        all_definitions = []
        
        for symbol_type in symbol_types:
            tmp = query_by_name(self.config['paths']['db_path'], symbol_type, symbol_name)
            if tmp != []:
                all_definitions.extend(tmp)
            # if symbol_name in symbols[symbol_type]:
            #     symbol_data = symbols[symbol_type][symbol_name]
            #     if isinstance(symbol_data, list):
            #         all_definitions.extend(symbol_data)
            #     else:
            #         all_definitions.append(symbol_data)
        
        if not all_definitions:
            return None
        
        if len(all_definitions) == 1:
            return all_definitions[0]
        
        # 多个定义：先筛选在基础目录下的定义
        base_dir_definitions = []
        if base_dir:
            for definition in all_definitions:
                definition_path = self.get_file_path_without_line_number(definition["filename"])
                if definition_path.startswith(base_dir):
                    base_dir_definitions.append(definition)
        
        # 如果有在基础目录下的定义，从中选择最佳
        if base_dir_definitions:
            return self.select_best_definition(base_dir_definitions, base_dir)
        
        # 如果没有在基础目录下的定义，从所有定义中选择最佳
        return self.select_best_definition(all_definitions, base_dir)

    def get_base_directory(self, file_path):
        """根据文件路径确定基础目录（定位到drivers/后的第一个子目录）"""
        file_path_no_line = self.get_file_path_without_line_number(file_path)
        
        # 查找drivers/在路径中的位置
        drivers_index = file_path_no_line.find('drivers/')
        if drivers_index == -1:
            # 如果没有找到drivers/，则返回文件所在目录
            return os.path.dirname(file_path_no_line)
        
        # 获取drivers/后的部分
        after_drivers = file_path_no_line[drivers_index + len('drivers/'):]
        
        # 找到第一个目录分隔符
        first_slash = after_drivers.find('/')
        if first_slash == -1:
            # 如果没有找到分隔符，说明路径就是drivers/后的第一个目录
            return file_path_no_line
        
        # 返回drivers/后的第一个子目录的完整路径
        base_dir = file_path_no_line[:drivers_index + len('drivers/') + first_slash]
        return base_dir
    
# 创建全局实例，便于其他模块导入使用
driver_info = DriverInfo()

if __name__ == "__main__":
    # 测试代码
    set_driver_name("adm8211")
    driver_info = DriverInfo()

    res = driver_info.find_symbol('aceaddr', 'all')
    print(res)