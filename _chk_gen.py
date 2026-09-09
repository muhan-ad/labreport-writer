# -*- coding: utf-8 -*-
import io, re, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for exp in ["三线摆（刚体转动惯量）", "重力加速度的测量（复摆）", "单缝衍射（衍射光强分布）"]:
    src = io.open(
        rf"E:\agent-project\labreport-writer\物理实验\实验脚本\{exp}\generate.py",
        encoding="utf-8-sig").read()
    print(f"===== {exp} =====")
    for m in re.finditer(r"(ROW_\w+|COL_\w+)\s*=\s*([0-9]+|\"[A-Z]\"|'[A-Z]')", src):
        print(" 常量:", m.group(1), "=", m.group(2))
    # 读取调用与所在行
    for m in re.finditer(r"read_(?:cell|row)\(([^)]{0,50})\)", src):
        line_no = src[:m.start()].count("\n") + 1
        print(f"  第{line_no}行: read_({m.group(1)[:50]})")
