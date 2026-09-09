"""三线摆（刚体转动惯量）— 数据处理脚本。"""

import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import *
from common.docx_report import DocxReportWriter
from common.variants import compose
from common.data_io import load_data

# ── 物理常数与仪器参数（按教材 + 范例） ──
g = 9.8                         # 重力加速度 m/s²
T_FACTOR = 1.14                 # n=5 时 t_0.683 因子
DELTA_RULER = 0.05              # 卷尺 Δ仪 (cm) — r, R, H
DELTA_TIMER = 0.01              # 数字毫秒计 Δ仪 (s) — T₀, T
DELTA_BALANCE = 0.5             # 物理天平 Δ仪 (g) — m₀, m

# 预填已知量（教材值，用户可按实物修改）
M0_G = 622.0                    # 下盘质量/g
M_G = 447.5                     # 圆环质量/g


# （方式三：_create_template 已移除，数据真相为 data.json）


# ── 辅助函数：直接测量量不确定度评定 ──
def _uncertainty_of_direct(data, delta_instrument):
    """直接测量量的完整不确定度评定。

    流程：s → σ = s × t_0.683 → ΔA = σ → ΔB = Δ仪/√3 → Δ = √(ΔA²+ΔB²)
    返回 (u, u_A, u_B, s, sigma)。
    """
    s_val = std_dev(data)
    sigma = s_val * T_FACTOR
    u_A = sigma
    u_B = type_b(delta_instrument, "uniform")
    u = combine(u_A, u_B)
    return u, u_A, u_B, s_val, sigma


# ── 辅助函数：构建偏差表数据 ──
def _deviation_table(data, avg, label_fmt="{:.2f}"):
    """生成 Word 偏差表的 rows。

    返回 3 行数据：测量值行、|Δ| 行、Δ² 行。
    """
    n = len(data)
    deviations = [x - avg for x in data]
    row_vals = [""] + [label_fmt.format(x) for x in data]
    row_deltas = ["|Δ|"] + [f"{abs(d):.{_decimals(abs(d))}f}" for d in deviations]
    row_sq = ["Δ²"] + [f"{d**2:.{_decimals_sq(d**2)}f}" for d in deviations]
    return [row_vals, row_deltas, row_sq]


def _decimals(val):
    """根据数值大小返回合适的小数位数。"""
    if val == 0:
        return 2
    abs_v = abs(val)
    if abs_v < 0.001:
        return 6
    elif abs_v < 0.01:
        return 5
    elif abs_v < 0.1:
        return 4
    else:
        return 3


def _decimals_sq(val):
    """偏差平方值的小数位数。"""
    if val == 0:
        return 2
    abs_v = abs(val)
    if abs_v < 1e-6:
        return 10
    elif abs_v < 1e-4:
        return 8
    elif abs_v < 1e-3:
        return 6
    else:
        return 4


