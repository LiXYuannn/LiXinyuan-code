#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 1 分钟以内的演示视频（MP4）。

原理：真实跑一遍 `main.py viz` / `main.py run`，把标准输出当作"录屏"素材，
用 Chrome 无头模式把每一帧渲染成 1920x1080 PNG，再用 ffmpeg 编码成 MP4。

依赖（仅本机生成视频时需要，运行本作业项目本身不需要）：
- Google Chrome（用于把 HTML 渲染成 PNG）
- ffmpeg（用于编码 MP4）

用法：
    python scripts/make_demo_video.py                 # 输出 demo.mp4
    python scripts/make_demo_video.py --out docs/d.mp4
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
W, H = 1920, 1080

CSS = """
:root{
  --bg:#0B1420; --panel:#101C2B; --line:#1E2F44;
  --fg:#DCE7F0; --dim:#7C93AA; --green:#5EE0A8; --amber:#F3C65A;
  --red:#FF8F73; --blue:#6FC3FF; --purple:#B79CFF;
}
*{box-sizing:border-box;margin:0;padding:0}
body{width:1920px;height:1080px;background:var(--bg);overflow:hidden;
  font-family:"PingFang SC","Microsoft YaHei",-apple-system,sans-serif;color:var(--fg)}
.stage{width:100%;height:100%;padding:72px 96px;display:flex;flex-direction:column;gap:28px}

/* ---------- 标题卡 ---------- */
.center{justify-content:center;align-items:center;text-align:center}
.big{font-size:96px;font-weight:800;letter-spacing:-2px;line-height:1.1}
.sub{font-size:34px;color:var(--dim);margin-top:18px}
.tagrow{display:flex;gap:18px;margin-top:44px}
.tag{background:var(--panel);border:1px solid var(--line);border-radius:999px;
  padding:12px 28px;font-size:24px;color:var(--blue)}
.hint{margin-top:56px;font-size:22px;color:var(--dim)}

/* ---------- 终端 ---------- */
.bar{display:flex;align-items:center;gap:10px;background:var(--panel);
  border:1px solid var(--line);border-bottom:none;border-radius:14px 14px 0 0;
  padding:14px 20px}
.dot{width:14px;height:14px;border-radius:50%}
.r{background:#FF5F57}.y{background:#FEBC2E}.g{background:#28C840}
.path{color:var(--dim);font-size:19px;margin-left:12px;
  font-family:"SF Mono",Menlo,Consolas,monospace}
.term{flex:1;min-height:0;background:#08101A;border:1px solid var(--line);
  border-radius:0 0 14px 14px;padding:26px 30px;overflow:hidden;
  font-family:"SF Mono",Menlo,Consolas,"PingFang SC",monospace;
  font-size:23px;line-height:1.62;white-space:pre-wrap;word-break:break-word}
.caption{flex:0 0 auto;display:flex;align-items:center;gap:16px;
  background:var(--panel);border:1px solid var(--line);border-left:6px solid var(--blue);
  border-radius:12px;padding:20px 28px;font-size:30px;font-weight:600}
.k{color:var(--dim)}
.g{color:var(--green)} .a{color:var(--amber)} .rd{color:var(--red)}
.b{color:var(--blue)} .p{color:var(--purple)} .w{color:#FFFFFF;font-weight:700}

/* ---------- 图 / 列表 ---------- */
.card{flex:1;background:var(--panel);border:1px solid var(--line);
  border-radius:16px;display:flex;align-items:center;justify-content:center;padding:24px}
.card svg{max-width:100%;max-height:100%}
h2{font-size:44px;font-weight:800}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:22px;flex:1}
.item{background:var(--panel);border:1px solid var(--line);border-radius:14px;
  padding:26px 30px}
.item .t{font-size:30px;font-weight:700;margin-bottom:10px}
.item .d{font-size:22px;color:var(--dim);line-height:1.5}
.mono{font-family:"SF Mono",Menlo,Consolas,monospace}
"""

CAPTIONS = {
    "requirements": "① 需求Agent：原始需求 → 需求规格说明书（SRS）",
    "design": "② 设计Agent：SRS → 模块划分 + 接口定义",
    "coding_impl": "③ 并行分支 A：编码Agent 生成实现代码 solution.py",
    "coding_test": "③ 并行分支 B：编码Agent 生成单元测试 test_solution.py",
    "verify": "④ 确定性校验器：语法检查 + 真实执行测试（守门员）",
    "fix": "⑤ 校验失败 → 自动回退到编码Agent 修复",
    "summarize": "⑥ 汇总器：产出交付物清单",
}
PARALLEL_CAPTION = "③ 编码阶段：实现 与 测试 两个分支并行执行"


