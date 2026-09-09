# -*- coding: utf-8 -*-
"""schema 校验器（方式三）：检查各实验 data.json 是否符合 schema.json。

替代旧的 check_data.py 启发式校验。校验规则来自 schema 的 type/required/length/rows/cols。

本脚本不接受外部路径参数：遍历项目内固定的 物理实验/实验脚本 目录，
对每个含 schema.json 的实验校验，结果以 JSON 打印到 stdout。

输出：
{
  "<实验名>": {"ok": true, "missing": [{"key","label"}...], "invalid": [{"key","label","reason"}...]}
}

用法：
    python validate_schema.py            # 校验所有已迁移（有 schema.json）的实验
"""
import json
import os

PROJECT_ROOT = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(PROJECT_ROOT, "物理实验", "实验脚本")


def _load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate(schema, data):
    missing, invalid = [], []
    for group in schema.get("groups", []):
        for fld in group.get("fields", []):
            key = fld.get("key")
            label = fld.get("label", key)
            typ = fld.get("type", "number")
            required = fld.get("required", False)
            v = data.get(key)

            # 必填检查
            if required:
                if v is None:
                    missing.append({"key": key, "label": label})
                    continue
                if typ == "array" and (not isinstance(v, list) or any(x is None for x in v)):
                    missing.append({"key": key, "label": label})
                    continue
                if typ == "matrix" and (not isinstance(v, list)
                        or any(x is None for row in v for x in row)):
                    missing.append({"key": key, "label": label})
                    continue

            if v is None:
                continue

            # 类型 / 长度检查
            if typ == "number":
                if not _is_num(v):
                    invalid.append({"key": key, "label": label, "reason": "应为数值"})
            elif typ == "array":
                if not isinstance(v, list):
                    invalid.append({"key": key, "label": label, "reason": "应为数组"})
                elif "length" in fld and len(v) != fld["length"]:
                    invalid.append({"key": key, "label": label,
                                    "reason": f"长度应为 {fld['length']}"})
                elif any(x is not None and not _is_num(x) for x in v):
                    invalid.append({"key": key, "label": label, "reason": "含非数值"})
            elif typ == "matrix":
                if not isinstance(v, list):
                    invalid.append({"key": key, "label": label, "reason": "应为矩阵"})
                else:
                    rows, cols = fld.get("rows"), fld.get("cols")
                    if rows is not None and len(v) != rows:
                        invalid.append({"key": key, "label": label,
                                        "reason": f"行数应为 {rows}"})
                    elif cols is not None and any(
                            not isinstance(r, list) or len(r) != cols for r in v):
                        invalid.append({"key": key, "label": label,
                                        "reason": f"列数应为 {cols}"})
                    elif any(x is not None and not _is_num(x)
                             for r in v if isinstance(r, list) for x in r):
                        invalid.append({"key": key, "label": label, "reason": "含非数值"})
    return {"ok": True, "missing": missing, "invalid": invalid}


def main():
    exp_dirs = sorted(
        os.path.join(BASE, d) for d in os.listdir(BASE)
        if os.path.isdir(os.path.join(BASE, d)) and d != "common" and not d.startswith(".")
    )
    results = {}
    for d in exp_dirs:
        schema = _load_json(os.path.join(d, "schema.json"))
        if schema is None:
            continue  # 未迁移（无 schema.json）的实验跳过
        data = _load_json(os.path.join(d, "data.json")) or {}
        results[os.path.basename(d)] = validate(schema, data)
    print(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()