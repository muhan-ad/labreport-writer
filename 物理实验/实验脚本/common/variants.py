# -*- coding: utf-8 -*-
"""变体组合模块。

同一个实验的报告/论文可以由不同"变体"章节组合而成：
- 实验目录下放置 variants.json：{章节名: [变体1文本, 变体2文本, 变体3文本, ...]}
- 应用通过环境变量 LAB_VARIANTS 传入本次组合选择：{"章节名": 变体序号, ...}
- 文本支持 $...$ 内联公式（由 DocxReportWriter.add_paragraph_rich 渲染）
- 文本支持数据占位符 %%DATA:<key>:<format>%%，组合时从计算结果注入
  （format 为 printf 风格，如 %%DATA:Y:%.2f%%）

无 variants.json 或未提供选择时，compose() 返回空 dict，报告保持原有行为。
"""

import json
import os
import re

DATA_PATTERN = re.compile(r"%%DATA:([^:]+):(.+?)%%")


def load_variants(script_dir: str):
    """读取实验目录下的 variants.json；不存在时返回 None。"""
    p = os.path.join(script_dir, "variants.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def get_variant_choices():
    """读取环境变量 LAB_VARIANTS 中的组合选择（JSON dict）。未提供返回 None。"""
    raw = os.environ.get("LAB_VARIANTS", "").strip()
    if not raw:
        return None
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def render_variant(text: str, data: dict) -> str:
    """将 %%DATA:<key>:<format>%% 占位符替换为计算结果中的数值。"""

    def repl(m):
        key, fmt = m.group(1), m.group(2)
        val = data.get(key)
        if val is None:
            return m.group(0)  # 数据缺失时保留占位符，便于排查
        try:
            return fmt % val
        except Exception:
            return str(val)

    return DATA_PATTERN.sub(repl, text)


def get_polish_overrides():
    """读取环境变量 LAB_POLISH 中的润色导入（JSON {章节名: Markdown 文本}）。"""
    raw = os.environ.get("LAB_POLISH", "").strip()
    if not raw:
        return None
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


_HEADING_RE = re.compile(r"(?m)^[ \t]*#{1,6}[ \t]*")
_BULLET_RE = re.compile(r"(?m)^[ \t]*[-*+][ \t]+")
_HR_RE = re.compile(r"(?m)^[ \t]*[-=*_]{3,}[ \t]*$")
_TABLE_SEP_CELL = re.compile(r":?-{2,}:?")

SECTIONS_MARKER = ".LAB_SECTIONS_JSON:"


def normalize_polish_md(text):
    """把 AI 输出的 Markdown 预处理成报告富文本（保留 $...$ 与 $$...$$ 公式）。

    处理：markdown 表格降级为分号文本行、\\( \\) 与 \\[ \\] 归一为 $ 与 $$、
    逐行剥离标题井号/列表符/分割线/引用符、去粗斜体与行内代码标记。
    """
    lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("|") or s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(not c or _TABLE_SEP_CELL.fullmatch(c) for c in cells):
                continue  # 表头分隔行整行丢弃
            ln = "；".join(c for c in cells if c)
        lines.append(ln)
    text = "\n".join(lines)
    text = text.replace(r"\[", "$$").replace(r"\]", "$$")
    text = text.replace(r"\(", "$").replace(r"\)", "$")
    text = _HEADING_RE.sub("", text)
    text = _BULLET_RE.sub("", text)
    text = _HR_RE.sub("", text)
    text = re.sub(r"(?m)^[ \t]*>[ \t]?", "", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<![\w$\\])\*([^*\n]+)\*(?![\w$])", r"\1", text)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def compose(script_dir: str, data: dict) -> dict:
    """按 LAB_VARIANTS 组合各章节文本，并应用 LAB_POLISH 润色导入覆盖。

    返回 {章节名: 渲染后文本}。LAB_POLISH 中提供的章节以润色文本覆盖变体
    （Markdown 先归一为报告富文本，%%DATA:%% 占位符对两者同样生效）。
    同时向 stdout 打印一行 SECTIONS_MARKER + JSON，由应用侧捕获并持久化为
    章节缓存（.lab_sections.json），供"按章节润色/导入重生成"读取原文。
    """
    variants = load_variants(script_dir) or {}
    choices = get_variant_choices()
    out = {}
    for section, texts in variants.items():
        idx = -1
        if choices and section in choices:
            try:
                idx = int(choices[section])
            except Exception:
                idx = -1
        if 0 <= idx < len(texts):
            out[section] = render_variant(texts[idx], data)
    for section, md in (get_polish_overrides() or {}).items():
        if not isinstance(md, str) or not md.strip():
            continue
        out[section] = render_variant(normalize_polish_md(md), data)
    if out:
        print(SECTIONS_MARKER + json.dumps(out, ensure_ascii=False), flush=True)
    return out


def variants_summary(script_dir: str) -> dict:
    """返回 {章节名: 变体数}，供应用展示变体库是否存在及规模。"""
    v = load_variants(script_dir)
    if not v:
        return {}
    return {section: len(texts) for section, texts in v.items()}