def sanitize(lines: list[str]) -> list[str]:
    """抹掉视频里不该出现的本机绝对路径，让输出更像在项目根目录下运行。"""
    root = str(ROOT)
    out = []
    for line in lines:
        for raw, shown in (
            (f"{root}/.demo_out", "outputs"),
            (f"{root}/.demo_logs", "logs"),
            (f"{root}/", "./"),
            (root, "."),
        ):
            line = line.replace(raw, shown)
        out.append(line)
    return out


def run_cmd(args: list[str]) -> str:
    """真实执行一条命令并拿到输出（这才是"演示"的可信来源）。"""
    proc = subprocess.run(
        [sys.executable, *args], cwd=str(ROOT), capture_output=True, text=True, timeout=300
    )
    return (proc.stdout or "") + (proc.stderr or "")


def colorize(line: str) -> str:
    """给终端输出上色，让视频更好读。"""
    esc = html.escape(line)
    esc = re.sub(r"(✓ \[[^\]]+\])", r'<span class="g">\1</span>', esc)
    esc = re.sub(r"(✖|失败|未通过)", r'<span class="rd">\1</span>', esc)
    esc = re.sub(r"(⇉ [^\n]*)", r'<span class="b">\1</span>', esc)
    esc = re.sub(r"(→ \[[^\]]+\])", r'<span class="p">\1</span>', esc)
    esc = re.sub(r"(▶ [^\n]*|■ [^\n]*)", r'<span class="w">\1</span>', esc)
    esc = re.sub(r"(↻ [^\n]*)", r'<span class="a">\1</span>', esc)
    esc = re.sub(r"(第 \d+ 次执行…)", r'<span class="k">\1</span>', esc)
    return esc


def frame_page(inner: str, extra_class: str = "") -> str:
    return (
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        f"<style>{CSS}</style></head><body><div class='stage {extra_class}'>{inner}</div>"
        "</body></html>"
    )


def page_title() -> str:
    return frame_page(
        """
        <div class="big">Homework 2 · Simple Workflow MVP</div>
        <div class="sub">Mini SE 流程：需求 → 设计 → 代码　｜　3 Agent 协作的工作流引擎</div>
        <div class="tagrow">
          <div class="tag">顺序执行</div><div class="tag">并行分支</div>
          <div class="tag">条件路由</div><div class="tag">循环修复</div>
          <div class="tag">零第三方依赖</div>
        </div>
        <div class="hint">需求Agent ＋ 设计Agent ＋ 编码Agent　→　自动产出 SRS / 设计文档 / 代码 / 测试</div>
        """,
        "center",
    )


def page_graph(svg: str) -> str:
    return frame_page(
        f"<h2>工作流编排：7 个节点</h2>"
        f"<div class='caption' style='border-left-color:var(--green)'>"
        f"蓝＝Agent 节点　绿＝工具节点　橙＝「校验失败 → 修复 → 重校验」回边</div>"
        f"<div class='card'>{svg}</div>"
    )


TERM_MAX_LINES = 19  # 1080p 下终端面板能完整显示的行数


def page_terminal(lines: list[str], title: str, caption: str) -> str:
    # 模拟真实终端的滚动：只保留最近 N 行，前面用省略号示意
    dropped = 0
    if len(lines) > TERM_MAX_LINES:
        dropped = len(lines) - TERM_MAX_LINES
        lines = lines[-TERM_MAX_LINES:]
    head = f'<span class="k">…（前面 {dropped} 行已滚出视野）</span>\n' if dropped else ""
    body = "\n".join(colorize(l) for l in lines)
    cursor = '<span class="g">▍</span>' if lines else ""
    return frame_page(
        f"<div class='bar'><span class='dot r'></span><span class='dot y'></span>"
        f"<span class='dot g'></span><span class='path'>{html.escape(title)}</span></div>"
        f"<div class='term'>{head}{body}{cursor}</div>"
        f"<div class='caption'>{html.escape(caption)}</div>"
    )


def page_artifacts() -> str:
    items = [
        ("01_requirements.md", "需求规格说明书", "需求Agent"),
        ("02_design.md", "软件设计说明书", "设计Agent"),
        ("solution.py", "可运行的实现代码", "编码Agent"),
        ("test_solution.py", "单元测试（20 条用例）", "编码Agent"),
        ("03_verify_report.md", "语法检查 + 测试执行报告", "代码校验器"),
        ("report.html", "可视化执行报告（流程图/甘特图/消息流）", "引擎"),
    ]
    cards = "".join(
        f"<div class='item'><div class='t mono'>{name}</div>"
        f"<div class='d'>{desc}<br><span class='k'>产出者：{who}</span></div></div>"
        for name, desc, who in items
    )
    return frame_page(
        f"<h2>端到端产物</h2><div class='grid'>{cards}</div>"
        f"<div class='caption' style='border-left-color:var(--green)'>"
        f"一句话需求进，六份交付物出 —— 全程无需人工干预</div>"
    )


