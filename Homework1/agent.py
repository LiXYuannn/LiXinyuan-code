"""
Agent 核心逻辑模块：实现“输入 -> 推理 -> 工具调用 -> 输出”的 Agent 循环。
"""
import os
from openai import OpenAI
from tools import read_code_file, list_directory_files

class CodeAgent:
    def __init__(self):
        # 此处使用兼容 OpenAI 格式的 API（如 DeepSeek、通义千问等，可在环境变量中配置）
        # 默认读取环境变量：OPENAI_API_KEY 和 OPENAI_BASE_URL
        self.client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY", "your-api-key-here"),
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com") # 默认以 DeepSeek 为例，可自行修改
        )
        # 选用适合的轻量高效模型
        self.model = os.environ.get("OPENAI_MODEL", "deepseek-chat")
        
        # 定义系统提示词 (Prompt Design)，赋予其代码助手身份
        self.system_prompt = (
            "你是一个专业的软件开发和代码审查 Agent。你的任务是协助用户阅读、解释、审查或优化代码。\n"
            "当你需要读取本地文件来获取代码时，你可以告诉用户或直接调用工具。目前你可以使用的工具包括：\n"
            "1. read_code_file(file_path): 读取指定路径的代码文件内容。\n"
            "2. list_directory_files(dir_path): 列出指定目录下的所有文件。\n"
            "请根据用户的问题进行严谨的逻辑推理，并给出清晰、规范的中文解答。"
        )

    def run(self, user_query: str) -> str:
        """
        运行 Agent 循环
        """
        # 简单的前置意图识别与工具触发示例（支持直接读取文件类指令）
        if "读取" CATCH if "读" in user_query or "查看" in user_query or "文件" in user_query:
            # 可以在此处扩展更智能的 ReAct 循环或 Tool Calling 逻辑
            pass

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_query}
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"调用大模型时发生错误: {str(e)}，请检查您的 API Key 是否正确配置。"