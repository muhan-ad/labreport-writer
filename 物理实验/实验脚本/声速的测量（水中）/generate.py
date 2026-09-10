"""水中声速的测量 — 数据处理脚本。

方法：共振干涉法（驻波法） + 位相比较法（李萨如图形法）

理论模型（来源：rag/原理.md 水中声速实验数据报告）：纯水中的声速
随水温在极大值附近呈抛物型经验关系
    v = 1557 - 0.0245 * (75 - t)^2   (m/s)
常温段随水温单调上升，t = 20 °C 时 v ≈ 1482.9 m/s（与纯水常用值
约 1482 m/s 一致），约为空气中声速的 4.3 倍。相对误差以该水中
理论值为基准计算。
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

# ── 物理常数与仪器参数 ──
V_PEAK = 1557.0     # 水中声速峰值 (m/s)，出现在 t ≈ 75 °C 附近
T_PEAK = 75.0       # 水中声速极大值对应的水温 (°C)
K_WATER = 0.0245    # 抛物型经验公式曲率系数 (m/s/°C^2)
DELTA_F = 0.001     # 频率分辨率 (kHz)
DELTA_X_INST = 0.02 # 声速测定仪（游标卡尺）Δ_仪 (mm)
N_HALF = 6          # 逐差法半组数 (12 个测量值分 6+6)
N_LAMBDA = 6        # λ_i 个数


# （方式三：_create_template 已移除，数据真相为 data.json）


# ═══════════════════════════════════════════════════
# 计算核心
# ═══════════════════════════════════════════════════

def _v_theory_water(t_celsius: float) -> float:
    """水中声速随水温的抛物型经验公式：v = 1557 - 0.0245(75 - t)^2。"""
    return V_PEAK - K_WATER * (T_PEAK - t_celsius) ** 2


def _compute_method(L_values: list[float], f: float, t_celsius: float) -> dict:
    """对一个方法的 12 个位置测量值进行完整计算。

    返回包含所有中间和最终结果的字典。
    """
    # 相邻极大值（同/反相点）间距为半波长，逐差法计算 λ_i
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

    # 水中理论声速（抛物型经验公式）
    v_theory = _v_theory_water(t_celsius)

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

    v_avg = mean([r1["v_meas"], r2["v_meas"]])
    r = {
        "f": f_khz,
        "t": t_celsius,
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
        "v_avg": v_avg,
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
      参数 → 数据表(含 λ_i) → 理论值 → λ̄ → v̄ → Δλ → Δv → v' → E
    """
    L = r["L"]
    lam = r["lambda_vals"]
    lam_bar = r["lambda_bar"]

    # ── 实验参数 ──
    doc.add_paragraph(
        f"水温 t = {r['t']}°C，频率 f = {r['f']:.4f} kHz，"
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
    doc.add_paragraph("该水温下纯水声速理论值（抛物型经验公式）：")
    doc.add_math(
        rf"v = {V_PEAK} - {K_WATER}\left( {T_PEAK} - t \right)^{{2}} = "
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
        rf"({format_number(r['v_meas'], r['u_v'])} \pm {format_number(r['u_v'], r['u_v'])})\,\mathrm{{m/s}}"
    )

    # ── 相对误差 ──
    doc.add_paragraph("相对误差：")
    doc.add_math(
        rf"E = \left|\frac{{v_{{\text{{理论}}}} - \bar{{v}}}}{{v_{{\text{{理论}}}}}}\right| \cdot "
        rf"100\% = {format_percent(r['E'])}\%"
    )


def _generate_docx(data: dict, output_path: str):
    """读取 data.json 数据，计算并生成 Word 实验报告。"""

    # ── 1. 读取数据（含必填空值校验） ──
    labels = {
        "f": "谐振频率 f / kHz",
        "t": "水温 t / °C",
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

    # 控制台输出
    print(f"Resonance: lambda = {r1['lambda_bar']:.3f} mm, "
          f"v = {r1['v_meas']:.3f} m/s, dv = {r1['u_v']:.3f} m/s, "
          f"E = {r1['E']:.3f}%")
    print(f"Phase:     lambda = {r2['lambda_bar']:.3f} mm, "
          f"v = {r2['v_meas']:.3f} m/s, dv = {r2['u_v']:.3f} m/s, "
          f"E = {r2['E']:.3f}%")
    print(f"v_theory  = {r['v_theory']:.3f} m/s "
          f"(water, t = {r['t']} C)")

    # ── 3. 生成 docx ──
    doc = DocxReportWriter(output_path)

    # ════════════════════════════════════════
    # 零、实验标题
    # ════════════════════════════════════════
    doc.add_title("声速的测量（水中）")
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
    _write_method_section(doc, r1, "水中声速的测量（共振干涉法）")

    # （二）位相比较法
    doc.add_heading("（二）位相比较法", level=2)
    _write_method_section(doc, r2, "水中声速的测量（位相比较法）")

    # ════════════════════════════════════════
    # 三、实验结果分析
    # ════════════════════════════════════════
    doc.add_heading("三、实验结果分析", level=1)

    # 理论值
    doc.add_paragraph("在水温 ")
    doc.add_inline_math(rf"t = {r['t']}\,^\circ\mathrm{{C}}")
    doc.add_run(" 条件下，取水中声速抛物型经验公式 ")
    doc.add_inline_math(
        rf"v = {V_PEAK} - {K_WATER}( {T_PEAK} - t )^{{2}}"
    )
    doc.add_run("，理论声速为 ")
    doc.add_inline_math(rf"v_{{\text{{理论}}}} = {r['v_theory']:.1f}\,\mathrm{{m/s}}")
    doc.add_run("。")

    # 共振干涉法结果
    doc.add_paragraph("共振干涉法测得水中声速为 ")
    doc.add_inline_math(
        rf"v' = ({format_number(r1['v_meas'], r1['u_v'])} \pm {format_number(r1['u_v'], r1['u_v'])})\,\mathrm{{m/s}}"
    )
    doc.add_run("，相对误差 ")
    doc.add_inline_math(rf"E_1 = {format_percent(r1['E'])}\%")
    doc.add_run("。")

    # 位相比较法结果
    doc.add_paragraph("位相比较法测得水中声速为 ")
    doc.add_inline_math(
        rf"v' = ({format_number(r2['v_meas'], r2['u_v'])} \pm {format_number(r2['u_v'], r2['u_v'])})\,\mathrm{{m/s}}"
    )
    doc.add_run("，相对误差 ")
    doc.add_inline_math(rf"E_2 = {format_percent(r2['E'])}\%")
    doc.add_run("。")

    # 比较两种方法
    better = "共振干涉法" if r1['E'] < r2['E'] else "位相比较法"
    worse = "位相比较法" if r1['E'] < r2['E'] else "共振干涉法"
    doc.add_paragraph(
        f"对比两种方法，{better}的测量精度更高"
        f"（E = {min(r1['E'], r2['E']):.2f}%）。{worse}误差稍大，"
        f"可能是由于李萨如图形判断同/反相点时人眼分辨率有限，"
        f"引入额外的读数误差。总体而言，两种方法测量结果均与水中"
        f"理论声速基本吻合。"
    )
    doc.add_paragraph("验证了声波在水中传播时 ")
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
        doc.add_run("，超出不确定度范围，可能存在系统误差"
                    "（如水温波动、水中气泡或杂质引入的声速偏离）。")

    # 偏差分析 - 位相
    delta2 = abs(r2['v_theory'] - r2['v_meas'])
    if delta2 <= r2['u_v']:
        doc.add_paragraph("位相比较法测量值在不确定度范围内与理论值一致。")
    else:
        doc.add_paragraph("位相比较法测量值与理论值偏差 ")
        doc.add_inline_math(
            rf"|v_{{\text{{理论}}}} - v'| = {delta2:.1f}\,\mathrm{{m/s}}"
        )
        doc.add_run("，超出不确定度范围，可能存在系统误差"
                    "（如水温波动、水中气泡或杂质引入的声速偏离）。")

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

    doc.add_heading(
        "1. 用共振干涉法和位相比较法测量水中声速有何相同和不同？", level=2)
    doc.add_paragraph(
        "相同：两者都是基于声波在水中传播的波动理论，测出同一频率超声"
        "在水中的波长，再按 v = λf 计算水中声速，所用仪器（声速测定仪、"
        "信号发生器、示波器）与逐差法数据处理也相同。"
    )
    doc.add_paragraph("不同：")
    doc.add_paragraph(
        "① 共振干涉法：以驻波理论为依据，靠监视接收换能器端面上声压"
        "（输出电压幅度）的极大值判断共振，相邻极大值间距为半波长；"
        "对谐振频率的调节与跟踪要求较高。"
    )
    doc.add_paragraph(
        "② 位相比较法：以行波相位传播为依据，用示波器李萨如图形比较"
        "接收信号与发射信号的相位差（φ = 2πl/λ），相位每变化 π（图形"
        "直线斜率交替一次）对应移动半波长；不依赖共振幅度，但凭图形"
        "判相带有一定主观性。"
    )

    doc.add_heading(
        "2. 声速测量实验中，定性分析共振法测量时声压振幅极大值"
        "随距离变大而减少的原因。", level=2
    )
    doc.add_paragraph(
        "① 能量减小：超声波在水中传播时会受到水的吸收（黏性、热传导及"
        "分子弛豫吸收）以及水中微小气泡、杂质的散射，声能沿程逐渐耗散，"
        "导致声压振幅随距离减小。"
    )
    doc.add_paragraph(
        "② 波动扩散：超声波束虽有较好的方向性，仍会随距离逐渐扩散，"
        "声能分布在越来越大的区域上，接收端面处的能量密度降低，声压"
        "振幅随之减小。"
    )
    doc.add_paragraph(
        "③ 此外，两换能器端面间的多次反射并非完全同相叠加，驻波不完全，"
        "也使高级次（较远距离）的振幅极大值逐渐降低。"
    )

    doc.add_heading(
        "3. 为什么测量水中声速时要尽量保持水温稳定？", level=2)
    doc.add_paragraph(
        "水中声速对水温敏感：对经验公式 v = 1557 − 0.0245(75 − t)² 求导，"
        "在 20 °C 附近水温每变化 1 °C，声速变化约 2.7 m/s（约 0.2%）。"
        "频率不变时波长随声速同步改变，若测量过程中水温漂移或不均匀，"
        "12 个位置读数不再等间距，逐差结果出现额外涨落，A 类不确定度被"
        "抬高，且与理论值比较时产生系统偏差。因此实验应尽快完成、避免"
        "手长时间浸入水槽，并记录测量时的水温。"
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
    DOCX_FILE = os.path.join(SCRIPT_DIR, "声速的测量（水中）实验.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    _generate_docx(data, DOCX_FILE)


if __name__ == "__main__":
    main()