def page_end() -> str:
    rows = [
        ("提交物 1 · 代码", "src/ main.py tests/ — 完整源码"),
        ("提交物 2 · 文档", "README.md（使用） + DESIGN.md（设计）"),
        ("提交物 3 · 演示", "本视频（1 分钟以内）"),
        ("备份提交", "打包为「学号姓名.zip」提交到 002Homework2"),
    ]
    cards = "".join(
        f"<div class='item'><div class='t'>{a}</div><div class='d'>{b}</div></div>"
        for a, b in rows
    )
    return frame_page(
        f"<h2>提交物一览</h2><div class='grid'>{cards}</div>"
        f"<div class='caption' style='border-left-color:var(--amber)'>"
        f"感谢观看 · SE2026 Homework 2</div>"
    )


def screenshot(html_path: Path, png_path: Path) -> None:
    subprocess.run(
        [
            CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--force-device-scale-factor=1", f"--window-size={W},{H}",
            f"--screenshot={png_path}", "--virtual-time-budget=3000",
            f"file://{html_path}",
        ],
        check=True, capture_output=True, timeout=120,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="demo.mp4", help="输出视频路径（相对项目根）")
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    if not Path(CHROME).exists():
        print(f"未找到 Chrome：{CHROME}", file=sys.stderr)
        return 2
    if not shutil.which("ffmpeg"):
        print("未找到 ffmpeg，请先 brew install ffmpeg", file=sys.stderr)
        return 2

    print("① 真实运行命令，采集输出…")
    viz_out = run_cmd(["main.py", "viz"]).strip().splitlines()
    # 用 --simulate-bug 演示「校验失败 → 自动修复 → 重新校验」这条回边
    run_out = run_cmd(
        ["main.py", "run", "--sim", "--simulate-bug", "--out", ".demo_out", "--logs", ".demo_logs"]
    ).strip().splitlines()
    # 拓扑那几行在 graph 场景里已经展示过，这里去掉以控制时长
    run_out = [l for l in run_out if not re.match(r"^\s*·", l) and l.strip()]
    run_out = sanitize(run_out)
    svg = (ROOT / "outputs" / "workflow.svg")
    subprocess.run([sys.executable, "main.py", "viz", "--svg", "outputs/workflow.svg"],
                   cwd=str(ROOT), capture_output=True)
    svg_text = svg.read_text(encoding="utf-8") if svg.exists() else ""

    tmp = Path(tempfile.mkdtemp(prefix="demo_frames_"))
    frames: list[tuple[Path, float]] = []

    def add(html_str: str, dur: float) -> None:
        idx = len(frames)
        hp = tmp / f"f{idx:03d}.html"
        pp = tmp / f"f{idx:03d}.png"
        hp.write_text(html_str, encoding="utf-8")
        screenshot(hp, pp)
        frames.append((pp, dur))

    print("② 渲染帧…")
    add(page_title(), 4.0)
    if svg_text:
        add(page_graph(svg_text), 5.0)
    add(page_terminal(viz_out, "python main.py viz",
                      "先看结构：7 个节点的依赖与出边（无需 API Key）"), 4.5)

    # 逐行推进的运行输出（核心演示段）
    shown: list[str] = []
    for line in run_out:
        shown.append(line)
        caption = PARALLEL_CAPTION if "并行执行" in line else ""
        if not caption:
            m = re.search(r"\[([a-z_]+)\]", line)
            caption = CAPTIONS.get(m.group(1), "") if m else ""
        if "工作流结束" in line:
            caption = "⑦ 端到端跑通：修复 1 轮后校验通过"
        add(page_terminal(shown, "python main.py run --sim --simulate-bug",
                          caption or "　"), 0.62)

    add(page_terminal(shown[-14:], "python main.py run --sim --simulate-bug",
                      "产物已落盘：SRS / 设计文档 / 实现 / 测试 / 校验报告 / 清单"), 4.0)
    add(page_artifacts(), 6.0)
    add(page_end(), 5.0)

    print(f"③ 编码 {len(frames)} 帧 → MP4…")
    lst = tmp / "list.txt"
    lines = []
    for p, d in frames:
        lines.append(f"file '{p}'")
        lines.append(f"duration {d}")
    lines.append(f"file '{frames[-1][0]}'")  # concat 需要重复最后一帧
    lst.write_text("\n".join(lines), encoding="utf-8")

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
            "-vf", f"fps={args.fps},scale={W}:{H}:force_original_aspect_ratio=decrease,"
                   f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-movflags", "+faststart", str(out),
        ],
        check=True, capture_output=True, timeout=900,
    )

    duration = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(out)],
        capture_output=True, text=True,
    ).stdout.strip()

    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(ROOT / ".demo_out", ignore_errors=True)
    shutil.rmtree(ROOT / ".demo_logs", ignore_errors=True)

    print(f"✓ 视频已生成：{out}  （{float(duration or 0):.1f}s，"
          f"{out.stat().st_size / 1024 / 1024:.1f} MB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
