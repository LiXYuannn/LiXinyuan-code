# MiniSE-Workflow-MVP

> SE2026 · Homework 2 · Simple Workflow MVP
> **选题方向：Mini SE 流程 —— 需求 → 设计 → 代码**

一个由 **3 个 Agent（需求 / 设计 / 编码）+ 2 个工具节点（校验 / 汇总）** 协作完成的
迷你软件工程工作流。给它一句话需求，它会自动产出需求规格说明书、软件设计说明书、
可运行的实现代码和单元测试，并在测试跑不过时自动打回修复。

---

## 1. 它做了什么

```
需求Agent ──> 设计Agent ──┬──> 编码Agent(实现) ──┐
                          │                      ├──> 代码校验器 ──┬──> 汇总器
                          └──> 编码Agent(测试) ──┘                 │
                                        ▲                          │
                                        └──── 编码Agent(修复) <────┘（失败则回退）
```

控制流覆盖情况：

| 控制流 | 出现位置 |
|--------|----------|
| 顺序执行 | `requirements → design → coding` |
| **并行执行** | `coding_impl` 与 `coding_test` 同时就绪后并发运行 |
| **条件分支** | `verify` 后按校验结果选择 `summarize`（通过）或 `fix`（失败） |
| **循环回退** | `fix → verify` 形成回边，最多 `--max-fix-rounds` 轮 |
| 错误处理 | 节点级重试 + 退避；耗尽后落盘快照，报告标记 `failed` |

一次成功运行会在 `outputs/` 下产出：

| 文件 | 说明 |
|------|------|
| `01_requirements.md` | 需求规格说明书（需求Agent） |
| `02_design.md` | 软件设计说明书（设计Agent） |
| `solution.py` | 实现代码（编码Agent） |
| `test_solution.py` | 单元测试（编码Agent） |
| `03_verify_report.md` | 语法检查 + 测试执行报告（校验器） |
| `00_summary.md` | 交付物清单（汇总器） |
| `report.html` | **可视化执行报告**（流程图 + 甘特图 + 消息流 + 产物） |

---

## 2. 快速开始

### 2.1 环境要求

- Python **3.9+**（实测 3.12）
- **零第三方依赖**：HTTP 调用、`.env` 解析、SVG 渲染全部使用标准库
- 大模型 API **可选**：有就接真实模型，没有也能用内置离线模拟引擎跑通全流程
  （OpenAI / DeepSeek / Moonshot / 通义 / 智谱 / vLLM / Ollama 均支持）

### 2.2 配置（使用真实大模型时才需要）

```bash
cp .env.example .env
# 编辑 .env，填入自己的 API 配置
```

```ini
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

> `LLM_BASE_URL` 若结尾不是 `/v1`、`/v2` 等版本号，程序会自动补 `/v1`。

### 2.3 运行

```bash
# 没有 API Key？用内置离线模拟引擎，零成本跑通全流程（产物完全一样）
python main.py run --sim

# 演示「校验失败 → 自动修复 → 重新校验」这条回边
python main.py run --sim --simulate-bug

# 用内置示例需求（中缀表达式计算器）+ 真实大模型跑通全流程
python main.py run

# 自定义需求
python main.py run --input "实现一个支持撤销的命令行待办事项管理器"

# 从文件读取需求
python main.py run --input-file requirement.txt

