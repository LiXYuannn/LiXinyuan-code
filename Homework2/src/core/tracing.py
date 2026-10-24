# -*- coding: utf-8 -*-
"""执行追踪与可视化报告生成。

产出三样东西：
1. trace.json      —— 完整机器可读轨迹（可用于回放 / 回归测试）
2. report.html     —— 人读的可视化报告（流程图 + 甘特图 + 消息流 + 产物）
3. 交付物文件      —— 把黑板上的产物落盘成真实文件
"""

from __future__ import annotations

import html
import json
import time
from pathlib import Path

from .graph import WorkflowGraph
from .state import WorkflowState
from .viz import render_svg

CSS = """
:root{--bg:#0F1B2A;--card:#16283C;--line:#24384F;--fg:#E8F1F8;--muted:#93A7BC;
--ok:#2A9D8F;--bad:#E76F51;--accent:#4EA8DE;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font-family:-apple-system,"PingFang SC","Microsoft YaHei",Segoe UI,sans-serif;}
.wrap{max-width:1080px;margin:0 auto;padding:32px 24px 64px}
h1{font-size:28px;margin:0 0 6px}
h2{font-size:19px;margin:36px 0 14px;padding-left:10px;border-left:4px solid var(--accent)}
.sub{color:var(--muted);font-size:13px;margin-bottom:8px}
.kpis{display:flex;gap:14px;flex-wrap:wrap;margin:18px 0 8px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:14px 18px;min-width:132px}
.kpi .v{font-size:24px;font-weight:700}
.kpi .k{font-size:12px;color:var(--muted);margin-top:2px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:18px;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;
vertical-align:top}
th{color:var(--muted);font-weight:600}
.badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px}
.ok{background:rgba(42,157,143,.18);color:#7EE0D1}
.bad{background:rgba(231,111,81,.18);color:#FFA98F}
.warn{background:rgba(230,168,23,.18);color:#F3C65A}
.bar{height:16px;border-radius:6px;background:var(--ok);display:inline-block}
.track{background:rgba(255,255,255,.04);border-radius:6px;flex:1;min-width:160px;
height:16px;position:relative;overflow:hidden}
.track .bar{position:absolute;top:0}
details{margin:10px 0}
summary{cursor:pointer;color:var(--accent);font-size:13px}
pre{background:#0B1420;border:1px solid var(--line);border-radius:8px;padding:12px;
overflow:auto;font-size:12px;line-height:1.55}
code{font-family:Menlo,Consolas,monospace}
.msg{border-left:3px solid var(--accent);padding:6px 0 6px 12px;margin:8px 0;
font-size:13px}
.msg .meta{color:var(--muted);font-size:11px}
footer{margin-top:40px;color:var(--muted);font-size:12px;text-align:center}
"""


def write_trace(state: WorkflowState, report, path: str | Path) -> Path:
    """落盘完整执行轨迹。"""
    payload = {
        "report": report.to_dict(),
        "state": state.snapshot(),
        "generated_at": time.time(),
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def write_artifacts(state: WorkflowState, out_dir: str | Path) -> list[Path]:
    """把黑板上的产物写成真实文件。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for key, art in state.artifacts().items():
        p = out / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(art.content, encoding="utf-8")
        written.append(p)
    return written


def render_report(
    graph: WorkflowGraph, state: WorkflowState, report, path: str | Path
) -> Path:
    """生成可视化 HTML 报告。"""
    esc = html.escape
    total = report.duration or 0.001
    t0 = min((r.started_at or time.time()) for r in state.runs()) if state.runs() else 0

    # --- KPI ---
    n_ok = len([r for r in state.runs() if r.status == "success"])
    n_fail = len([r for r in state.runs() if r.status == "failed"])
    kpis = [
        ("流程状态", esc(report.status.upper()), "ok" if report.status == "success" else "bad"),
        ("总耗时", f"{report.duration}s", "ok"),
        ("节点执行", f"{n_ok} 成功 / {n_fail} 失败", "ok" if n_fail == 0 else "bad"),
        ("Agent 消息", str(len(state.bus.history())), "warn"),
        ("产物件", str(len(state.artifacts())), "warn"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="v">{v}</div><div class="k">{k}</div></div>'
        for k, v, _ in kpis
    )

    # --- 甘特图 ---
    gantt = []
    for r in state.runs():
        start = (r.started_at or t0) - t0
        left = (start / total) * 100
        width = max((r.duration / total) * 100, 1.2)
        cls = "ok" if r.status == "success" else "bad"
        gantt.append(
            f"<tr><td><code>{esc(r.name)}</code></td><td>#{r.attempt}</td>"
            f'<td style="width:52%"><div class="track">'
            f'<span class="bar" style="left:{left:.1f}%;width:{width:.1f}%"></span>'
            f"</div></td>"
            f"<td>{r.duration}s</td>"
            f'<td><span class="badge {cls}">{esc(r.status)}</span></td>'
            f"<td>{esc((r.summary or '')[:70])}</td></tr>"
        )

    # --- 消息流 ---
    msgs = []
    for m in state.bus.history():
        msgs.append(
            f'<div class="msg"><div class="meta">#{m.seq} · {m.sender} → {m.receiver}'
            f" · {esc(m.msg_type)}</div>{esc(m.payload[:300])}</div>"
        )

    # --- 产物 ---
    arts = []
    for key, art in sorted(state.artifacts().items()):
        arts.append(
            f"<details><summary>{esc(key)} — v{art.version} · by {esc(art.producer)} "
            f"· {len(art.content)} 字符</summary>"
            f"<pre><code>{esc(art.content[:4000])}</code></pre></details>"
        )

    body = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{esc(graph.name)} · 执行报告</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>{esc(graph.name)} · 执行报告</h1>
<div class="sub">Mini Workflow MVP · 需求 → 设计 → 代码 · 生成于 {
    time.strftime('%Y-%m-%d %H:%M:%S')}</div>
<div class="kpis">{kpi_html}</div>

<h2>1. 工作流编排图</h2>
<div class="card">{render_svg(graph)}</div>
<div class="sub" style="margin-top:10px">蓝=Agent 节点，绿=工具/校验节点；
橙色回边表示「校验失败 → 修复 → 重新校验」的循环。</div>

<h2>2. 执行时间线</h2>
<div class="card"><table>
<tr><th>节点</th><th>轮次</th><th>时间轴</th><th>耗时</th><th>状态</th><th>摘要</th></tr>
{''.join(gantt)}
</table></div>

<h2>3. Agent 消息流（{len(state.bus.history())} 条）</h2>
<div class="card">{''.join(msgs) or '<div class="sub">无消息</div>'}</div>

<h2>4. 共享状态产物（Blackboard）</h2>
<div class="card">{''.join(arts) or '<div class="sub">无产物</div>'}</div>

<footer>Generated by MiniSE-Workflow-MVP · WorkflowEngine</footer>
</div></body></html>"""

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p
