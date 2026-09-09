# -*- coding: utf-8 -*-
"""电表的改装与校准 — 数据处理脚本（从公众号"对策府库"物理实验计算器提取）。

参考源：
  - 数据录入结构：XDU物理实验小助手（experiment-helper.wizzstudio.com）实验定义 JSON
    （变量 R_g / I_x / I_s / U_x / U_s，mathjs 表达式 R_g_a/9、10000-R_g_a、I_s-I_x、U_s-U_x）
  - 文件范式：物理实验/实验脚本/<实验名>/generate.py（schema.json + data.json + 计算 + Word 报告）
"""

import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import *
from common.docx_report import DocxReportWriter
from common.data_io import load_data
from common.variants import compose

# ── 实验参数（教材口径） ──
# 电流表改装：表头量程扩大 10 倍 → 分流电阻 R_s = R_g / 9
CURRENT_RANGE_MULT = 9
# 电压表改装：改装为 10V 量程，串联分压电阻使总内阻 10 kΩ
VOLT_RH_TOTAL = 10000.0        # Ω
# R_g 测量（数字万用表）B 类不确定度简化：不编造仪表规格，仅统计 A 类 + 说明
T_FACTOR_RG = 1.32             # t 因子 (n=3, df=2, P=0.683)


# （方式三：_create_template 已移除，数据真相为 data.json）


def _compute(data: dict) -> dict:
    """从 data.json 数据计算全部结果（与计算器 mathjs 逻辑一致）。"""
    # 1. 表头内阻（过滤未填）
    rg = [float(v) for v in data.get("rg", []) if v is not None]
    rg_mean = mean(rg)

    # 2. 电流校正（过滤未填）
    i_x = [float(v) for v in data.get("i_x", []) if v is not None]
    i_s = [float(v) for v in data.get("i_s", []) if v is not None]
    i_corr = [s - x for s, x in zip(i_s, i_x)]

    # 3. 电压校正（过滤未填）
    u_x = [float(v) for v in data.get("u_x", []) if v is not None]
    u_s = [float(v) for v in data.get("u_s", []) if v is not None]
    u_corr = [s - x for s, x in zip(u_s, u_x)]

    # 4. 计算值（计算器表达式）
    r_s_calc = rg_mean / CURRENT_RANGE_MULT          # R_g_a / 9
    r_h_calc = VOLT_RH_TOTAL - rg_mean               # 10000 - R_g_a

    # 5. 不确定度（统计口径，公式自动算）
    n = len(rg)
    u_A_rg = T_FACTOR_RG * std_dev(rg) / math.sqrt(n)   # A 类（t 因子修正）
    u_r_s = r_s_calc * (u_A_rg / rg_mean)               # R_s 相对传递
    u_r_h = u_A_rg                                      # R_h = const - R_g → 不确定度同 R_g

    return {
        "rg": rg, "rg_mean": rg_mean, "u_A_rg": u_A_rg,
        "r_s_calc": r_s_calc, "u_r_s": u_r_s,
        "r_h_calc": r_h_calc, "u_r_h": u_r_h,
        "i_x": i_x, "i_s": i_s, "i_corr": i_corr,
        "u_x": u_x, "u_s": u_s, "u_corr": u_corr,
        "max_i_corr": max(abs(c) for c in i_corr),
        "max_u_corr": max(abs(c) for c in u_corr),
    }


def _print_results(r: dict):
    """控制台打印计算结果（便于复现核对）。"""
    print("=" * 56)
    print("电表的改装与校准 — 计算结果")
    print("=" * 56)
    print(f"R_g 三次测量: {r['rg']}")
    print(f"R_g 平均值: {r['rg_mean']:.3f} Ω   (u_A = {r['u_A_rg']:.3f} Ω)")
    print(f"电流表分流电阻 R_s = R_g_a / 9 = {r['r_s_calc']:.3f} Ω")
    print(f"电压表分压电阻 R_h = 10000 - R_g_a = {r['r_h_calc']:.3f} Ω")
    print(f"\n电流校正 (I_x / I_s / 修正值):")
    for a, b, c in zip(r["i_x"], r["i_s"], r["i_corr"]):
        print(f"  {a:.1f} / {b:.3f} / {c:+.3f} mA")
    print(f"  最大修正值: {r['max_i_corr']:.3f} mA")
    print(f"\n电压校正 (U_x / U_s / 修正值):")
    for a, b, c in zip(r["u_x"], r["u_s"], r["u_corr"]):
        print(f"  {a:.1f} / {b:.3f} / {c:+.3f} V")
    print(f"  最大修正值: {r['max_u_corr']:.3f} V")
    print("=" * 56)