# 只做语法检查，不实际执行生成的测试（更快、更安全）
python main.py run --no-exec
```

常用参数：

| 参数 | 默认 | 说明 |
|------|------|------|
| `--max-fix-rounds` | 2 | 校验失败后的最大自动修复轮次 |
| `--workers` | 4 | 并行线程数 |
| `--out` | `outputs` | 产物输出目录 |
| `--logs` | `logs` | 轨迹输出目录 |
| `--no-exec` | 关 | 跳过测试执行，仅语法检查 |
| `--sim` | 关 | 使用内置离线模拟引擎，无需 API Key |
| `--simulate-bug` | 关 | 配合 `--sim`：首轮实现故意留缺陷，用于演示修复回边 |
| `--quiet` | 关 | 减少控制台输出 |

### 2.4 查看工作流结构（不需要 API Key）

```bash
python main.py viz                    # 打印 ASCII 拓扑 + Mermaid
python main.py viz --svg workflow.svg # 额外导出 SVG
```

### 2.5 跑自测（不需要 API Key）

```bash
python tests/test_engine.py
```

11 个用例覆盖：完整链路、并行分支、失败回退循环、产物版本自增、消息总线、
状态快照、图校验、节点失败降级等。

---

## 3. 目录结构

```
MiniSE-Workflow-MVP/
├── main.py                      # CLI 入口（run / viz）
├── README.md                    # 本文件：项目说明与使用
├── DESIGN.md                    # 设计文档：架构、协作机制、扩展方式
├── .env.example                 # 配置模板
├── src/
│   ├── core/                    # 工作流内核（与业务无关的通用引擎）
│   │   ├── message.py           #   Agent 间消息总线
│   │   ├── state.py             #   共享状态（黑板）+ 版本化产物 + 快照
│   │   ├── node.py              #   节点与条件路由抽象
│   │   ├── graph.py             #   工作流图 + 校验 + Mermaid 导出
│   │   ├── engine.py            #   调度器（拓扑/并行/重试/回边）
│   │   ├── tracing.py           #   轨迹落盘 + HTML 可视化报告
│   │   └── viz.py               #   自绘 SVG 流程图（离线可用）
│   ├── llm/                     # 大模型接入层（面向接口，可替换）
│   │   ├── base.py              #   LLMBackend 协议 + 代码块抽取
│   │   ├── config.py            #   配置加载（env / .env）
│   │   └── openai_client.py     #   OpenAI 兼容实现（含重试退避）
│   ├── agents/                  # 三个协作 Agent
│   │   ├── base.py              #   Agent 基类
│   │   ├── requirements_agent.py#   需求Agent
│   │   ├── design_agent.py      #   设计Agent
│   │   └── coding_agent.py      #   编码Agent（实现/测试/修复 三模式）
│   ├── tools/                   # 确定性工具节点
│   │   ├── verifier.py          #   语法检查 + 执行单测
│   │   └── summarizer.py        #   交付物汇总
│   └── workflows/
│       └── mini_se.py           # 流程装配（唯一的"编排代码"）
├── tests/                       # 离线自测（含测试用 LLM 桩）
├── scripts/
│   └── make_demo_video.py       # 生成演示视频（可选，需要 Chrome + ffmpeg）
├── outputs/                     # 运行产物 + report.html
├── outputs_loop/                # 附加证据：--simulate-bug 的修复回边运行产物
└── logs/                        # trace.json
```

---

## 4. 设计要点速览

- **Agent 之间不直接调用**：全部通过 `MessageBus` 收发消息 + 共享黑板交换数据，
  消息体只放摘要和引用键，不塞大段代码。
- **大模型输出不能自证正确**：所以流水线里放了一个确定性的"守门员"
  （`CodeVerifier`），用 `ast` 语法检查 + `subprocess` 真实执行测试来判定，
  判定结果写回黑板驱动条件路由。
- **引擎与业务解耦**：`src/core` 完全不知道"需求/设计/代码"这些概念，
  换一个业务流程只需改 `src/workflows/` 里的装配代码。

详见 [DESIGN.md](./DESIGN.md)。

---

## 5. 常见问题

**Q：报 `[配置错误] 未检测到 LLM_API_KEY`？**
A：在项目根目录创建 `.env`（可复制 `.env.example`），或直接设置环境变量 `LLM_API_KEY`。
   如果暂时没有 Key，用 `python main.py run --sim` 离线跑通全流程，不消耗 token。

**Q：`--sim` 模式跑出来的东西是"假的"吗？**
A：只替换了"大模型回复"这一段。引擎的调度、并行、条件分支、循环回退，
   以及代码落盘与真实执行测试，全部照常发生 —— 这也是 `tests/` 里
   11 个自测用例能离线验证内核逻辑的原因。

**Q：生成的测试跑不过，一直修复？**
A：属于预期行为。修复超过 `--max-fix-rounds` 轮会自动放弃并进入汇总，
`03_verify_report.md` 里能看到最后一次的失败信息。可调大轮次或换更强的模型。

**Q：`verify` 阶段会执行大模型生成的代码吗？**
A：默认会，但在 `tempfile` 临时目录中以子进程执行，带超时（默认 60s）。
如不希望执行任何生成代码，加 `--no-exec` 即可只做语法检查。

**Q：可以换成别的大模型吗？**
A：可以，只要是 OpenAI 兼容的 `/chat/completions` 接口，改 `.env` 即可，无需改代码。

---

## 6. 提交物清单

| 提交物 | 内容 |
|--------|------|
| 代码 | 本仓库全部源码（`src/`、`main.py`、`tests/`） |
| 文档 | `README.md`（使用说明）+ `DESIGN.md`（设计文档） |
| 演示视频 | 1 分钟以内，演示完整流程运行与产物生成 |
| 备份 | 以上内容打包为 `学号姓名.zip` |