def _compute(data: dict) -> dict:
    """由已知量与 7 组测量值计算平均值、各测量量不确定度、下盘与圆环转动惯量
    及其不确定度、理论值与偏差，返回结果字典 r（纯计算，不产生任何输出）。

    默认（无变体选择）时其全部数值与原 _generate_docx 内联计算完全一致。
    """
    # 已知量
    m0_g = float(data["m0_g"])
    m_g = float(data["m_g"])

    # 7 组测量值（matrix 行序：r、R、T₀、H、d、D、T，各 5 次）
    m = data["measurements"]
    r_vals = [float(v) for v in m[0]]   # cm
    R_vals = [float(v) for v in m[1]]   # cm
    T0_vals = [float(v) for v in m[2]]  # s (周期，已除50)
    H_vals = [float(v) for v in m[3]]   # cm
    d_vals = [float(v) for v in m[4]]   # cm
    D_vals = [float(v) for v in m[5]]   # cm
    T_vals = [float(v) for v in m[6]]   # s (周期，已除50)

    # 平均值
    r_bar = mean(r_vals)
    R_bar = mean(R_vals)
    T0_bar = mean(T0_vals)
    H_bar = mean(H_vals)
    d_bar = mean(d_vals)
    D_bar = mean(D_vals)
    T_bar = mean(T_vals)

    # 不确定度（r, R, H, T₀）
    u_r, u_rA, u_rB, s_r, sig_r = _uncertainty_of_direct(r_vals, DELTA_RULER)
    u_R, u_RA, u_RB, s_R, sig_R = _uncertainty_of_direct(R_vals, DELTA_RULER)
    u_H, u_HA, u_HB, s_H, sig_H = _uncertainty_of_direct(H_vals, DELTA_RULER)
    u_T0, u_T0A, u_T0B, s_T0, sig_T0 = _uncertainty_of_direct(T0_vals, DELTA_TIMER)

    # SI 单位转换
    r = r_bar / 100
    R = R_bar / 100
    H = H_bar / 100
    d = d_bar / 100
    D = D_bar / 100
    m0 = m0_g / 1000
    m_si = m_g / 1000
    u_m0 = DELTA_BALANCE / 1000   # 质量仅 B 类，直接用 Δ仪（g→kg）

    # 核心结果计算
    common_factor = (g * r * R) / (4 * math.pi ** 2 * H)
    I0 = common_factor * m0 * T0_bar ** 2                       # 下盘转动惯量
    I_exp = common_factor * ((m_si + m0) * T_bar ** 2 - m0 * T0_bar ** 2)  # 圆环实验值
    I_theory = (1 / 8) * m_si * (d ** 2 + D ** 2)               # 圆环理论值

    # I₀ 相对不确定度
    rel_u_m0 = u_m0 / m0
    rel_u_r = u_r / r_bar
    rel_u_R = u_R / R_bar
    rel_u_H = u_H / H_bar
    rel_u_T0 = 2 * u_T0 / T0_bar
    rel_u_I0 = math.sqrt(rel_u_m0 ** 2 + rel_u_r ** 2 + rel_u_R ** 2 +
                          rel_u_H ** 2 + rel_u_T0 ** 2)
    u_I0 = rel_u_I0 * I0

    # 圆环不确定度：|I_exp - I_theory|
    delta_I = abs(I_exp - I_theory)
    rel_error = delta_I / I_theory * 100

    return {
        "m0_g": m0_g, "m_g": m_g,
        "r_vals": r_vals, "R_vals": R_vals, "T0_vals": T0_vals,
        "H_vals": H_vals, "d_vals": d_vals, "D_vals": D_vals, "T_vals": T_vals,
        "r_bar": r_bar, "R_bar": R_bar, "T0_bar": T0_bar, "H_bar": H_bar,
        "d_bar": d_bar, "D_bar": D_bar, "T_bar": T_bar,
        "u_r": u_r, "u_rA": u_rA, "u_rB": u_rB, "s_r": s_r, "sig_r": sig_r,
        "u_R": u_R, "u_RA": u_RA, "u_RB": u_RB, "s_R": s_R, "sig_R": sig_R,
        "u_H": u_H, "u_HA": u_HA, "u_HB": u_HB, "s_H": s_H, "sig_H": sig_H,
        "u_T0": u_T0, "u_T0A": u_T0A, "u_T0B": u_T0B, "s_T0": s_T0, "sig_T0": sig_T0,
        "r": r, "R": R, "H": H, "d": d, "D": D,
        "m0": m0, "m": m_si, "u_m0": u_m0,
        "common_factor": common_factor,
        "I0": I0, "I_exp": I_exp, "I_theory": I_theory,
        "rel_u_I0": rel_u_I0, "rel_u_I0_pct": rel_u_I0 * 100, "u_I0": u_I0,
        "delta_I": delta_I, "rel_error": rel_error,
        # 以 10⁻³ kg·m² 为量纲的换算值，供变体正文以 nicer 科学计数法引用
        "I0_m3": I0 * 1e3, "u_I0_m3": u_I0 * 1e3,
        "I_exp_m3": I_exp * 1e3, "I_theory_m3": I_theory * 1e3,
        "delta_I_m3": delta_I * 1e3,
    }


