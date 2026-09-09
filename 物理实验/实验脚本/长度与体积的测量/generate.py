# -*- coding: utf-8 -*-
"""实验1 长度与体积的测量 — 数据处理脚本。

教材来源：《大学物理实验》吴兴林等（ISBN 978-7-5606-6654-9）实验1。
仪器：米尺、游标卡尺（50 分度，分度值 0.02 mm）、螺旋测微计（一级，量程 25 mm，
  分度值 0.01 mm，0~100 mm 示值误差 ±0.004 mm）、15J 测量显微镜（X/Y 测微器分度 0.01 mm）。

数据处理要求（教材）：
  (1) 计算板长、板宽及其测量不确定度
  (2) 计算孔径及其测量不确定度
  (3) 计算金属板厚度及其测量不确定度
  (4) 计算缝长、缝宽及其测量不确定度
  (5) 计算板体积、圆孔体积、缝体积及其测量不确定度
  (6) 计算金属体体积及其不确定度
体积模型：金属体 = 板 − 圆孔 − 缝（三者均贯穿板厚 d）。
"""

import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import *
from common.docx_report import DocxReportWriter
from common.variants import compose
from common.data_io import load_data

# t 因子（置信概率 0.683，与全项目口径一致）：下标 = 测量次数 n
T_FACTOR = [0, 0, 1.84, 1.32, 1.2, 1.14, 1.11, 1.09, 1.08]
SQRT3 = math.sqrt(3)

# ── 示例数据（计算器 default，量级参照教材表 3-1-6）──
L_DEFAULT = 60.0        # 板长，mm（直尺，1 次）
W_DEFAULT = 40.0        # 板宽，mm（直尺，1 次）
D_DEFAULT = [8.02, 8.00, 8.03, 8.01, 8.02]   # 孔径，mm（游标卡尺，5 次）
D_SHI_DEFAULT = [2.006, 2.004, 2.005, 2.007, 2.006]  # 板厚，mm（千分尺，5 次）
X0_DEFAULT = [10.000, 10.000, 10.001, 10.000, 10.000]  # 缝长起点读数，mm
X1_DEFAULT = [30.014, 30.010, 30.012, 30.013, 30.011]  # 缝长终点读数，mm
Y0_DEFAULT = [12.000, 12.001, 12.000, 12.000, 12.001]  # 缝宽起点读数，mm
Y1_DEFAULT = [13.002, 13.000, 13.001, 13.003, 13.001]  # 缝宽终点读数，mm
D0_DEFAULT = -0.005     # 螺旋测微计零点读数，mm
D0_CARD_DEFAULT = 0.000  # 游标卡尺零点读数，mm

# 仪器误差（教材表 3-1-1/3-1-3/3-1-4 及分度值）
DL_INST = 0.2    # 米尺允许误差，mm（500~1000 mm 档 ±0.20）
DD_INST = 0.02   # 游标卡尺分度值（50 分度），mm
DD_SHI_INST = 0.004  # 一级千分尺 0~100 mm 示值误差，mm
DX_INST = 0.01   # 测量显微镜测微器分度值，mm


def smartlab_ua(data):
    """A 类不确定度：t 因子 × 均值标准误。"""
    n = len(data)
    if n < 2:
        return 0.0
    t = T_FACTOR[n] if n < len(T_FACTOR) else 1.0
    mean_val = sum(data) / n
    variance = sum((x - mean_val) ** 2 for x in data) / ((n - 1) * n)
    return t * math.sqrt(variance)


def smartlab_u(data, inst_err):
    """合成不确定度：A 类（t 因子）+ B 类（均匀分布 /√3）。"""
    ua = smartlab_ua(data)
    return math.sqrt(ua ** 2 + (inst_err / SQRT3) ** 2)


# （方式三：_create_template 已移除，数据真相为 data.json）


