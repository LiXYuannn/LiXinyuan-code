"""
工具集模块：为 Agent 提供与本地环境交互的工具（如文件读取、目录查看等）。
"""
import os

def read_code_file(file_path: str) -> str:
    """
    读取本地指定的代码文件内容
    :param file_path: 文件路径
    :return: 文件内容或错误信息
    """
    if not os.path.exists(file_path):
        return f"错误：文件 '{file_path}' 不存在，请检查路径是否正确。"
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except Exception as e:
        return f"读取文件时发生异常: {str(e)}"

def list_directory_files(dir_path: str = ".") -> str:
    """
    列出指定目录下的文件列表，帮助 Agent 了解项目结构
    :param dir_path: 目录路径
    :return: 文件列表字符串
    """
    if not os.path.exists(dir_path):
        return f"错误：目录 '{dir_path}' 不存在。"
    
    try:
        files = os.listdir(dir_path)
        # 过滤掉隐藏文件和虚拟环境目录
        filtered_files = [f for f in files if not f.startswith('.') and f not in ['__pycache__', 'venv']]
        return f"目录 {dir_path} 下的文件有: " + ", ".join(filtered_files)
    except Exception as e:
        return f"获取目录列表失败: {str(e)}"