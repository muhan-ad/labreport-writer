# -*- coding: utf-8 -*-
"""拉伸法测量钢丝杨氏弹性模量（光杠杆法）— 数据处理脚本。

参考源：XDU物理实验小助手 实验定义 JSON（模块 7492）
实验原理：拉伸法测杨氏模量 Y = FL/(SΔL)，用光杠杆法测量微小伸长量 ΔL，
  逐差法处理标尺读数。Y = 32·g·L·H/(π·d²·D·Δn)。
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

T_FACTOR = [0, 0, 1.84, 1.32, 1.2, 1.14, 1.11, 1.09, 1.08]
G = 9.8  # smartlab_g


def smartlab_ua(data):
    n = len(data)
    t = T_FACTOR[n] if n < len(T_FACTOR) else 1.0
    mean_val = sum(data) / n
    variance = sum((x - mean_val) ** 2 for x in data) / ((n - 1) * n)
    return t * math.sqrt(variance)


def smartlab_u(data, inst_err):
    ua = smartlab_ua(data)
    return math.sqrt(ua ** 2 + (inst_err / math.sqrt(3)) ** 2)


def get_n_d(arr):
    """逐差法：arr[i+4] - arr[i]，i=0..3。"""
    return [arr[i + 4] - arr[i] for i in range(len(arr) - 4)]


# ── 示例数据（计算器 default）──
NI_ZHENG_DEFAULT = [2.06, 2.70, 3.32, 3.91, 4.38, 4.95, 5.56, 6.15]  # 增重，cm
NI_JIAN_DEFAULT = [1.96, 2.58, 3.20, 3.78, 4.44, 5.01, 5.62, 6.23]   # 减重，cm
D_SHI_DEFAULT = [0.626, 0.625, 0.628, 0.622, 0.625, 0.623]  # 钢丝直径，mm
D_0_DEFAULT = -0.015  # 零点修正，mm
L_DEFAULT = 0.973   # 钢丝长度，m
D_DEFAULT = 45      # 光杠杆常数（后足到前足连线距离），mm
H_DEFAULT = 0.939   # 镜面到标尺距离，m
D_INST_ERR = 0.005  # 螺旋测微计仪器误差，mm


# （方式三：_create_template 已移除，数据真相为 data.json）


def _compute(data: dict) -> dict:
    # 读参数
    L = float(data["L"])
    D = float(data["D"])
    H = float(data["H"])
    d_0 = float(data["d_0"])
    # 读直径（过滤未填）
    d_shi = [float(v) for v in data.get("d_shi", []) if v is not None]
    # 读标尺读数（增重/减重配对，过滤未填）
    ni_zheng, ni_jian = [], []
    for z, j in zip(data.get("ni_zheng", []), data.get("ni_jian", [])):
        if z is not None and j is not None:
            ni_zheng.append(float(z))
            ni_jian.append(float(j))

    n_ni = len(ni_zheng)
    n_d = len(d_shi)

    # 标尺读数平均
    ni = [(z + j) / 2 for z, j in zip(ni_zheng, ni_jian)]

    # 逐差法
    delta_n = get_n_d(ni)
    delta_n_a = sum(delta_n) / len(delta_n)
    delta_n_dev = [abs(x - delta_n_a) for x in delta_n]
    delta_n_dev_a = sum(delta_n_dev) / len(delta_n_dev)

    # 钢丝直径
    d_shi_a = sum(d_shi) / n_d
    d_shi_u = smartlab_u(d_shi, D_INST_ERR)
    d_shi_corrected = d_shi_a - d_0  # 零点修正后

    # 杨氏模量
    Y = 8 * 4 * G * L * H / (math.pi * d_shi_a ** 2 * D * delta_n_a)

    # 不确定度传递
    Y_u = math.sqrt(
        (0.003 / L) ** 2
        + (0.003 / H) ** 2
        + (2 * d_shi_u / d_shi_a) ** 2
        + (0.003 / (D / 1000)) ** 2
        + (delta_n_dev_a / delta_n_a) ** 2
    ) * Y

    return {
        "L": L, "D": D, "H": H, "d_0": d_0,
        "ni_zheng": ni_zheng, "ni_jian": ni_jian, "ni": ni,
        "delta_n": delta_n, "delta_n_a": delta_n_a,
        "delta_n_dev": delta_n_dev, "delta_n_dev_a": delta_n_dev_a,
        "d_shi": d_shi, "d_shi_a": d_shi_a, "d_shi_u": d_shi_u,
        "d_shi_corrected": d_shi_corrected,
        "Y": Y, "Y_u": Y_u,
        "n_ni": n_ni, "n_d": n_d,
    }


def _print_results(r: dict):
    print("=" * 60)
    print("拉伸法测杨氏弹性模量 — 计算结果")
    print("=" * 60)
    print(f"L={r['L']}m, D={r['D']}mm, H={r['H']}m, d_0={r['d_0']}mm")
    print(f"d_shi = {r['d_shi']}")
    print(f"d_shi_a = {r['d_shi_a']:.4f} mm (修正后 {r['d_shi_corrected']:.4f} mm)")
    print(f"d_shi_u = {r['d_shi_u']:.6f} mm")
    print()
    print(f"{'序号':>4} {'增重':>8} {'减重':>8} {'平均':>8}")
    for i in range(r["n_ni"]):
        print(f"{i+1:4d} {r['ni_zheng'][i]:8.2f} {r['ni_jian'][i]:8.2f} {r['ni'][i]:8.2f}")
    print()
    print("逐差 Δn =", [round(x, 4) for x in r["delta_n"]])
    print(f"Δn_a = {r['delta_n_a']:.4f} cm")
    print(f"平均偏差 δn_a = {r['delta_n_dev_a']:.4f} cm")
    print()
    print(f"Y = {r['Y']:.4e} Pa")
    print(f"Y_u = {r['Y_u']:.4e} Pa")
    print("=" * 60)


def _generate_docx(data: dict, output_path: str):
    r = _compute(data)
    _print_results(r)

    doc = DocxReportWriter(output_path)
    doc.add_title("拉伸法测量钢丝杨氏弹性模量")
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

    doc.add_heading("1. 实验参数", level=2)
    doc.add_paragraph("")
    doc.add_run("钢丝长度 L = ")
    doc.add_inline_math(f"{r['L']} m")
    doc.add_run("，光杠杆常数 D = ")
    doc.add_inline_math(f"{r['D']} mm")
    doc.add_run("，镜面到标尺距离 H = ")
    doc.add_inline_math(f"{r['H']} m")
    doc.add_run("，螺旋测微计零点修正 d_0 = ")
    doc.add_inline_math(f"{r['d_0']} mm")

    doc.add_heading("2. 钢丝直径测量", level=2)
    doc.add_paragraph("")
    d_str = "，".join(f"{x:.3f}" for x in r["d_shi"])
    doc.add_paragraph(f"测量值（mm）：{d_str}")
    doc.add_paragraph("")
    doc.add_run("直径平均值：")
    doc.add_inline_math(f"d_a = {r['d_shi_a']:.4f} mm")
    doc.add_run("，修正零点后：")
    doc.add_inline_math(f"d = d_a - d_0 = {r['d_shi_corrected']:.4f} mm")
    doc.add_paragraph("")
    doc.add_run("合成不确定度（仪器误差 Δ_inst = 0.005 mm）：")
    doc.add_math(
        r"u(d) = \sqrt{u_A(d)^2 + \left(\frac{0.005}{\sqrt{3}}\right)^2} = "
        + format_number(r["d_shi_u"], 6)
        + r" \text{ mm}"
    )

    doc.add_heading("3. 光杠杆标尺读数与逐差法", level=2)
    doc.add_paragraph("")
    doc.add_run("记录增重和减重时的标尺读数，取平均值消除摩擦和滞后影响：")

    rows = []
    for i in range(r["n_ni"]):
        rows.append([
            str(i + 1),
            f"{r['ni_zheng'][i]:.2f}",
            f"{r['ni_jian'][i]:.2f}",
            f"{r['ni'][i]:.2f}",
        ])
    doc.add_table(
        ["砝码序号", "增重 $n_i$ / cm", "减重 $n_i$ / cm", "平均值 / cm"],
        rows, col_widths=[2.0, 2.5, 2.5, 2.5]
    )

    doc.add_paragraph("")
    doc.add_run("采用逐差法处理数据：将 8 个读数分为前后两组，对应增加 4 个砝码的读数差：")
    doc.add_math(
        r"\Delta n_i = n_{i+4} - n_i \quad (i = 1,2,3,4)"
    )
    dn_str = "，".join(f"{x:.4f}" for x in r["delta_n"])
    doc.add_paragraph(f"逐差值（cm）：{dn_str}")
    doc.add_paragraph("")
    doc.add_run("逐差平均值：")
    doc.add_inline_math(f"Δn_a = {r['delta_n_a']:.4f} cm")
    doc.add_run("，平均偏差：")
    doc.add_inline_math(f"δn_a = {r['delta_n_dev_a']:.4f} cm")

    doc.add_heading("4. 杨氏模量计算", level=2)
    doc.add_paragraph("")
    doc.add_run("由胡克定律和光杠杆放大原理，杨氏模量公式为（d 单位 mm，D 单位 mm，Δn 单位 cm，结果单位 10¹¹ Pa）：")
    doc.add_math(
        r"Y = \frac{8 \cdot 4 \cdot g \cdot L \cdot H}{\pi \cdot d^2 \cdot D \cdot \Delta n}"
    )
    doc.add_paragraph("")
    doc.add_run("代入数据：")
    doc.add_math(
        r"Y = \frac{32 \times 9.8 \times " + str(r["L"]) + r" \times " + str(r["H"])
        + r"}{\pi \times (" + format_number(r["d_shi_a"]) + r")^2 \times "
        + str(int(r["D"])) + r" \times " + format_number(r["delta_n_a"]) + r"}"
        + r" = " + format_number(r["Y"], 2) + r" \times 10^{11} \text{ Pa}"
    )

    doc.add_heading("5. 不确定度评定", level=2)
    doc.add_paragraph("")
    doc.add_run("相对不确定度合成（L、H 仪器误差 0.003 m，D 仪器误差 0.003 m）：")
    doc.add_math(
        r"\frac{u(Y)}{Y} = \sqrt{\left(\frac{0.003}{L}\right)^2 + \left(\frac{0.003}{H}\right)^2"
        r" + \left(2\frac{u(d)}{d}\right)^2 + \left(\frac{0.003}{D/1000}\right)^2"
        r" + \left(\frac{\delta n_a}{\Delta n_a}\right)^2}"
    )
    doc.add_paragraph("")
    doc.add_run("最终结果：")
    doc.add_math(
        r"Y = (" + format_number(r["Y"], 2) + r" \pm " + format_number(r["Y_u"], 2)
        + r") \times 10^{11} \text{ Pa}"
    )

    doc.add_heading("三、实验结果分析", level=1)
    doc.add_paragraph("")
    doc.add_run("本实验采用拉伸法和光杠杆放大技术测量钢丝的杨氏弹性模量。通过逐差法处理标尺读数，")
    doc.add_run("充分利用了全部测量数据，减小了随机误差。测得杨氏模量 Y = ")
    doc.add_inline_math(f"{format_number(r['Y'], 2)} × 10¹¹ Pa")
    doc.add_run("，与钢丝的公认值（约 2.0×10¹¹ Pa）进行比较，可评估实验准确度。")

    doc.add_paragraph("")
    doc.add_run("误差来源分析：")
    doc.add_run("（1）钢丝直径测量的随机误差和螺旋测微计的仪器误差；")
    doc.add_run("（2）光杠杆常数 D 和镜面到标尺距离 H 的测量误差；")
    doc.add_run("（3）标尺读数的视差和估读误差，增重减重过程中的摩擦滞后；")
    doc.add_run("（4）钢丝可能存在的微小弯曲和非弹性形变，导致加卸载读数不完全对称；")
    doc.add_run("（5）砝码质量的标称误差。")

    # ── 变体组合：误差分析 / 结论（存在 variants.json 且应用传入选择时生效）──
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])
    if "结论" in variants:
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    doc.add_heading("四、思考题", level=1)

    doc.add_heading("1. 为什么要用逐差法处理数据？", level=2)
    doc.add_paragraph(
        "答：逐差法可以充分利用全部测量数据，减小随机误差。如果只用首末两项之差计算，"
        "中间数据全部浪费，且首末两项的误差直接决定结果。逐差法将数据分成前后两组对应相减，"
        "相当于多次测量取平均，提高了结果的可靠性。同时逐差法还能检验数据的线性关系——"
        "如果各逐差值接近相等，说明力与伸长量呈线性关系（胡克定律成立）。"
    )

    doc.add_heading("2. 光杠杆法的放大倍数是多少？如何提高测量灵敏度？", level=2)
    doc.add_paragraph(
        "答：光杠杆的放大倍数为 2D/H（D 为镜面到标尺距离，H 为光杠杆常数即后足到前足连线距离）。"
        "当钢丝伸长 ΔL 时，光杠杆后足下降 ΔL，镜面偏转角度 θ ≈ ΔL/H，标尺读数变化 Δn = 2Dθ = 2D·ΔL/H。"
        "提高灵敏度的方法：增大镜面到标尺距离 D，减小光杠杆常数 H。但 D 过大时标尺像会变小变模糊，"
        "H 过小时光杠杆稳定性变差，因此需要综合考虑。"
    )

    doc.add_heading("3. 为什么要进行增重和减重两次测量？", level=2)
    doc.add_paragraph(
        "答：增重和减重两次测量可以消除摩擦滞后和弹性后效的影响。在加载过程中，"
        "光杠杆镜面和支架之间可能存在静摩擦，导致加卸载时标尺读数不重合（滞后回线）。"
        "取增重和减重读数的平均值，可以部分消除这种系统误差。同时两次测量还能检验数据的重复性，"
        "如果增重减重数据差异过大，说明实验装置存在问题或操作不规范。"
    )

    doc.save()
    doc.close()


def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "拉伸法测量杨氏弹性模量.docx")
    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return
    _generate_docx(data, DOCX_FILE)
    print(f"报告已生成: {DOCX_FILE}")


if __name__ == "__main__":
    main()