def _compute(data: dict) -> dict:
    # 仪器误差
    dl_inst = float(data["dl_inst"])
    dd_inst = float(data["dd_inst"])
    dd_shi_inst = float(data["dd_shi_inst"])
    dx_inst = float(data["dx_inst"])

    # 零点读数（未填按 0 处理）
    d0 = float(data.get("d0") or 0.0)
    d0_card = float(data.get("d0_card") or 0.0)

    # 测量值（数组过滤未填）
    L = float(data["L"])
    W = float(data["W"])
    D = [float(v) for v in (data.get("D") or []) if v is not None]
    d_shi = [float(v) for v in (data.get("d_shi") or []) if v is not None]
    X0 = [float(v) for v in (data.get("X0") or []) if v is not None]
    X1 = [float(v) for v in (data.get("X1") or []) if v is not None]
    Y0 = [float(v) for v in (data.get("Y0") or []) if v is not None]
    Y1 = [float(v) for v in (data.get("Y1") or []) if v is not None]

    n = len(D)

    # 板长 / 板宽：单次测量，仅 B 类
    uL = dl_inst / math.sqrt(3)
    uW = dl_inst / math.sqrt(3)

    # 孔径（游标卡尺，零点修正）
    D_a = sum(D) / len(D)
    D_corrected = D_a - d0_card
    uD = smartlab_u(D, dd_inst)

    # 板厚（千分尺，零点修正）
    d_a = sum(d_shi) / len(d_shi)
    d_corrected = d_a - d0
    ud = smartlab_u(d_shi, dd_shi_inst)

    # 缝长 / 缝宽（测量显微镜，逐对求差）
    Lx = [abs(x1 - x0) for x0, x1 in zip(X0, X1)]
    Ly = [abs(y1 - y0) for y0, y1 in zip(Y0, Y1)]
    Lx_a = sum(Lx) / len(Lx)
    Ly_a = sum(Ly) / len(Ly)
    # 每对含两个读数，B 类按两个分度值合成
    uB_x = math.sqrt(2) * dx_inst / math.sqrt(3)
    uLx = math.sqrt(smartlab_ua(Lx) ** 2 + uB_x ** 2)
    uLy = math.sqrt(smartlab_ua(Ly) ** 2 + uB_x ** 2)

    # 体积（贯穿板厚 d）
    V_p = L * W * d_corrected
    V_h = math.pi * D_corrected ** 2 / 4 * d_corrected
    V_s = Lx_a * Ly_a * d_corrected
    V = V_p - V_h - V_s

    # 不确定度传递（相对合成）
    uVp = V_p * math.sqrt((uL / L) ** 2 + (uW / W) ** 2 + (ud / d_corrected) ** 2)
    uVh = V_h * math.sqrt((2 * uD / D_corrected) ** 2 + (ud / d_corrected) ** 2)
    uVs = V_s * math.sqrt((uLx / Lx_a) ** 2 + (uLy / Ly_a) ** 2 + (ud / d_corrected) ** 2)
    uV = math.sqrt(uVp ** 2 + uVh ** 2 + uVs ** 2)

    return {
        "dl_inst": dl_inst, "dd_inst": dd_inst, "dd_shi_inst": dd_shi_inst, "dx_inst": dx_inst,
        "d0": d0, "d0_card": d0_card,
        "L": L, "W": W, "uL": uL, "uW": uW,
        "D": D, "D_a": D_a, "D_corrected": D_corrected, "uD": uD,
        "d_shi": d_shi, "d_a": d_a, "d_corrected": d_corrected, "ud": ud,
        "X0": X0, "X1": X1, "Y0": Y0, "Y1": Y1,
        "Lx": Lx, "Ly": Ly, "Lx_a": Lx_a, "Ly_a": Ly_a, "uLx": uLx, "uLy": uLy,
        "V_p": V_p, "V_h": V_h, "V_s": V_s, "V": V,
        "uVp": uVp, "uVh": uVh, "uVs": uVs, "uV": uV,
        "REL": uV / V * 100 if V else 0.0,
        "n": n,
    }


def _print_results(r: dict):
    print("=" * 60)
    print("长度与体积的测量 — 计算结果")
    print("=" * 60)
    print(f"零点读数: 千分尺 d0={r['d0']} mm, 游标卡尺 D0={r['d0_card']} mm")
    print(f"板长 L = {r['L']} mm, u(L) = {r['uL']:.4f} mm")
    print(f"板宽 W = {r['W']} mm, u(W) = {r['uW']:.4f} mm")
    print(f"孔径 D = {r['D']}, 平均 {r['D_a']:.3f} (修正 {r['D_corrected']:.3f}) mm, u(D) = {r['uD']:.5f} mm")
    print(f"板厚 d = {r['d_shi']}, 平均 {r['d_a']:.4f} (修正 {r['d_corrected']:.4f}) mm, u(d) = {r['ud']:.5f} mm")
    print(f"缝长 Lx = {r['Lx']}, 平均 {r['Lx_a']:.4f} mm, u(Lx) = {r['uLx']:.5f} mm")
    print(f"缝宽 Ly = {r['Ly']}, 平均 {r['Ly_a']:.4f} mm, u(Ly) = {r['uLy']:.5f} mm")
    print()
    print(f"板体积 Vp = {r['V_p']:.2f} mm³, u = {r['uVp']:.2f} mm³")
    print(f"圆孔体积 Vh = {r['V_h']:.2f} mm³, u = {r['uVh']:.2f} mm³")
    print(f"缝体积 Vs = {r['V_s']:.2f} mm³, u = {r['uVs']:.2f} mm³")
    print(f"金属体体积 V = {r['V']:.2f} mm³, u = {r['uV']:.2f} mm³")
    print("=" * 60)


