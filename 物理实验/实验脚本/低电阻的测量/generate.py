# -*- coding: utf-8 -*-
"""低电阻的测量（双臂电桥）— 数据处理脚本。

参考源：XDU物理实验小助手 实验定义 JSON（模块 0ebc）
实验原理：双臂电桥（开尔文电桥）消除接触电阻和引线电阻影响，
  测量金属丝的低电阻 R_x = (R_3/R_1)·R_n，并计算电阻率 ρ = πd²R_x/(4L)。
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

# ── t 因子表（与计算器一致）──
T_FACTOR = [0, 0, 1.84, 1.32, 1.2, 1.14, 1.11, 1.09, 1.08]


def smartlab_ua(data):
    """A 类不确定度：t 因子 * std/sqrt(n)。"""
    n = len(data)
    t = T_FACTOR[n] if n < len(T_FACTOR) else 1.0
    mean_val = sum(data) / n
    variance = sum((x - mean_val) ** 2 for x in data) / ((n - 1) * n)
    return t * math.sqrt(variance)


def smartlab_u(data, inst_err):
    """合成不确定度：sqrt(u_A² + (inst_err/√3)²)。"""
    ua = smartlab_ua(data)
    return math.sqrt(ua ** 2 + (inst_err / math.sqrt(3)) ** 2)


# ── 示例数据（计算器 default）──
R_1_DEFAULT = 1000.0  # Ω
R_3_DEFAULT = 100.0   # Ω
D_DEFAULT = [3.958, 3.955, 3.956, 3.951, 3.953, 3.952]  # mm
L_DEFAULT = [100, 140, 180, 220, 260, 300, 340, 380]     # mm
R_N_ZHENG_DEFAULT = [0.00558, 0.00775, 0.01, 0.01224, 0.01446, 0.0167, 0.01891, 0.02127]
R_N_FAN_DEFAULT = [0.00565, 0.00787, 0.0115, 0.01236, 0.01466, 0.01686, 0.01916, 0.02139]
D_INST_ERR = 0.001  # mm（螺旋测微计仪器误差）


# （方式三：_create_template 已移除，数据真相为 data.json）


def _compute(data: dict) -> dict:
    # 读参数
    r1 = float(data["R_1"])
    r3 = float(data["R_3"])
    # 读直径（6 次，过滤未填项）
    d = [float(v) for v in data.get("d", []) if v is not None]
    # 读电阻测量（8 个长度点，L 与正反向读数配对，过滤未填项）
    L = []
    rn_zheng = []
    rn_fan = []
    for lv, zv, fv in zip(data.get("L", []), data.get("R_n_zheng", []), data.get("R_n_fan", [])):
        if lv is not None and zv is not None and fv is not None:
            L.append(float(lv))
            rn_zheng.append(float(zv))
            rn_fan.append(float(fv))

    n_d = len(d)
    n_l = len(L)

    # 直径统计
    d_a = sum(d) / n_d
    d_ua = smartlab_ua(d)
    d_u = smartlab_u(d, D_INST_ERR)

    # 电桥读数平均
    rn_a = [(z + f) / 2 for z, f in zip(rn_zheng, rn_fan)]

    # 待测电阻 R_x = R_n_a * R_3 / R_1 * 1000（单位 mΩ）
    R_x = [rna * r3 / r1 * 1000 for rna in rn_a]
    R_x_a = sum(R_x) / n_l
    R_x_ua = smartlab_ua(R_x)

    # 电阻率 ρ = π*d_a²*R_x*100/(4*L)
    rho = [math.pi * d_a ** 2 * rx * 100 / (4 * li) for rx, li in zip(R_x, L)]
    rho_a = sum(rho) / n_l

    # 电阻率不确定度传递
    rho_u = math.sqrt(4 * (d_u / d_a) ** 2 + (R_x_ua / R_x_a) ** 2) * rho_a

    return {
        "r1": r1, "r3": r3,
        "d": d, "d_a": d_a, "d_ua": d_ua, "d_u": d_u,
        "L": L, "rn_zheng": rn_zheng, "rn_fan": rn_fan, "rn_a": rn_a,
        "R_x": R_x, "R_x_a": R_x_a, "R_x_ua": R_x_ua,
        "rho": rho, "rho_a": rho_a, "rho_u": rho_u,
        "n_d": n_d, "n_l": n_l,
    }


def _print_results(r: dict):
    print("=" * 60)
    print("低电阻的测量（双臂电桥）— 计算结果")
    print("=" * 60)
    print(f"R_1 = {r['r1']:.0f} Ω, R_3 = {r['r3']:.0f} Ω")
    print(f"d = {r['d']}")
    print(f"d_a = {r['d_a']:.6f} mm, d_u = {r['d_u']:.6f} mm")
    print()
    print(f"{'L/mm':>8} {'R_n正/Ω':>10} {'R_n反/Ω':>10} {'R_n均/Ω':>10} {'R_x/mΩ':>10} {'ρ':>12}")
    for i in range(r["n_l"]):
        print(f"{r['L'][i]:8.0f} {r['rn_zheng'][i]:10.5f} {r['rn_fan'][i]:10.5f} "
              f"{r['rn_a'][i]:10.5f} {r['R_x'][i]:10.4f} {r['rho'][i]:12.4f}")
    print()
    print(f"R_x_a = {r['R_x_a']:.4f} mΩ, R_x_ua = {r['R_x_ua']:.6f} mΩ")
    print(f"ρ_a = {r['rho_a']:.4f}, ρ_u = {r['rho_u']:.4f}")
    print("=" * 60)


def _generate_docx(data: dict, output_path: str):
    # 校验必填数据（required 字段为 null 或 array 含 null → 缺失）
    def _flat(v):
        if isinstance(v, list) and v and isinstance(v[0], list):
            return [x for row in v for x in row]
        return v if isinstance(v, list) else [v]

    missing = []
    for k in ("R_1", "R_3", "d", "L", "R_n_zheng", "R_n_fan"):
        v = data.get(k)
        if v is None:
            missing.append(k)
        elif isinstance(v, list) and any(x is None for x in _flat(v)):
            missing.append(k)
    if missing:
        print("以下必填数据未填写，请补齐后重新运行：")
        for m in missing:
            print(f"  - {m}")
        return

    r = _compute(data)
    _print_results(r)

    doc = DocxReportWriter(output_path)
    doc.add_title("低电阻的测量（双臂电桥）")
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
    doc.add_paragraph("请在下方粘贴原始数据记录照片。")

    doc.add_heading("二、数据处理", level=1)

    doc.add_heading("1. 金属丝直径测量", level=2)
    doc.add_paragraph("")
    doc.add_run("用螺旋测微计在金属丝不同位置测量直径 6 次，仪器误差 Δ_inst = 0.001 mm。")
    d_str = "，".join(f"{x:.3f}" for x in r["d"])
    doc.add_paragraph(f"测量值（mm）：{d_str}")
    doc.add_paragraph("")
    doc.add_run("直径平均值：")
    doc.add_inline_math(f"d_a = {r['d_a']:.4f} mm")
    doc.add_paragraph("")
    doc.add_run("A 类不确定度（t 因子法，n=6, t=1.11）：")
    doc.add_inline_math(f"u_A(d) = {r['d_ua']:.6f} mm")
    doc.add_paragraph("")
    doc.add_run("合成不确定度：")
    doc.add_math(
        r"u(d) = \sqrt{u_A(d)^2 + \left(\frac{\Delta_{inst}}{\sqrt{3}}\right)^2} = "
        + format_number(r["d_u"], 6)
        + r" \text{ mm}"
    )

    doc.add_heading("2. 双臂电桥测电阻", level=2)
    doc.add_paragraph("")
    doc.add_run("电桥比例臂 R_1 = ")
    doc.add_inline_math(f"{r['r1']:.0f} Ω")
    doc.add_run("，R_3 = ")
    doc.add_inline_math(f"{r['r3']:.0f} Ω")
    doc.add_run("。改变金属丝长度 L，分别记录正向和反向电桥读数 R_n，取平均值消除热电势影响。")
    doc.add_paragraph("待测电阻：")
    doc.add_math(
        r"R_x = \frac{R_3}{R_1} \cdot R_n \times 1000 \quad (\text{m}\Omega)"
    )

    rows = []
    for i in range(r["n_l"]):
        rows.append([
            f"{r['L'][i]:.0f}",
            f"{r['rn_zheng'][i]:.5f}",
            f"{r['rn_fan'][i]:.5f}",
            f"{r['rn_a'][i]:.5f}",
            f"{r['R_x'][i]:.4f}",
        ])
    doc.add_table(
        ["$L$ / mm", "$R_n$(正) / Ω", "$R_n$(反) / Ω", "$R_n$(平均) / Ω", "$R_x$ / mΩ"],
        rows, col_widths=[1.8, 2.2, 2.2, 2.2, 2.0]
    )

    doc.add_paragraph("")
    doc.add_run("8 个长度点的待测电阻平均值：")
    doc.add_inline_math(f"R_{{x,a}} = {r['R_x_a']:.4f} mΩ")
    doc.add_run("，A 类不确定度：")
    doc.add_inline_math(f"u_A(R_x) = {r['R_x_ua']:.6f} mΩ")

    doc.add_heading("3. 电阻率计算", level=2)
    doc.add_paragraph("")
    doc.add_run("由电阻公式 R = ρL/S，S = πd²/4，得电阻率：")
    doc.add_math(
        r"\rho = \frac{\pi d_a^2 R_x \times 100}{4L}"
    )

    rows2 = []
    for i in range(r["n_l"]):
        rows2.append([f"{r['L'][i]:.0f}", f"{r['rho'][i]:.4f}"])
    doc.add_table(["$L$ / mm", "$\\rho$"], rows2, col_widths=[3.0, 4.0])

    doc.add_paragraph("")
    doc.add_run("电阻率平均值：")
    doc.add_inline_math(f"ρ_a = {r['rho_a']:.4f}")
    doc.add_paragraph("")
    doc.add_run("不确定度传递（相对不确定度合成）：")
    doc.add_math(
        r"\frac{u(\rho)}{\rho} = \sqrt{4\left(\frac{u(d)}{d_a}\right)^2 + \left(\frac{u_A(R_x)}{R_{x,a}}\right)^2}"
    )
    doc.add_paragraph("")
    doc.add_run("电阻率最终结果：")
    doc.add_math(
        r"\rho = " + format_number(r["rho_a"], r["rho_u"])
    )

    doc.add_heading("三、实验结果分析", level=1)
    doc.add_paragraph("")
    doc.add_run("本实验采用双臂电桥（开尔文电桥）测量金属丝的低电阻，通过正反向测量消除热电势影响，")
    doc.add_run("测量了 8 个不同长度下的电阻值并计算电阻率。电阻率平均值 ρ_a = ")
    doc.add_inline_math(f"{format_number(r['rho_a'])}")
    doc.add_run("，各长度点的电阻率一致性较好，说明实验数据可靠。")

    doc.add_paragraph("")
    doc.add_run("误差来源分析：")
    doc.add_run("（1）螺旋测微计的读数误差和金属丝直径不均匀性；")
    doc.add_run("（2）电桥灵敏度限制，平衡点判断存在视差；")
    doc.add_run("（3）接触电阻和引线电阻虽被双臂电桥结构消除，但电压端接触不良仍会引入误差；")
    doc.add_run("（4）热电势和接触电势的影响（通过正反向测量部分消除）；")
    doc.add_run("（5）金属丝长度测量的定位误差。")

    # ── 变体组合：误差分析 / 结论（存在 variants.json 且应用传入选择时生效）──
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])
    if "结论" in variants:
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    doc.add_heading("四、思考题", level=1)

    doc.add_heading("1. 双臂电桥为什么能消除接触电阻和引线电阻的影响？", level=2)
    doc.add_paragraph(
        "答：双臂电桥在单臂电桥基础上增加了两个比例臂（R_3、R_4），将待测电阻 R_x 和标准电阻 R_n "
        "的电压端直接接入比例臂回路，使电流端的接触电阻和引线电阻被排除在桥臂之外。"
        "当满足 R_1/R_2 = R_3/R_4 时，跨线电阻的影响也被消除，从而准确测量低电阻。"
    )

    doc.add_heading("2. 为什么要进行正反向测量？", level=2)
    doc.add_paragraph(
        "答：在低电阻测量中，回路中存在热电势和接触电势（由不同金属接触点的温度差引起），"
        "这些附加电势会叠加在测量信号上，导致电桥平衡点偏移。正反向测量（交换电流方向）后，"
        "热电势的符号反转而电阻电压不变，取两次读数的平均值即可消除热电势的系统误差。"
    )

    doc.add_heading("3. 如果金属丝直径不均匀，对电阻率测量结果有何影响？", level=2)
    doc.add_paragraph(
        "答：电阻率计算中使用的是直径的平均值 d_a，假设金属丝是均匀圆柱。如果直径实际不均匀，"
        "不同位置的横截面积不同，电阻分布也不均匀。平均直径只能给出等效横截面积，"
        "当直径波动较大时，等效截面积与实际截面积存在偏差，引入系统误差。"
        "因此实验中在不同位置多次测量直径取平均，以减小这种影响。"
    )

    doc.save()
    doc.close()


def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "低电阻的测量.docx")
    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return
    _generate_docx(data, DOCX_FILE)
    print(f"报告已生成: {DOCX_FILE}")


if __name__ == "__main__":
    main()
