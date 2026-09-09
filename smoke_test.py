# -*- coding: utf-8 -*-
"""全实验回归冒烟（静态、不启动 Word）。

对每个实验检查：
  - generate.py 语法（ast.parse）
  - schema.json + data.json 校验（复用 validate_schema.validate）：missing / invalid
  - variants.json：每节条数、每条 `$` 成对、每个 %%DATA:key 是否存在于 _compute 返回字典键
  - rag/原理.md 是否存在
只读项目文件、打印结果表，不写任何文件、不启动 Word。
"""
import ast
import json
import os
import re
import sys

ROOT = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "物理实验", "实验脚本")
sys.path.insert(0, ROOT)
from validate_schema import validate

DATA_KEY_RE = re.compile(r"%%DATA:([^:]+):")


def compute_return_keys(src):
    """返回 ('syntax',None) | ('ok',keys:set) | ('no_compute',None)。"""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return ("syntax", str(e))
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_compute"), None)
    if fn is None:
        return ("no_compute", None)
    for n in ast.walk(fn):
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict):
            keys = set()
            for k in n.value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
            return ("ok", keys)
    return ("no_compute", None)


def main():
    rows = []
    for d in sorted(os.listdir(BASE)):
        ed = os.path.join(BASE, d)
        if not os.path.isdir(ed) or d == "common" or d.startswith("."):
            continue
        gp = os.path.join(ed, "generate.py")
        if not os.path.isfile(gp):
            continue
        issues = []
        src = open(gp, encoding="utf-8-sig").read()
        st, keys = compute_return_keys(src)
        if st == "syntax":
            issues.append("语法错误:" + keys)

        # schema/data 校验
        miss = "?"
        try:
            sch = json.load(open(os.path.join(ed, "schema.json"), encoding="utf-8"))
            dat = json.load(open(os.path.join(ed, "data.json"), encoding="utf-8"))
            v = validate(sch, dat)
            miss = len(v["missing"])
            if v["invalid"]:
                issues.append(f"invalid:{[i['key'] for i in v['invalid']]}")
        except Exception as e:
            issues.append(f"schema/data:{e}")

        # variants 校验
        vinfo = "无"
        vp = os.path.join(ed, "variants.json")
        if os.path.isfile(vp):
            try:
                var = json.load(open(vp, encoding="utf-8"))
                vinfo = "×".join(str(len(t)) for t in var.values())
                for sec, texts in var.items():
                    for i, t in enumerate(texts):
                        if t.count("$") % 2:
                            issues.append(f"{sec}[{i}]$不成对")
                        if st == "ok":
                            for m in DATA_KEY_RE.finditer(t):
                                if m.group(1) not in keys:
                                    issues.append(f"{sec}[{i}]占位符键'{m.group(1)}'不在_compute")
            except Exception as e:
                issues.append(f"variants:{e}")

        # rag
        if not os.path.isfile(os.path.join(ed, "rag", "原理.md")):
            issues.append("缺rag/原理.md")

        rows.append((d, miss, vinfo, issues))

    print(f"{'状态':<4}{'实验':<30}{'未填':>4}{' 变体':>8}  问题")
    print("-" * 90)
    bad = 0
    for d, miss, vinfo, iss in rows:
        flag = "  " if not iss else "✗ "
        if iss:
            bad += 1
        print(f"{flag}{d:<30}{str(miss):>4} {str(vinfo):>8}  {('; '.join(iss)) if iss else 'OK'}")
    print("-" * 90)
    print(f"共 {len(rows)} 个实验，异常 {bad} 个")


if __name__ == "__main__":
    main()