def _generate_docx(data: dict, output_path: str):
    """读取 data.json 数据，计算并生成 Word 实验报告。"""
    # 校验必填数据（required 字段为 null 或 array 含 null → 缺失）
    missing = []
    for k in ("rg", "i_x", "i_s", "u_x", "u_s"):
        v = data.get(k)
        if v is None:
            missing.append(k)
        elif isinstance(v, list) and any(x is None for x in v):
            missing.append(k)
    if missing:
        print("以下必填数据未填写，请补齐后重新运行：")
        for m in missing:
            print(f"  - {m}")
        return

    r = _compute(data)
    _print_results(r)
    variants = compose(SCRIPT_DIR, r)

    doc = DocxReportWriter(output_path)

    # ── 零、实验标题 ──
    doc.add_title("电表的改装与校准")
    doc.add_student_info()

    # ── 变体章节：实验原理 / 实验方法（置于原始数据之前） ──
    if "实验原理" in variants:
        doc.add_heading("实验原理", level=1)
        doc.add_paragraph_rich(variants["实验原理"])
    if "实验方法" in variants:
        doc.add_heading("实验方法", level=1)
        doc.add_paragraph_rich(variants["实验方法"])

    # ── 一、原始数据提交 ──
    doc.add_heading("一、原始数据提交（拍照上传）", level=1)
    doc.add_paragraph("请在下方粘贴原始数据记录照片。")

    # ── 二、数据处理 ──
    doc.add_heading("二、数据处理", level=1)

    # 1. 表头内阻
    doc.add_heading("1. 表头内阻测量", level=2)
    doc.add_paragraph("")
    doc.add_run("用数字万用表对表头内阻进行 3 次测量：")
    for i, v in enumerate(r["rg"]):
        doc.add_run(f"R_g{'' if i == 0 else i + 1} = {v} Ω，")
    doc.add_paragraph("")
    doc.add_paragraph("内阻平均值：")
    doc.add_math(
        r"\bar{R}_g = \frac{1}{3}\sum R_{gi} = "
        + format_number(r["rg_mean"]) + r"\,\mathrm{\Omega}"
    )
    doc.add_paragraph("")
    doc.add_run("A 类不确定度（t 因子修正，n=3, P=0.683）：")
    doc.add_inline_math(f"u_A = {format_number(r['u_A_rg'])} Ω")

    # 2. 电流表改装
    doc.add_heading("2. 电流表改装（量程扩大 10 倍）", level=2)
    doc.add_paragraph("")
    doc.add_run("改装为 1 mA 量程，需并联分流电阻，由 ")
    doc.add_inline_math(r"R_s = \bar{R}_g / (n-1)")
    doc.add_run(" 得（n=10）：")
    doc.add_math(
        r"R_s = \frac{\bar{R}_g}{9} = "
        + format_number(r["r_s_calc"]) + r"\,\mathrm{\Omega}"
    )

    doc.add_paragraph("电流表校正数据（标准表 I_s 与改装表 I_x 对照）：")
    rows = []
    for a, b, c in zip(r["i_x"], r["i_s"], r["i_corr"]):
        rows.append([f"{a:.1f}", f"{b:.3f}", f"{c:+.3f}"])
    doc.add_table(["$I_x$ / mA", "$I_s$ / mA", "$I_s-I_x$ / mA"], rows,
                  col_widths=[3.0, 3.0, 3.5])

    # 3. 电压表改装
    doc.add_heading("3. 电压表改装（量程 10 V）", level=2)
    doc.add_paragraph("")
    doc.add_run("改装为 10 V 量程，需串联分压电阻使总内阻为 10 kΩ：")
    doc.add_math(
        r"R_h = 10000 - \bar{R}_g = "
        + format_number(r["r_h_calc"]) + r"\,\mathrm{\Omega}"
    )

    doc.add_paragraph("电压表校正数据（标准表 U_s 与改装表 U_x 对照）：")
    rows = []
    for a, b, c in zip(r["u_x"], r["u_s"], r["u_corr"]):
        rows.append([f"{a:.1f}", f"{b:.3f}", f"{c:+.3f}"])
    doc.add_table(["$U_x$ / V", "$U_s$ / V", "$U_s-U_x$ / V"], rows,
                  col_widths=[3.0, 3.0, 3.5])

    # ── 三、实验结果分析 ──
    doc.add_heading("三、实验结果分析", level=1)
    doc.add_paragraph("")
    doc.add_run("电流表校正最大修正值 ")
    doc.add_inline_math(f"\\Delta I_{{max}} = {format_number(r['max_i_corr'])} mA")
    doc.add_run("，电压表校正最大修正值 ")
    doc.add_inline_math(f"\\Delta U_{{max}} = {format_number(r['max_u_corr'])} V")
    doc.add_run("。若最大修正值不超过量程的 0.5%，则改装表达到 0.5 级精度。")

    doc.add_paragraph("")
    doc.add_run("误差来源分析：")
    doc.add_run("（1）表头内阻测量的随机误差，由 3 次测量的统计涨落体现（")
    doc.add_inline_math(f"u_A = {format_number(r['u_A_rg'])} Ω")
    doc.add_run("），并传递给分流/分压电阻的标称值；")
    doc.add_run("（2）标准表本身的等级误差与读数估读误差；")
    doc.add_run("（3）分流、分压电阻的阻值偏差与温度漂移；")
    doc.add_run("（4）改装表刻度非线性导致的读数误差。")

    # ── 变体章节：误差分析（置于结果分析之后、思考题之前） ──
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])

    # ── 四、思考题 ──
    doc.add_heading("四、思考题", level=1)

    doc.add_heading("1. 为什么电流表改装要用并联电阻？", level=2)
    doc.add_paragraph(
        "答：电流表本质是微安表头，内阻较大，只能通过很小的电流。"
        "要扩大电流量程，必须并联一个分流电阻，使大部分被测电流从分流电阻流过，"
        "表头只流过与其内阻成反比的份额，从而保证表头工作在额定电流范围内。"
    )

    doc.add_heading("2. 电压表改装为什么串联大电阻？", level=2)
    doc.add_paragraph(
        "答：电压表要求内阻很大，测量时几乎不分流被测电路电流。"
        "扩大量程时需串联分压电阻，使绝大部分电压降落在分压电阻上，"
        "表头只承担额定电压降，同时使改装表的总内阻按量程成比例增大（欧姆/伏特）。"
    )

    doc.add_heading("3. 校正时发现改装表读数普遍偏大，说明什么？", level=2)
    doc.add_paragraph(
        "答：读数普遍偏大说明表头支路电流偏大，即分流/分压电阻取值偏大（或表头内阻标定偏小），"
        "导致流过表头的电流超过额定值。应适当减小分流电阻（电流表）或减小分压电阻（电压表），"
        "并重新校正，使各点修正值尽量减小且正负对称。"
    )

    # ── 变体章节：实验结论（置于思考题之后） ──
    if "实验结论" in variants:
        doc.add_heading("实验结论", level=1)
        doc.add_paragraph_rich(variants["实验结论"])

    # ── 保存 ──
    doc.save()
    doc.close()


def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "电表的改装与校准.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    _generate_docx(data, DOCX_FILE)
    print(f"报告已生成: {DOCX_FILE}")


if __name__ == "__main__":
    main()
