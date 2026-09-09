"""空气中声速的测量 — 数据处理脚本。

方法：共振干涉法（驻波法） + 位相比较法（李萨如图形法）
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

# ── 物理常数与仪器参数（按教材） ──
V0 = 331.45           # 0°C 时空气中声速 (m/s)
T0_K = 273.15         # 0°C 对应的开尔文温度 (K)
DELTA_F = 0.001       # 频率分辨率 (kHz)
DELTA_X_INST = 0.02   # 声速测定仪（游标卡尺）Δ_仪 (mm)
N_HALF = 6            # 逐差法半组数 (12 个测量值分 6+6)
N_LAMBDA = 6          # λ_i 个数


# ═══════════════════════════════════════════════════
# Excel 模板生成
# ═══════════════════════════════════════════════════

# （方式三：_create_template 已移除，数据真相为 data.json）


# ═══════════════════════════════════════════════════
# 计算核心
# ═══════════════════════════════════════════════════

def _compute_method(L_values: list[float], f: float, t_celsius: float) -> dict:
    """对一个方法的 12 个位置测量值进行完整计算。

    返回包含所有中间和最终结果的字典。
    """
    # 逐差法计算 λ_i
    lambda_vals = []
    for i in range(N_LAMBDA):
        lam = abs(L_values[i + N_HALF] - L_values[i]) / 3.0
        lambda_vals.append(lam)

    lambda_bar = mean(lambda_vals)

    # λ 不确定度：A 类（均值标准误）+ B 类（仪器/√3）
    u_lambda_A = type_a(lambda_vals)
    u_lambda_B = type_b(DELTA_X_INST)
    u_lambda = combine(u_lambda_A, u_lambda_B)

    # 声速（kHz × mm = m/s）
    v_meas = f * lambda_bar

    # 声速不确定度
    u_v = v_meas * math.sqrt(
        (u_lambda / lambda_bar) ** 2 + (DELTA_F / f) ** 2
    )

    # 理论值
    T_kelvin = t_celsius + T0_K
    v_theory = V0 * math.sqrt(T_kelvin / T0_K)

    # 相对误差
    relative_error = abs(v_meas - v_theory) / v_theory * 100

    return {
        "L": L_values,
        "lambda_vals": lambda_vals,
        "lambda_bar": lambda_bar,
        "u_lambda_A": u_lambda_A,
        "u_lambda_B": u_lambda_B,
        "u_lambda": u_lambda,
        "v_meas": v_meas,
        "u_v": u_v,
        "v_theory": v_theory,
        "t": t_celsius,
        "T_kelvin": T_kelvin,
        "f": f,
        "E": relative_error,
    }


def _compute(data: dict) -> dict:
    """由 data.json 计算两法结果并汇总，返回供变体注入的扁平结果字典 r。"""
    f_khz = float(data["f"])
    t_celsius = float(data["t"])
    L1 = [float(v) for v in data["L1"]]
    L2 = [float(v) for v in data["L2"]]

    r1 = _compute_method(L1, f_khz, t_celsius)
    r2 = _compute_method(L2, f_khz, t_celsius)

    r = {
        "f": f_khz,
        "t": t_celsius,
        "T_kelvin": r1["T_kelvin"],
        "v_theory": r1["v_theory"],
        "m1": r1,
        "m2": r2,
        "lambda1": r1["lambda_bar"],
        "u_lambda1": r1["u_lambda"],
        "v1": r1["v_meas"],
        "u_v1": r1["u_v"],
        "E1": r1["E"],
        "lambda2": r2["lambda_bar"],
        "u_lambda2": r2["u_lambda"],
        "v2": r2["v_meas"],
        "u_v2": r2["u_v"],
        "E2": r2["E"],
        "lambda_avg": mean([r1["lambda_bar"], r2["lambda_bar"]]),
        "v_avg": mean([r1["v_meas"], r2["v_meas"]]),
        "u_v_avg": mean([r1["u_v"], r2["u_v"]]),
        "E_avg": mean([r1["E"], r2["E"]]),
    }
    return r


# ═══════════════════════════════════════════════════
# 报告生成
# ═══════════════════════════════════════════════════

def _write_method_section(doc, r: dict, table_label: str):
    """按范例格式输出一个方法的完整数据处理子节。

    范例结构：
      表 3-6-X 空气中声速的测量
      参数 → 数据表(含 λ_i) → 理论值 → λ̄ → v̄ → Δλ → Δv → v' → E
    """
    L = r["L"]
    lam = r["lambda_vals"]
    lam_bar = r["lambda_bar"]

    # ── 实验参数 ──
    doc.add_paragraph(
        f"室温 t = {r['t']}°C，频率 f = {r['f']:.4f} kHz，"
        f"Δf = {DELTA_F} kHz，声速测定仪 Δx_仪 = {DELTA_X_INST} mm。"
    )

    # ── 数据表（含 λ_i） ──
    # 前 6 行填计算值，后 6 行填 "/"
    # 注：表格单元格不支持 OMath 公式渲染，故公式说明以正文形式放在表前，
    # 表头仅用纯文本列名
    doc.add_paragraph(
        "用逐差法计算波长，将 12 个数据分为前后两组（1~6 和 7~12），"
        "对应项相减后除以 3："
    )
    doc.add_math(r"\lambda_i = \frac{1}{3}|L_{i+6} - L_i|")

    headers = ["$i$", "$L_i$ / mm", "$\\lambda_i$ / mm"]
    rows = []
    for i in range(12):
        if i < N_LAMBDA:
            rows.append([str(i + 1), f"{L[i]:.2f}", f"{lam[i]:.3f}"])
        else:
            rows.append([str(i + 1), f"{L[i]:.2f}", "/"])
    doc.add_table(headers, rows, col_widths=[1.5, 5.0, 6.0])

    # ── 理论声速 ──
    doc.add_paragraph("开尔文温度及当前理论声速：")
    doc.add_inline_math(
        rf"T = {r['T_kelvin']:.3f}\,\mathrm{{K}}"
    )
    doc.add_math(
        rf"v = {V0} \sqrt{{\frac{{T}}{{{T0_K}}}}} = "
        rf"{V0} \sqrt{{1 + \frac{{t}}{{{T0_K}}}}} = "
        rf"{r['v_theory']:.3f}\,\mathrm{{m/s}}"
    )

    # ── 平均波长与声速 ──
    doc.add_paragraph("平均波长：")
    doc.add_math(
        rf"\bar{{\lambda}} = \frac{{1}}{{{N_LAMBDA}}}"
        rf"\sum_{{i=1}}^{{{N_LAMBDA}}} \lambda_i = "
        rf"{lam_bar:.3f}\,\mathrm{{mm}}"
    )
    doc.add_paragraph("计算声速结果：")
    doc.add_math(
        rf"\bar{{v}} = f \cdot \bar{{\lambda}} = "
        rf"{r['f']:.4f} \times {lam_bar:.3f} = "
        rf"{r['v_meas']:.3f}\,\mathrm{{m/s}}"
    )

    # ── 波长不确定度 ──
    doc.add_paragraph("波长不确定度：")
    doc.add_math(
        rf"\Delta\lambda = \sqrt{{(\Delta\lambda_A)^2 + "
        rf"(\Delta\lambda_B)^2}} = "
        rf"\sqrt{{\frac{{\sum_{{i=1}}^{{{N_LAMBDA}}}"
        rf"(\lambda_i - \bar{{\lambda}})^2}}{{{N_LAMBDA} \times "
        rf"({N_LAMBDA} - 1)}} + "
        rf"\left(\frac{{\Delta x_{{\text{{仪}}}}}}{{\sqrt{{3}}}}\right)^2}} = "
        rf"{r['u_lambda']:.3f}\,\mathrm{{mm}}"
    )

    # ── 声速误差 ──
    doc.add_paragraph("声速误差：")
    doc.add_math(
        rf"\Delta v = \sqrt{{"
        rf"\left(\frac{{\Delta\lambda}}{{\bar{{\lambda}}}}\right)^2 + "
        rf"\left(\frac{{\Delta f}}{{f}}\right)^2}} \cdot \bar{{v}} = "
        rf"{r['u_v']:.3f}\,\mathrm{{m/s}}"
    )

    # ── 实验结果 ──
    doc.add_paragraph("实验结果：")
    doc.add_math(
        rf"v' = \bar{{v}} \pm \Delta v = "
        rf"({r['v_meas']:.3f} \pm {r['u_v']:.3f})\,\mathrm{{m/s}}"
    )

    # ── 相对误差 ──
    doc.add_paragraph("相对误差：")
    doc.add_math(
        rf"E = \left|\frac{{v - \bar{{v}}}}{{v}}\right| \cdot "
        rf"100\% = {r['E']:.3f}\%"
    )


def _generate_docx(data: dict, output_path: str):
    """读取 data.json 数据，计算并生成 Word 实验报告。"""

    # ── 1. 读取数据（含必填空值校验） ──
    labels = {
        "f": "谐振频率 f / kHz",
        "t": "室温 t / °C",
        "L1": "表1 L_i（共振干涉法）",
        "L2": "表2 L_i（位相比较法）",
    }
    missing = []
    for k in ("f", "t", "L1", "L2"):
        v = data.get(k)
        if v is None or (isinstance(v, list) and any(x is None for x in v)):
            missing.append(labels[k])
    if missing:
        print("以下必填数据未填写，请补齐后重新运行：")
        for m in missing:
            print(f"  - {m}")
        return

    # ── 2. 计算 ──
    r = _compute(data)
    r1, r2 = r["m1"], r["m2"]
    t_celsius = r["t"]

    # 控制台输出
    print(f"Resonance: lambda = {r1['lambda_bar']:.3f} mm, "
          f"v = {r1['v_meas']:.3f} m/s, dv = {r1['u_v']:.3f} m/s, "
          f"E = {r1['E']:.3f}%")
    print(f"Phase:     lambda = {r2['lambda_bar']:.3f} mm, "
          f"v = {r2['v_meas']:.3f} m/s, dv = {r2['u_v']:.3f} m/s, "
          f"E = {r2['E']:.3f}%")
    print(f"v_theory  = {r1['v_theory']:.3f} m/s "
          f"(t = {t_celsius} C, T = {r1['T_kelvin']:.2f} K)")

    # ── 3. 生成 docx ──
    doc = DocxReportWriter(output_path)

    # ════════════════════════════════════════
    # 零、实验标题
    # ════════════════════════════════════════
    doc.add_title("空气中声速的测量实验")
    doc.add_student_info()

    # ── 变体组合：实验原理 / 实验方法（存在 variants.json 且应用传入选择时生效）──
    variants = compose(SCRIPT_DIR, r)
    if "实验原理" in variants:
        doc.add_heading("实验原理", level=1)
        doc.add_paragraph_rich(variants["实验原理"])
    if "实验方法" in variants:
        doc.add_heading("实验方法", level=1)
        doc.add_paragraph_rich(variants["实验方法"])

    # ════════════════════════════════════════
    # 一、原始数据提交（拍照上传）
    # ════════════════════════════════════════
    doc.add_heading("一、原始数据提交（拍照上传）", level=1)
    doc.add_paragraph("请在下方粘贴原始数据记录照片。")

    # ════════════════════════════════════════
    # 二、数据处理
    # ════════════════════════════════════════
    doc.add_heading("二、数据处理", level=1)

    # （一）共振干涉法
    doc.add_heading("（一）共振干涉法", level=2)
    _write_method_section(doc, r1, "3-6-1")

    # （二）位相比较法
    doc.add_heading("（二）位相比较法", level=2)
    _write_method_section(doc, r2, "3-6-2")

    # ════════════════════════════════════════
    # 三、实验结果分析
    # ════════════════════════════════════════
    doc.add_heading("三、实验结果分析", level=1)

    # 理论值
    doc.add_paragraph("在室温 ")
    doc.add_inline_math(rf"t = {t_celsius}\,^\circ\mathrm{{C}}")
    doc.add_run(" 条件下，理论声速为 ")
    doc.add_inline_math(rf"v_{{\text{{理论}}}} = {r1['v_theory']:.1f}\,\mathrm{{m/s}}")
    doc.add_run("。")

    # 共振干涉法结果
    doc.add_paragraph("共振干涉法测得声速为 ")
    doc.add_inline_math(
        rf"v' = ({r1['v_meas']:.2f} \pm {r1['u_v']:.2f})\,\mathrm{{m/s}}"
    )
    doc.add_run("，相对误差 ")
    doc.add_inline_math(rf"E_1 = {r1['E']:.2f}\%")
    doc.add_run("。")

    # 位相比较法结果
    doc.add_paragraph("位相比较法测得声速为 ")
    doc.add_inline_math(
        rf"v' = ({r2['v_meas']:.2f} \pm {r2['u_v']:.2f})\,\mathrm{{m/s}}"
    )
    doc.add_run("，相对误差 ")
    doc.add_inline_math(rf"E_2 = {r2['E']:.2f}\%")
    doc.add_run("。")

    # 比较两种方法
    better = "共振干涉法" if r1['E'] < r2['E'] else "位相比较法"
    worse = "位相比较法" if r1['E'] < r2['E'] else "共振干涉法"
    doc.add_paragraph(
        f"对比两种方法，{better}的测量精度更高"
        f"（E = {min(r1['E'], r2['E']):.2f}%）。{worse}误差稍大，"
        f"可能是由于李萨如图形判断同/反相点时人眼分辨率有限，"
        f"引入额外的读数误差。总体而言，两种方法测量结果均与理论值"
        f"基本吻合。"
    )
    doc.add_paragraph("验证了 ")
    doc.add_inline_math(r"v = \lambda f")
    doc.add_run(" 关系式以及逐差法处理数据的有效性。")

    # 偏差分析 - 共振
    delta1 = abs(r1['v_theory'] - r1['v_meas'])
    if delta1 <= r1['u_v']:
        doc.add_paragraph("共振干涉法测量值在不确定度范围内与理论值一致。")
    else:
        doc.add_paragraph("共振干涉法测量值与理论值偏差 ")
        doc.add_inline_math(
            rf"|v_{{\text{{理论}}}} - v'| = {delta1:.1f}\,\mathrm{{m/s}}"
        )
        doc.add_run("，超出不确定度范围，可能存在系统误差。")

    # 偏差分析 - 位相
    delta2 = abs(r2['v_theory'] - r2['v_meas'])
    if delta2 <= r2['u_v']:
        doc.add_paragraph("位相比较法测量值在不确定度范围内与理论值一致。")
    else:
        doc.add_paragraph("位相比较法测量值与理论值偏差 ")
        doc.add_inline_math(
            rf"|v_{{\text{{理论}}}} - v'| = {delta2:.1f}\,\mathrm{{m/s}}"
        )
        doc.add_run("，超出不确定度范围，可能存在系统误差。")

    # ── 变体组合：误差分析 / 结论（存在 variants.json 且应用传入选择时生效）──
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])
    if "结论" in variants:
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    # ════════════════════════════════════════
    # 四、课后思考题
    # ════════════════════════════════════════
    doc.add_heading("四、课后思考题", level=1)

    doc.add_heading("1. 用共振干涉法和位相比较法测声速有何相同和不同？", level=2)
    doc.add_paragraph(
        "相同：都是基于声波在空气中传播的原理进行测量，"
        "通过测量声波传播的时间或频率来计算声速。"
    )
    doc.add_paragraph("不同：")
    doc.add_paragraph(
        "① 共振干涉法：通过测量声波在管道或腔体内的共振频率来确定声速，"
        "利用声波与腔体内壁反射后形成的干涉现象来测量声速。"
    )
    doc.add_paragraph(
        "② 位相比较法：通过测量两个声波信号之间的相位差来计算声速，"
        "通常用频率较稳定的信号源和精确计时设备来实现。"
    )

    doc.add_heading(
        "2. 声速测量实验中，定性分析共振法测量时声压振幅极大值"
        "随距离变大而减少的原因。", level=2
    )
    doc.add_paragraph(
        "① 能量减小：声波在传播过程中会受到空气和管道等介质的吸收和散射，"
        "导致声波能量逐渐减小，声压振幅减小。"
    )
    doc.add_paragraph(
        "② 波动扩散：声波传播时会发生波动扩散，随着距离增大，"
        "声波波动波束逐渐扩散，导致声波的能量分布在更大的区域内，"
        "从而导致声压振幅减小。"
    )

    # ── 保存 ──
    doc.save()
    doc.close()
    print(f"报告已生成: {output_path}")


# ═══════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════

def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "空气中声速的测量实验.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    _generate_docx(data, DOCX_FILE)


if __name__ == "__main__":
    main()