def _generate_docx(data: dict, output_path: str):
    """从 data.json 读取数据，计算并生成 Word 实验报告。"""

    # ═══════════════════════════════════════════════
    # 1. 读取数据（含空值校验）
    # ═══════════════════════════════════════════════
    # 校验必填数据（required 字段为 null 或 matrix 含 null → 缺失）
    def _flat(v):
        if isinstance(v, list) and v and isinstance(v[0], list):
            return [x for row in v for x in row]
        return v if isinstance(v, list) else [v]

    missing = []
    for k in ("m0_g", "m_g", "measurements"):
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

    # ═══════════════════════════════════════════════
    # 2. 数据处理：平均值、不确定度、转动惯量与偏差（见 _compute）
    # ═══════════════════════════════════════════════
    res = _compute(data)
    m0_g = res["m0_g"]; m_g = res["m_g"]
    r_vals = res["r_vals"]; R_vals = res["R_vals"]; T0_vals = res["T0_vals"]
    H_vals = res["H_vals"]; d_vals = res["d_vals"]; D_vals = res["D_vals"]; T_vals = res["T_vals"]
    r_bar = res["r_bar"]; R_bar = res["R_bar"]; T0_bar = res["T0_bar"]; H_bar = res["H_bar"]
    d_bar = res["d_bar"]; D_bar = res["D_bar"]; T_bar = res["T_bar"]
    u_r = res["u_r"]; u_rA = res["u_rA"]; u_rB = res["u_rB"]; s_r = res["s_r"]; sig_r = res["sig_r"]
    u_R = res["u_R"]; u_RA = res["u_RA"]; u_RB = res["u_RB"]; s_R = res["s_R"]; sig_R = res["sig_R"]
    u_H = res["u_H"]; u_HA = res["u_HA"]; u_HB = res["u_HB"]; s_H = res["s_H"]; sig_H = res["sig_H"]
    u_T0 = res["u_T0"]; u_T0A = res["u_T0A"]; u_T0B = res["u_T0B"]; s_T0 = res["s_T0"]; sig_T0 = res["sig_T0"]
    m0 = res["m0"]; m = res["m"]; u_m0 = res["u_m0"]
    common_factor = res["common_factor"]
    I0 = res["I0"]; I_exp = res["I_exp"]; I_theory = res["I_theory"]
    rel_u_I0 = res["rel_u_I0"]; u_I0 = res["u_I0"]
    delta_I = res["delta_I"]; rel_error = res["rel_error"]
    # 以下 SI 量在报告中以平均值（cm）表述，SI 值仅供变体引用
    r = res["r"]; R = res["R"]; H = res["H"]; d = res["d"]; D = res["D"]

    # 3σ 坏值检验（仅控制台）
    for name, vals, s3 in [("r", r_vals, 3 * sig_r), ("R", R_vals, 3 * sig_R),
                            ("H", H_vals, 3 * sig_H), ("T₀", T0_vals, 3 * sig_T0)]:
        bad = [i + 1 for i, x in enumerate(vals) if abs(x - mean(vals)) >= s3]
        if bad:
            print(f"警告：{name} 第 {bad} 次测量超过 3*sigma(={s3:.4f})，可能为坏值")

    # ═══════════════════════════════════════════════
    # 7. 控制台输出
    # ═══════════════════════════════════════════════
    print("=== 三线摆(刚体转动惯量)数据处理 ===")
    print(f"r_avg  = {r_bar:.2f} cm,  u_r  = {u_r:.3f} cm")
    print(f"R_avg  = {R_bar:.2f} cm,  u_R  = {u_R:.3f} cm")
    print(f"T0_avg = {T0_bar:.3f} s,  u_T0 = {u_T0:.4f} s")
    print(f"H_avg  = {H_bar:.2f} cm,  u_H  = {u_H:.3f} cm")
    print(f"d_avg  = {d_bar:.2f} cm,  D_avg = {D_bar:.2f} cm")
    print(f"T_avg  = {T_bar:.3f} s")
    print("---")
    print(f"I0       = {I0:.4e} kg.m2")
    print(f"u_I0     = {u_I0:.3e} kg.m2")
    print(f"I_exp    = {I_exp:.4e} kg.m2")
    print(f"I_theory = {I_theory:.4e} kg.m2")
    print(f"dI       = {delta_I:.3e} kg.m2")
    print(f"relative error = {rel_error:.2f}%")

    # ═══════════════════════════════════════════════
    # 8. 生成 docx 报告
    # ═══════════════════════════════════════════════
    doc = DocxReportWriter(output_path)

    # ── 零、实验标题 ──
    doc.add_title("三线摆测量刚体的转动惯量")
    doc.add_student_info()

    # ── 变体组合：实验原理 / 实验方法（存在 variants.json 且应用传入选择时生效）──
    variants = compose(SCRIPT_DIR, res)
    if "实验原理" in variants:
        doc.add_heading("实验原理", level=1)
        doc.add_paragraph_rich(variants["实验原理"])
    if "实验方法" in variants:
        doc.add_heading("实验方法", level=1)
        doc.add_paragraph_rich(variants["实验方法"])

    # ── 一、原始数据记录 ──
    doc.add_heading("一、原始数据记录", level=1)
    doc.add_paragraph("请在下方粘贴原始数据记录照片。")

    # ═══════════════════════════════════════════════
    # ── 二、数据处理 ──
    # ═══════════════════════════════════════════════
    doc.add_heading("二、数据处理", level=1)

    # ── 2.1 下盘转动惯量 I₀ 及不确定度 ──
    doc.add_heading("1. 下盘转动惯量 I₀ 及不确定度", level=2)

    doc.add_paragraph("下盘转动惯量公式为")
    doc.add_math(r"I_{0} = \frac{m_{0} g \bar{r} \bar{R}}{4\pi^{2} \bar{H}} "
                 r"\bar{T}_{0}^{2}")

    doc.add_paragraph("代入数据：")
    doc.add_math(
        r"\bar{I_{0}} = \frac{" + f"{m0:.3f}" + r" \times "
        + f"{g}" + r" \times " + f"{r_bar:.2f}" + r" \times "
        + f"{R_bar:.2f}" + r"}"
        + r"{4\pi^{2} \times " + f"{H_bar:.2f}" + r"} \times "
        + f"{T0_bar:.3f}" + r"^{2}"
        + r" \approx " + format_scientific(I0, 3)
        + r"\,\mathrm{kg·m²}"
    )

    doc.add_paragraph("相对不确定度公式：")
    doc.add_math(
        r"\frac{\Delta I_{0}}{I_{0}} = "
        r"\sqrt{\left(\frac{\Delta m_{0}}{m_{0}}\right)^{2}"
        r" + \left(\frac{\Delta r}{r}\right)^{2}"
        r" + \left(\frac{\Delta R}{R}\right)^{2}"
        r" + \left(\frac{\Delta H}{H}\right)^{2}"
        r" + \left(2\frac{\Delta T_{0}}{T_{0}}\right)^{2}}"
    )

    # (1) 已知 Δ仪
    doc.add_paragraph("(1) 已知：")
    doc.add_run("Δm₀ = 0.5 g，卷尺 Δ")
    doc.add_inline_math(r"\Delta_{\text{仪}} = 0.5\,\mathrm{mm}")
    doc.add_run("，秒表 Δ")
    doc.add_inline_math(r"\Delta_{\text{仪}}' = 0.01\,\mathrm{s}")
    doc.add_paragraph("")

    # (2) Δr
    doc.add_paragraph("(2) 对于 Δr：")
    _write_deviation_section(doc, r_vals, r_bar, u_r, u_rA, u_rB, s_r,
                              sig_r, DELTA_RULER, "r", "cm")

    # (3) ΔR
    doc.add_paragraph("(3) 对于 ΔR：")
    _write_deviation_section(doc, R_vals, R_bar, u_R, u_RA, u_RB, s_R,
                              sig_R, DELTA_RULER, "R", "cm")

    # (4) ΔH
    doc.add_paragraph("(4) 对于 ΔH：")
    _write_deviation_section(doc, H_vals, H_bar, u_H, u_HA, u_HB, s_H,
                              sig_H, DELTA_RULER, "H", "cm")

    # (5) ΔT₀
    doc.add_paragraph("(5) 对于 ΔT₀：")
    _write_deviation_section(doc, T0_vals, T0_bar, u_T0, u_T0A, u_T0B, s_T0,
                              sig_T0, DELTA_TIMER, "T_{0}", "s")

    # 代入相对不确定度
    doc.add_paragraph("代入相对不确定度公式：")
    doc.add_math(
        r"\frac{\Delta I_{0}}{I_{0}} = "
        r"\sqrt{\left(\frac{" + f"{DELTA_BALANCE}" + r"}{" + f"{m0_g:.1f}" + r"}\right)^{2}"
        r" + \left(\frac{" + f"{u_r:.3f}" + r"}{" + f"{r_bar:.2f}" + r"}\right)^{2}"
        r" + \left(\frac{" + f"{u_R:.3f}" + r"}{" + f"{R_bar:.2f}" + r"}\right)^{2}"
        r" + \left(\frac{" + f"{u_H:.3f}" + r"}{" + f"{H_bar:.2f}" + r"}\right)^{2}"
        r" + \left(2 \times \frac{" + f"{u_T0:.3f}" + r"}{" + f"{T0_bar:.3f}" + r"}\right)^{2}}"
        r" \approx " + f"{rel_u_I0:.3f}"
    )

    doc.add_paragraph("则")
    doc.add_math(
        r"\Delta \bar{I_{0}} = \frac{\Delta I_{0}}{I_{0}} \bar{I_{0}} = "
        + f"{rel_u_I0:.3f}" + r" \times " + format_scientific(I0, 3)
        + r" \approx " + format_scientific(u_I0, 2)
        + r"\,\mathrm{kg·m²}"
    )

    # I₀ 结果表达
    doc.add_paragraph("下盘转动惯量测量结果：")
    i0_power = int(math.floor(math.log10(I0)))
    i0_mantissa = I0 / 10 ** i0_power
    di0_mantissa = u_I0 / 10 ** i0_power
    doc.add_math(
        r"I_{0} = \bar{I_{0}} \pm \Delta \bar{I_{0}} = ("
        + f"{i0_mantissa:.2f}" + r" \pm " + f"{di0_mantissa:.2f}"
        + r") \times 10^{" + f"{i0_power}" + r"}\,\mathrm{kg·m²}"
    )

    # ── 2.2 圆环转动惯量 I 的计算 ──
    doc.add_heading("2. 圆环转动惯量 I 的计算", level=2)

    doc.add_paragraph("圆环转动惯量实验值为")
    doc.add_math(
        r"\bar{I} = \frac{g \bar{r} \bar{R}}{4\pi^{2} \bar{H}} "
        r"\left[(m + m_{0})\bar{T}^{2} - m_{0}\bar{T_{0}}^{2}\right]"
    )
    doc.add_paragraph("代入数据：")
    doc.add_math(
        r"\bar{I} = \frac{" + f"{g}" + r" \times " + f"{r_bar:.2f}"
        + r" \times " + f"{R_bar:.2f}" + r"}"
        + r"{4\pi^{2} \times " + f"{H_bar:.2f}" + r"} \times \Big[("
        + f"{m:.3f}" + r" + " + f"{m0:.3f}" + r") \times "
        + f"{T_bar:.3f}" + r"^{2} - " + f"{m0:.3f}" + r" \times "
        + f"{T0_bar:.3f}" + r"^{2}\Big]"
        + r" \approx " + format_scientific(I_exp, 3)
        + r"\,\mathrm{kg·m²}"
    )

    doc.add_paragraph("圆环绕中心轴的转动惯量理论公式为")
    doc.add_math(r"I_{\text{理论}} = \frac{1}{8}m(d^{2} + D^{2})")
    doc.add_paragraph("代入数据：")
    doc.add_math(
        r"I_{\text{理论}} = \frac{1}{8} \times " + f"{m:.3f}"
        + r" \times (" + f"{d_bar:.2f}" + r"^{2} + "
        + f"{D_bar:.2f}" + r"^{2})"
        + r" \approx " + format_scientific(I_theory, 3)
        + r"\,\mathrm{kg·m²}"
    )

    doc.add_paragraph("则圆环转动惯量实验值与理论值的偏差为")
    doc.add_math(
        r"\Delta \bar{I} = |\bar{I} - I_{\text{理论}}| = "
        + f"{delta_I:.2e}" + r"\,\mathrm{kg·m²}"
    )

    doc.add_paragraph("圆环转动惯量结果表达：")
    i_power = int(math.floor(math.log10(I_exp)))
    i_mantissa = I_exp / 10 ** i_power
    di_mantissa = delta_I / 10 ** i_power
    doc.add_math(
        r"I = \bar{I} \pm \Delta \bar{I} = ("
        + f"{i_mantissa:.2f}" + r" \pm " + f"{di_mantissa:.2f}"
        + r") \times 10^{" + f"{i_power}" + r"}\,\mathrm{kg·m²}"
    )

    # ═══════════════════════════════════════════════
    # ── 三、实验结果分析 ──
    # ═══════════════════════════════════════════════
    doc.add_heading("三、实验结果分析", level=1)

    doc.add_heading("1. 误差", level=2)
    doc.add_paragraph(
        "①摆线问题：器材使用时间较久，摆线的材质、粗细和弹性不均匀"
        "可能导致摆动过程中的阻力和弹性势能的变化，从而影响实验结果。"
    )
    doc.add_paragraph(
        "②扭振周期测量误差：使用秒表计时容易因人的反应时间导致误差。"
    )
    doc.add_paragraph(
        "③空气阻力：空气阻力会影响摆动的周期和幅度，从而影响实验结果。"
    )
    doc.add_paragraph(
        "④读数误差：使用卷尺测量时，读数误差不可避免。"
    )

    doc.add_heading("2. 不足", level=2)
    doc.add_paragraph(
        "实验时因对仪器不熟悉，导致调试仪器时所用时间过久。"
    )

    # ── 变体组合：误差分析 / 结论（存在 variants.json 且应用传入选择时生效）──
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])
    if "结论" in variants:
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    # ═══════════════════════════════════════════════
    # ── 四、问题讨论 ──
    # ═══════════════════════════════════════════════
    doc.add_heading("四、问题讨论", level=1)

    doc.add_paragraph(
        "1. 实验中转动惯量公式中的 R 是否为下圆盘半径？其数值如何测量？"
    )
    doc.add_paragraph("")
    doc.add_run("答：不是，R 是下盘圆心到悬挂点的距离。"
                 "测量方法：三悬点组成一个等边三角形，设其边长为 L，"
                 "则 R 等于其外接圆的半径，测量出 L 的长度后，")
    doc.add_inline_math(r"R = \frac{L}{\sqrt{3}}")
    doc.add_run("，通过计算即可得到 R 的数值。")

    doc.add_paragraph(
        "2. 当待测物体的转动惯量比下圆盘的转动惯量小得多时，"
        "为何不宜采用三线摆测量？"
    )
    doc.add_paragraph(
        "答：若待测物转动惯量远小于下盘，则加与不加样品时周期变化极小，"
        "T ≈ T₀，公式中差值项接近零，测量误差被放大，灵敏度不足，"
        "会导致误差过多，无法得到理想结果。"
    )

    # ── 保存 ──
    doc.save()
    doc.close()
    print(f"报告已生成: {output_path}")


