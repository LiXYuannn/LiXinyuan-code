"""
主程序入口：提供简单的命令行交互界面，用于启动代码 Agent。
"""
from agent import CodeAgent

def main():
    print("=" * 50)
    print("欢迎使用智能代码助手 Agent（Homework 1）")
    print("支持功能：代码审查、解释、逻辑分析与文件读取")
    print("输入 'exit' 或 'quit' 即可退出程序。")
    print("=" * 50)

    # 初始化 Agent
    try:
        agent = CodeAgent()
    except Exception as e:
        print(f"初始化 Agent 失败，请检查 API Key 或网络配置: {e}")
        return

    while True:
        try:
            user_input = input("\n请输入您的需求（例如：'请帮我审查 test.py 中的代码'）：\n> ")
            if user_input.strip().lower() in ['exit', 'quit']:
                print("感谢使用，再见！")
                break
            
            if not user_input.strip():
                continue

            print("\n正在思考并处理中...")
            response = agent.run(user_input)
            
            print("\n" + "-" * 30 + " Agent 回复 " + "-" * 30)
            print(response)
            print("-" * 72)

        except KeyboardInterrupt:
            print("\n程序已终止。")
            break
        except Exception as e:
            print(f"\n发生错误: {e}")

if __name__ == "__main__":
    main()