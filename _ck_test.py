# -*- coding: utf-8 -*-
import subprocess, json, io, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PY = r"E:\agent-project\labreport-writer\python-runtime\python.exe"
ROOT = r"E:\agent-project\labreport-writer"
BASE = r"E:\agent-project\labreport-writer\物理实验\实验脚本"

for exp in ["长度与体积的测量", "拉伸法测量杨氏弹性模量", "RLC电路的稳态特性研究实验", "霍尔效应测量磁场", "静电场的模拟", "用冲击法测量螺旋管磁场分布实验"]:
    r = subprocess.run(
        [PY, "check_data.py", BASE + "\\" + exp, ROOT],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    try:
        d = json.loads(r.stdout)
        print(f"【{exp}】 missing={len(d['missing'])} invalid={len(d['invalid'])}")
        if d["missing"]:
            print("  missing:", [x["cell"] for x in d["missing"]][:12])
        if d["invalid"]:
            print("  invalid:", [x["cell"] for x in d["invalid"]][:12])
    except Exception as e:
        print(f"【{exp}】 解析失败: {r.stdout[:200]} err={e}")