def _write_deviation_section(doc, data, avg, u, u_A, u_B, s_val, sigma,
                              delta_inst, symbol, unit):
    """输出单个测量量的完整不确定度评定章节（偏差表 → s → σ → 3σ → ΔA,B → Δ）。"""
    n = len(data)

    # 偏差表
    deviations = [x - avg for x in data]
    abs_devs = [abs(d) for d in deviations]
    sq_devs = [d ** 2 for d in deviations]

    headers = [""] + [str(i) for i in range(1, n + 1)]
    # 格式化辅助
    def _fmt_vals(vals, prec):
        return [""] + [f"{x:.{prec}f}" for x in vals]

    # 根据数值大小自适应精度
    mag = max(abs(avg), max(abs_devs)) if max(abs_devs) > 0 else 1
    if mag < 0.01:
        vprec = 3
    elif mag < 0.1:
        vprec = 3
    elif mag < 1:
        vprec = 3
    else:
        vprec = 2

    amag = max(abs_devs) if max(abs_devs) > 0 else 1
    if amag < 0.001:
        dprec = 4
    elif amag < 0.01:
        dprec = 3
    elif amag < 0.1:
        dprec = 3
    else:
        dprec = 2

    smag = max(sq_devs) if max(sq_devs) > 0 else 1
    if smag < 1e-6:
        sprec = 8
    elif smag < 1e-4:
        sprec = 6
    elif smag < 0.001:
        sprec = 5
    else:
        sprec = 4

    rows = [
        [f"${symbol}_i$"] + [f"{x:.{vprec}f}" for x in data],
        [f"$|\\Delta {symbol}_i|$"] + [f"{abs(d):.{dprec}f}" for d in deviations],
        [f"$(\\Delta {symbol}_i)^2$"] + [f"{d**2:.{sprec}f}" for d in deviations],
    ]
    doc.add_table(headers, rows, col_widths=[2.0] + [1.6] * 5)

    # s 公式
    sum_sq_str = " + ".join([f"{d**2:.{sprec}f}" for d in deviations])
    doc.add_paragraph("")
    doc.add_math(
        r"s_{(" + symbol + r")} = "
        r"\sqrt{\frac{1}{" + f"{n - 1}" + r"} \sum_{i=1}^{" + f"{n}"
        + r"} (\Delta " + symbol + r"_i)^{2}} = "
        r"\sqrt{\frac{" + sum_sq_str + r"}{" + f"{n - 1}" + r"}}"
        r" \approx " + f"{s_val:.3f}" + r"\,\mathrm{" + unit + r"}"
    )

    # σ
    doc.add_math(
        r"\sigma = s_{(" + symbol + r")} \times t_{0.683} = "
        + f"{s_val:.3f}" + r" \times " + f"{T_FACTOR}"
        + r" \approx " + f"{sigma:.3f}" + r"\,\mathrm{" + unit + r"}"
    )

    # 3σ
    doc.add_math(r"3\sigma = " + f"{3 * sigma:.3f}" + r"\,\mathrm{" + unit + r"}")

    doc.add_paragraph("经检验，无坏值。")
    doc.add_paragraph("则")

    # ΔA, ΔB
    u_B_val = type_b(delta_inst, "uniform")
    doc.add_math(
        r"\Delta " + symbol + r"_{A} = \sigma = " + f"{u_A:.3f}"
        + r"\,\mathrm{" + unit + r"}, "
        r"\Delta " + symbol + r"_{B} = "
        r"\frac{\Delta_{\text{仪}}}{\sqrt{3}} = "
        r"\frac{" + f"{delta_inst:.2f}" + r"}{\sqrt{3}}"
        r" \approx " + f"{u_B_val:.3f}" + r"\,\mathrm{" + unit + r"}"
    )

    # Δ
    doc.add_math(
        r"\Delta " + symbol + r" = \sqrt{"
        r"\Delta " + symbol + r"_{A}^{2} + "
        r"\Delta " + symbol + r"_{B}^{2}}"
        r" \approx " + f"{u:.3f}" + r"\,\mathrm{" + unit + r"}"
    )


def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "三线摆（刚体转动惯量）实验报告.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    _generate_docx(data, DOCX_FILE)


if __name__ == "__main__":
    main()