def _generate_docx(data: dict, output_path: str):
    # 校验必填数据（required 字段为 null 或 array 含 null → 缺失）
    missing = []
    for k in ("dl_inst", "dd_inst", "dd_shi_inst", "dx_inst",
              "L", "W", "D", "d_shi", "X0", "X1", "Y0", "Y1"):
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

    doc = DocxReportWriter(output_path)
    doc.add_title("长度与体积的测量")
    doc.add_student_info()

    # ── 变体组合：实验原理 / 实验方法（存在 variants.json 且应用传入选择时生效）──
    variants = compose(SCRIPT_DIR, r)
    if "实验原理" in variants:
        doc.add_heading("实验原理", level=1)
        doc.add_paragraph_rich(variants["实验原理"])
    if "实验方法" in variants:
        doc.add_heading("实验方法", level=1)
        doc.add_paragraph_rich(variants["实验方法"])

    doc.add_heading("一、原始数据提交（拍照上传）", level=1)
    doc.add_paragraph("请在下方粘贴原始数据记录照片（含仪器读数与数据表格）。")

    doc.add_heading("二、数据处理", level=1)

    doc.add_heading("1. 实验参数", level=2)
    doc.add_paragraph("")
    doc.add_run("螺旋测微计零点读数 d₀ = ")
    doc.add_inline_math(f"{r['d0']} mm")
    doc.add_run("，游标卡尺零点读数 D₀ = ")
    doc.add_inline_math(f"{r['d0_card']} mm")
    doc.add_paragraph("")
    doc.add_run("仪器误差：米尺 ΔL = ")
    doc.add_inline_math(f"{r['dl_inst']} mm")
    doc.add_run("，游标卡尺分度值 ΔD = ")
    doc.add_inline_math(f"{r['dd_inst']} mm")
    doc.add_run("，千分尺示值误差 Δd = ")
    doc.add_inline_math(f"{r['dd_shi_inst']} mm")
    doc.add_run("，测量显微镜分度值 Δx = ")
    doc.add_inline_math(f"{r['dx_inst']} mm")

    doc.add_heading("2. 板长与板宽", level=2)
    doc.add_paragraph("")
    doc.add_run("用米尺测量金属板长、宽各 1 次，属于单次测量，不确定度仅取 B 类（均匀分布）：")
    doc.add_math(r"u(L) = u(W) = \frac{\Delta L}{\sqrt{3}}")
    doc.add_paragraph("")
    doc.add_run("板长 L = ")
    doc.add_inline_math(f"{r['L']} mm")
    doc.add_run("，u(L) = ")
    doc.add_inline_math(f"{format_number(r['uL'], 4)} mm")
    doc.add_run("；板宽 W = ")
    doc.add_inline_math(f"{r['W']} mm")
    doc.add_run("，u(W) = ")
    doc.add_inline_math(f"{format_number(r['uW'], 4)} mm")

    doc.add_heading("3. 孔径测量（游标卡尺，50 分度）", level=2)
    doc.add_paragraph("")
    doc.add_table(["次数", *[str(i + 1) for i in range(r["n"])]],
                  [[f"{x:.2f}"] for x in r["D"]], col_widths=[1.5] + [1.4] * r["n"])
    doc.add_paragraph("")
    doc.add_run("平均值：")
    doc.add_inline_math(f"D_a = {r['D_a']:.3f} mm")
    doc.add_run("，扣除游标卡尺零点读数 D₀ 后：")
    doc.add_inline_math(f"D = D_a - D_0 = {r['D_corrected']:.3f} mm")
    doc.add_paragraph("")
    doc.add_run("合成不确定度：")
    doc.add_math(
        r"u(D) = \sqrt{u_A(D)^2 + \left(\frac{\Delta D}{\sqrt{3}}\right)^2} = "
        + format_number(r["uD"], 5) + r" \text{ mm}"
    )

    doc.add_heading("4. 板厚测量（螺旋测微计）", level=2)
    doc.add_paragraph("")
    doc.add_table(["次数", *[str(i + 1) for i in range(r["n"])]],
                  [[f"{x:.3f}"] for x in r["d_shi"]], col_widths=[1.5] + [1.4] * r["n"])
    doc.add_paragraph("")
    doc.add_run("平均值：")
    doc.add_inline_math(f"d_a = {r['d_a']:.4f} mm")
    doc.add_run("，扣除零点读数 d₀ 后：")
    doc.add_inline_math(f"d = d_a - d_0 = {r['d_corrected']:.4f} mm")
    doc.add_paragraph("")
    doc.add_run("合成不确定度（一级千分尺示值误差 Δd = 0.004 mm）：")
    doc.add_math(
        r"u(d) = \sqrt{u_A(d)^2 + \left(\frac{\Delta d}{\sqrt{3}}\right)^2} = "
        + format_number(r["ud"], 5) + r" \text{ mm}"
    )

    doc.add_heading("5. 缝长与缝宽测量（15J 测量显微镜）", level=2)
    doc.add_paragraph("")
    doc.add_run("沿 X 方向移动工作台，用十字线对准缝隙两边，读数差即为缝长；Y 方向同理得缝宽。"
                "每个方向记录 5 对读数（起点 X₀/Y₀、终点 X₁/Y₁），逐对求差：")
    rows = []
    for i in range(r["n"]):
        rows.append([
            str(i + 1),
            f"{r['X0'][i]:.3f}", f"{r['X1'][i]:.3f}", f"{r['Lx'][i]:.3f}",
            f"{r['Y0'][i]:.3f}", f"{r['Y1'][i]:.3f}", f"{r['Ly'][i]:.3f}",
        ])
    doc.add_table(
        ["次数", "X₀ / mm", "X₁ / mm", "Lx / mm", "Y₀ / mm", "Y₁ / mm", "Ly / mm"],
        rows, col_widths=[1.2, 1.7, 1.7, 1.7, 1.7, 1.7, 1.7]
    )
    doc.add_paragraph("")
    doc.add_run("缝长平均值：")
    doc.add_inline_math(f"Lx = {r['Lx_a']:.4f} mm")
    doc.add_run("，缝宽平均值：")
    doc.add_inline_math(f"Ly = {r['Ly_a']:.4f} mm")
    doc.add_paragraph("")
    doc.add_run("每个缝值由两个读数之差得到，B 类不确定度按两个分度值合成：")
    doc.add_math(
        r"u_B = \frac{\sqrt{2}\,\Delta x}{\sqrt{3}}, \quad "
        r"u(Lx) = \sqrt{u_A(Lx)^2 + u_B^2} = " + format_number(r["uLx"], 5) + r" \text{ mm}"
    )
    doc.add_run("，u(Ly) = ")
    doc.add_inline_math(format_number(r["uLy"], 5) + r" \text{ mm}")

    doc.add_heading("6. 体积计算与不确定度", level=2)
    doc.add_paragraph("")
    doc.add_run("金属体体积由板体积扣除圆孔体积与缝体积得到（圆孔与缝均贯穿板厚 d）：")
    doc.add_math(
        r"V = V_p - V_h - V_s = L \cdot W \cdot d - \frac{\pi D^2}{4} \cdot d - L_x \cdot L_y \cdot d"
    )
    doc.add_paragraph("")
    rows = [
        ["板体积 Vp / mm³", f"{r['V_p']:.2f}", f"{r['uVp']:.2f}"],
        ["圆孔体积 Vh / mm³", f"{r['V_h']:.2f}", f"{r['uVh']:.2f}"],
        ["缝体积 Vs / mm³", f"{r['V_s']:.2f}", f"{r['uVs']:.2f}"],
        ["金属体体积 V / mm³", f"{r['V']:.2f}", f"{r['uV']:.2f}"],
    ]
    doc.add_table(["项目", "体积值", "不确定度"], rows, col_widths=[4.0, 2.5, 2.5])
    doc.add_paragraph("")
    doc.add_run("相对不确定度合成（各量独立）：")
    doc.add_math(
        r"\frac{u(V_p)}{V_p} = \sqrt{\left(\frac{u(L)}{L}\right)^2 + \left(\frac{u(W)}{W}\right)^2 + \left(\frac{u(d)}{d}\right)^2}"
    )
    doc.add_math(
        r"\frac{u(V_h)}{V_h} = \sqrt{\left(2\frac{u(D)}{D}\right)^2 + \left(\frac{u(d)}{d}\right)^2}, \quad "
        r"\frac{u(V_s)}{V_s} = \sqrt{\left(\frac{u(L_x)}{L_x}\right)^2 + \left(\frac{u(L_y)}{L_y}\right)^2 + \left(\frac{u(d)}{d}\right)^2}"
    )
    doc.add_paragraph("")
    doc.add_run("金属体体积的绝对不确定度：")
    doc.add_math(
        r"u(V) = \sqrt{u(V_p)^2 + u(V_h)^2 + u(V_s)^2} = "
        + format_number(r["uV"], 2) + r" \text{ mm}^3"
    )
    doc.add_paragraph("")
    doc.add_run("最终结果：")
    doc.add_math(
        r"V = (" + format_number(r["V"], 2) + r" \pm " + format_number(r["uV"], 2) + r") \text{ mm}^3"
    )

    doc.add_heading("三、实验结果分析", level=1)
    doc.add_paragraph("")
    doc.add_run("本实验综合使用米尺、游标卡尺、螺旋测微计和 15J 测量显微镜四种长度测量仪器，"
                "分别适用于不同精度等级的测量对象：板长与板宽用米尺单次测量，孔径用 50 分度游标卡尺，"
                "板厚用千分尺，缝长与缝宽用测量显微镜。测得金属体体积 V = ")
    doc.add_inline_math(f"{format_number(r['V'], 2)} mm³")
    doc.add_run("，相对不确定度约 ")
    doc.add_inline_math(f"{format_number(r['uV'] / r['V'] * 100, 2)}%")
    doc.add_run("，精度主要受缝宽（最小尺寸）与孔径测量限制。")

    doc.add_paragraph("")
    doc.add_run("误差来源分析：")
    doc.add_run("（1）米尺估读误差：读数需估读到分度值的 1/10，且存在视差；")
    doc.add_run("（2）游标卡尺零点未对准及读数时游标刻线对齐判断误差；")
    doc.add_run("（3）千分尺零点读数修正与棘轮接触压力控制；")
    doc.add_run("（4）测量显微镜测微鼓轮的空回误差，要求单向旋转读数；")
    doc.add_run("（5）被测物体表面平整度、测量面磨损等系统因素。")

    # ── 变体组合：误差分析 / 结论（存在 variants.json 且应用传入选择时生效）──
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])
    if "结论" in variants:
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    doc.add_heading("四、思考题", level=1)

    doc.add_heading("1. 为什么米尺读数要估读到分度值的 1/10？", level=2)
    doc.add_paragraph(
        "答：米尺最小分度为 1 mm，测量时可精确读到毫米位。估读到分度值的 1/10（即 0.1 mm）"
        "可以在不降低可靠性的前提下充分利用仪器信息，减小读数随机误差。估读本身就是一次"
        "在相邻刻线之间的内插，是人为判断的结果，其不确定度约为最小分度的 1/10，故读数结果"
        "记为 L ± 0.1 mm 量级。"
    )

    doc.add_heading("2. 游标卡尺为什么能准确读出分度值的 1/n？", level=2)
    doc.add_paragraph(
        "答：游标卡尺利用游标（副尺）与主尺分度之间的微小差值来实现细分。n 个游标分度与主尺上 "
        "Mn−1 个分度等长，主尺分度 a 与游标分度 b 之差 h = a − b = a/n，即为游标卡尺的分度值。"
        "读数时只需判断游标上哪一根刻线与主尺刻线对齐，该刻线的序号 k 与 h 的乘积 kh 就是"
        "小于一个主尺分度的部分，因此可以准确读出 a/n 的整数倍而无需估读。"
    )

    doc.add_heading("3. 为什么要对千分尺和游标卡尺进行零点修正？", level=2)
    doc.add_paragraph(
        "答：仪器在长期使用后，测量面磨损或装配间隙变化会使“零位”偏离理想位置。若测量前两测量面"
        "直接接触时微分套筒读数不为零（千分尺零点读数 d₀ 可正可负），或游标零线与主尺零线不重合"
        "（游标卡尺零点读数 D₀），则所有测量读数都带有固定的系统偏差。通过测量前记录零点读数，"
        "并在结果中扣除（实际长度 = 测量读数 − 零点读数），即可消除该系统误差。"
    )

    doc.save()
    doc.close()


def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "长度与体积的测量.docx")
    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return
    _generate_docx(data, DOCX_FILE)
    print(f"报告已生成: {DOCX_FILE}")


if __name__ == "__main__":
    main()
