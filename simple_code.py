import json
import os


def filter_json_by_path(data, path_keywords):

    if isinstance(data, dict):
        if "path" in data:
            path_value = data["path"]
            if not any(keyword in path_value for keyword in path_keywords):
                return None  

        result = {}
        for key, value in data.items():
            filtered_value = filter_json_by_path(value, path_keywords)
            if filtered_value is not None:
                result[key] = filtered_value
            else:
                top_level_keys = ["驱动名称", "驱动核心路径", "宏定义", "enum定义", "enum-typedef定义",
                                  "struct定义", "struct-typedef定义", "var声明", "struct-init声明",
                                  "func声明", "struct-init定义", "func定义"]
                if key in top_level_keys:
                    if isinstance(value, list):
                        result[key] = []
                    else:
                        result[key] = None

        return result if result else None

    elif isinstance(data, list):
        result = []
        for item in data:
            filtered_item = filter_json_by_path(item, path_keywords)
            if filtered_item is not None:
                result.append(filtered_item)
        return result

    else:
        return data


def create_empty_structure(original_data):
    empty_structure = {}
    for key, value in original_data.items():
        if isinstance(value, list):
            empty_structure[key] = []
        else:
            empty_structure[key] = None
    return empty_structure


def ensure_top_level_keys(original_data, filtered_data):
    if filtered_data is None:
        filtered_data = {}

    for key in original_data.keys():
        if key not in filtered_data:
            original_value = original_data[key]
            if isinstance(original_value, list):
                filtered_data[key] = []
            else:
                filtered_data[key] = None

    return filtered_data


def process_single_json_file(input_file, output_file, path_keywords):
    try:
        if not os.path.exists(input_file):
            print(f"警告: 输入文件 '{input_file}' 不存在，跳过处理")
            return False

        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print(f"开始过滤JSON数据: {input_file}")
        print(f"过滤关键词: {path_keywords}")

        filtered_data = filter_json_by_path(data, path_keywords)

        if filtered_data is None:
            filtered_data = create_empty_structure(data)

        filtered_data = ensure_top_level_keys(data, filtered_data)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(filtered_data, f, ensure_ascii=False, indent=2)

        print(f"过滤完成! 结果已保存到: {output_file}")
        return True

    except Exception as e:
        print(f"处理文件 '{input_file}' 时发生错误: {e}")
        return False


def batch_process_json_files(config_file):

    try:
        # 读取配置文件
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        print(f"开始批量处理，共 {len(config)} 个文件需要处理")
        print("=" * 50)

        success_count = 0
        fail_count = 0

        for key, path_keywords in config.items():
            print(f"\n正在处理: {key}")

            input_dir= "data/100_example_6.18/"
            output_dir= "data/100_example_new_6.18/"
            input_file = input_dir + f"{key}.json"
            output_file = output_dir + f"{key}.json"

            if process_single_json_file(input_file, output_file, path_keywords):
                success_count += 1
            else:
                fail_count += 1

        print("\n" + "=" * 50)
        print(f"批量处理完成!")
        print(f"成功: {success_count} 个文件")
        print(f"失败: {fail_count} 个文件")

    except Exception as e:
        print(f"批量处理时发生错误: {e}")
        return False


if __name__ == "__main__":

    config_file = "data/100_example.json"  

    batch_process_json_files(config_file)
