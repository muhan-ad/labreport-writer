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


def compose(script_dir: str, data: dict) -> dict:
    """按 LAB_VARIANTS 选择组合各章节文本。

    返回 {章节名: 渲染后文本}；仅包含被选中的章节。
    无 variants.json 或 LAB_VARIANTS 未给出该章节选择时，该章节不会出现在结果中。
    """
    variants = load_variants(script_dir)
    if not variants:
        return {}
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
    return out


def variants_summary(script_dir: str) -> dict:
    """返回 {章节名: 变体数}，供应用展示变体库是否存在及规模。"""
    v = load_variants(script_dir)
    if not v:
        return {}
    return {section: len(texts) for section, texts in v.items()}
