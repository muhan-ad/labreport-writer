"""扭摆法测量切变模量 — 数据处理脚本。"""

import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import *
from common.docx_report import DocxReportWriter
from common.variants import compose
from common.data_io import load_data

# ── 物理常数与仪器参数（按教材） ──
N_CYCLES = 30              # 每次测量的周期数
N_TRIALS = 5               # 周期重复测量次数
DELTA_TIMER = 0.01         # 周期测定仪 Δ_仪 (s)
DELTA_MICROMETER = 0.004   # 一级千分尺 Δ_仪 (mm)
DELTA_CALIPER = 0.02       # 游标卡尺 Δ_仪 (mm)，直接作 ΔD1/ΔD2
DELTA_RULER = 0.5          # 米尺 Δ_仪 (mm) → Δl = 0.5/√3 ≈ 0.3 mm

RING_MASS_G = 480          # 圆环质量 (g)，教材给定量，预填入模板


# （方式三：_create_template 已移除，数据真相为 data.json）


def _compute(data: dict) -> dict:
    """由原始数据计算周期、直径、切变模量及其不确定度，返回结果字典。

    无变体时供正文取用（键名与原文局部变量一致）；有变体时作为
    variants.json 中 %%DATA:<key>%% 占位符的数据源。除各中间量外，另以
    ×10¹⁰ 量纲提供 G_10、uG_10，并以百分数提供 E_pct，便于结论/误差章节引用。
    """
    t_disk = [float(v) for v in data["t_disk"]]     # 摆盘 5 次总时间/s
    t_ring = [float(v) for v in data["t_ring"]]     # 摆盘+圆环 5 次总时间/s
    d_zero = float(data["d_zero"])                  # 千分尺零误差/mm
    d_horiz = [float(v) for v in data["d_horiz"]]   # 横向 3 值/mm
    d_vert = [float(v) for v in data["d_vert"]]     # 纵向 3 值/mm
    l_mm = float(data["l_mm"])                      # 钢丝长度/mm
    D1_mm = float(data["D1_mm"])                    # 圆环内径/mm
    D2_mm = float(data["D2_mm"])                    # 圆环外径/mm
    m_g = float(data["m_g"])                        # 圆环质量/g

    # ── 周期与直径 ──
    T0 = mean(t_disk) / N_CYCLES        # 摆盘周期/s
    T = mean(t_ring) / N_CYCLES         # 摆盘+圆环周期/s

    d_s_bar = (mean(d_horiz) + mean(d_vert)) / 2   # 直径视数平均/mm
    d_mm = d_s_bar - d_zero                         # 钢丝直径/mm

    # ── SI 单位 ──
    l = l_mm / 1000
    d = d_mm / 1000
    D1 = D1_mm / 1000
    D2 = D2_mm / 1000
    m = m_g / 1000

    # ── 切变模量计算链 ──
    J1p = m * (D1 ** 2 + D2 ** 2) / 8                  # 圆环转动惯量理论值 kg·m²
    F = 4 * math.pi ** 2 * J1p / (T ** 2 - T0 ** 2)    # 扭转模量 kg·m²·s⁻²
    G = 32 * l * F / (math.pi * d ** 4)                # 切变模量 N/m²

    # ── 不确定度分析 ──
    u_T0 = combine(std_dev(t_disk) / (N_CYCLES * math.sqrt(N_TRIALS)),
                   type_b(DELTA_TIMER))
    u_T = combine(std_dev(t_ring) / (N_CYCLES * math.sqrt(N_TRIALS)),
                  type_b(DELTA_TIMER))
    u_l = type_b(DELTA_RULER)                          # mm
    u_dir_h = combine(type_a(d_horiz), type_b(DELTA_MICROMETER))
    u_dir_v = combine(type_a(d_vert), type_b(DELTA_MICROMETER))
    u_d1 = max(u_dir_h, u_dir_v)                       # mm
    u_d2 = u_d1
    u_d = 0.5 * combine(u_d1, u_d2)                    # mm
    u_F = F * 2 * math.sqrt(T ** 2 * u_T ** 2 + T0 ** 2 * u_T0 ** 2) \
        / (T ** 2 - T0 ** 2)
    u_G = G * math.sqrt((u_F / F) ** 2 + (u_l / 1000 / l) ** 2
                        + 16 * (u_d / 1000 / d) ** 2)
    E = u_G / G

    return {
        "t_disk": t_disk, "t_ring": t_ring,
        "d_zero": d_zero, "d_horiz": d_horiz, "d_vert": d_vert,
        "l_mm": l_mm, "D1_mm": D1_mm, "D2_mm": D2_mm, "m_g": m_g,
        "T0": T0, "T": T, "d_s_bar": d_s_bar, "d_mm": d_mm,
        "l": l, "d": d, "D1": D1, "D2": D2, "m": m,
        "J1p": J1p, "F": F, "G": G,
        "u_T0": u_T0, "u_T": u_T, "u_l": u_l,
        "u_d1": u_d1, "u_d2": u_d2, "u_d": u_d,
        "u_F": u_F, "u_G": u_G, "E": E,
        # 变体 %%DATA 用：G 以 ×10¹⁰ 量纲、相对误差以百分数给出（量纲匹配）
        "G_10": G / 1e10, "uG_10": u_G / 1e10, "E_pct": E * 100,
    }


def _generate_docx(data: dict, output_path: str):
    """从 data.json 读取数据，计算并生成 Word 实验报告。"""

    # ═══════════════════════════════════════════════
    # 1. 读取数据（含空值校验）
    # ═══════════════════════════════════════════════
    # 校验必填数据（required 字段为 null 或 array 含 null → 缺失）
    missing = []
    for k in ("t_disk", "t_ring", "d_zero", "d_horiz", "d_vert",
              "l_mm", "D1_mm", "D2_mm", "m_g"):
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

    # 解包供正文使用（沿用原有变量名，保证无变体时输出与之前完全一致）
    T0, T = r["T0"], r["T"]
    d_mm, l_mm = r["d_mm"], r["l_mm"]
    l, d, D1, D2, m = r["l"], r["d"], r["D1"], r["D2"], r["m"]
    J1p, F, G = r["J1p"], r["F"], r["G"]
    u_T0, u_T, u_l = r["u_T0"], r["u_T"], r["u_l"]
    u_d1, u_d, u_F, u_G, E = r["u_d1"], r["u_d"], r["u_F"], r["u_G"], r["E"]

    # ── 控制台输出中间量（GBK 控制台，单位用 ASCII 写法） ──
    print(f"T0 = {T0:.3f} s, T = {T:.3f} s")
    print(f"d = {d_mm:.3f} mm, l = {l_mm:.1f} mm")
    print(f"dT0 = {u_T0:.4f} s, dT = {u_T:.4f} s")
    print(f"dd1 = dd2 = {u_d1:.4f} mm, dd = {u_d:.4f} mm, dl = {u_l:.2f} mm")
    print(f"J1' = {J1p:.4e} kg*m^2, F = {F:.4e} kg*m^2*s^-2")
    print(f"dF = {u_F:.3e}")
    print(f"G = {G:.4e} N/m^2, dG = {u_G:.3e}, E = {E * 100:.2f}%")

    # ═══════════════════════════════════════════════
    # 5. 生成 docx 报告
    # ═══════════════════════════════════════════════
    doc = DocxReportWriter(output_path)

    # ── 零、实验标题 ──
    doc.add_title("扭摆法测量切变模量实验")
    doc.add_student_info()

    # ── 变体组合：实验原理 / 实验方法（有 variants.json 且应用传入选择时生效）──
    variants = compose(SCRIPT_DIR, r)
    if "实验原理" in variants:
        doc.add_heading("实验原理", level=1)
        doc.add_paragraph_rich(variants["实验原理"])
    if "实验方法" in variants:
        doc.add_heading("实验方法", level=1)
        doc.add_paragraph_rich(variants["实验方法"])

    # ── 一、原始数据提交（拍照上传） ──
    doc.add_heading("一、原始数据提交（拍照上传）", level=1)
    doc.add_paragraph("请在下方粘贴原始数据记录照片。")

    # ── 二、切变模量计算原理 ──
    doc.add_heading("二、切变模量计算原理", level=1)

    doc.add_paragraph("设钢丝的扭转模量为 F，作用力矩为 M，根据 F 的定义有")
    doc.add_math(r"M = F \cdot \theta \text{  (1)}")
    doc.add_paragraph("设钢丝和载物圆台沿正轴心的转动惯量为 J₀，根据牛顿力学的转动定理有")
    doc.add_math(r"M = -J_{0} \cdot \frac{d^{2}\theta}{dt^{2}} \text{  (2)}")
    doc.add_paragraph("式中，负号表示恢复力矩 M 始终与 θ 反向。将式（1）代入式（2）可得")
    doc.add_math(r"\frac{d^{2}\theta}{dt^{2}} = -\frac{F}{J_{0}}\theta \text{  (3)}")
    doc.add_paragraph("可见，圆台将围绕 θ=0 的点作简谐扭转摆动，"
                      "解微分方程式（3）可得其扭转运动周期 T₀ 为")
    doc.add_math(r"T_{0} = 2\pi\sqrt{\frac{J_{0}}{F}} \text{  (4)}")
    doc.add_paragraph("因此，可求出圆台的转动惯量为")
    doc.add_math(r"J_{0} = \frac{F \cdot T_{0}^{2}}{4\pi^{2}} \text{  (5)}")
    doc.add_paragraph("由于转动惯量遵从叠加原理，故可用载物圆台扭摆法测量其他物体的转动惯量。"
                      "将圆环同心地装于圆台上，测得系统的转动周期为 T，"
                      "可得系统的转动惯量 J 为")
    doc.add_math(r"J = \frac{F \cdot T^{2}}{4\pi^{2}} \text{  (6)}")
    doc.add_paragraph("圆环的转动惯量 J₁ 为")
    doc.add_math(r"J_{1} = J - J_{0} \text{  (7)}")
    doc.add_paragraph("圆环的转动惯量的理论计算值为")
    doc.add_math(r"J_{1}′ = \frac{1}{8}m(D_{1}^{2} + D_{2}^{2}) \text{  (8)}")
    doc.add_paragraph("式中，m 为圆环质量，D₁ 和 D₂ 分别为圆环的内、外直径。"
                      "结合式（5）~式（8），则根据已测知的 T、T₀，"
                      "即可计算出扭转模量 F：")
    doc.add_math(r"F = \frac{4\pi^{2}}{T^{2} - T_{0}^{2}} J_{1}′ \text{  (9)}")
    doc.add_paragraph("切变模量和扭转模量的关系式如下：")
    doc.add_math(r"F = \frac{\pi \cdot d^{4}}{32l}G \text{  (10)}")
    doc.add_paragraph("其中，d 为钢丝直径，l 为钢丝长度。"
                      "进而利用式（9）和式（10），可由钢丝的扭转模量 F 计算出切变模量 G：")
    doc.add_math(r"G = \frac{128\pi l}{d^{4}(T^{2} - T_{0}^{2})} J_{1}′ = "
                 r"\frac{16\pi lm}{d^{4}(T^{2} - T_{0}^{2})}(D_{1}^{2} + D_{2}^{2}) "
                 r"\text{  (11)}")

    # ── 三、数据处理 ──
    doc.add_heading("三、数据处理", level=1)

    # (1) 切变模量计算
    doc.add_heading("（1）切变模量计算", level=2)
    doc.add_paragraph("圆环的转动惯量的理论计算值为")
    doc.add_math(
        r"J_{1}′ = \frac{1}{8}m(D_{1}^{2} + D_{2}^{2}) = "
        + rf"\frac{{1}}{{8}} \times {m:.3f} \times ({D1:.5f}^{{2}} + {D2:.5f}^{{2}}) = "
        + format_scientific(J1p, 4) + r"\,\mathrm{kg·m²}"
    )
    doc.add_paragraph("计算可得扭转模量 F：")
    doc.add_math(
        r"F = \frac{4\pi^{2}}{T^{2} - T_{0}^{2}} J_{1}′ = "
        + rf"\frac{{4\pi^{{2}}}}{{{T:.3f}^{{2}} - {T0:.3f}^{{2}}}} \times "
        + format_scientific(J1p, 4) + " = "
        + format_scientific(F, 4) + r"\,\mathrm{kg·m²·s⁻²}"
    )
    doc.add_paragraph("切变模量 G：")
    doc.add_math(
        r"G = \frac{32lF}{\pi \cdot d^{4}} = "
        + rf"\frac{{32 \times {l:.4f} \times {format_scientific(F, 4)}}}"
        + rf"{{\pi \times ({d_mm:.3f} \times 10^{{-3}})^{{4}}}} = "
        + format_scientific(G, 4) + r"\,\mathrm{N/m²}"
    )

    # (2) 切变模量不确定度
    doc.add_heading("（2）切变模量不确定度", level=2)

    doc.add_paragraph("l 的不确定度（米尺单次测量，仅 B 类）：")
    doc.add_math(
        r"\Delta l = \Delta x_{B} = \frac{\Delta x_{\text{仪}}}{\sqrt{3}} = "
        + rf"{u_l:.1f}\,\mathrm{{mm}}"
    )

    doc.add_paragraph("T₀ 的不确定度：")
    doc.add_math(
        r"\Delta T_{0} = \sqrt{(\Delta x_{A})^{2} + (\Delta x_{B})^{2}} = "
        r"\sqrt{\sigma_{\overline{T_{0}}}^{2} + "
        r"(\frac{\Delta x_{\text{仪}}}{\sqrt{3}})^{2}} = "
        + rf"{u_T0:.3f}\,\mathrm{{s}}"
    )

    doc.add_paragraph("T 的不确定度：")
    doc.add_math(
        r"\Delta T = \sqrt{(\Delta x_{A})^{2} + (\Delta x_{B})^{2}} = "
        r"\sqrt{\sigma_{\overline{T}}^{2} + "
        r"(\frac{\Delta x_{\text{仪}}}{\sqrt{3}})^{2}} = "
        + rf"{u_T:.3f}\,\mathrm{{s}}"
    )

    doc.add_paragraph("d 的不确定度：")
    doc.add_math(
        r"\Delta d_{1} = \Delta d_{2} = "
        r"\sqrt{(\Delta x_{A})^{2} + (\Delta x_{B})^{2}} = "
        r"\sqrt{\sigma_{\overline{d}}^{2} + "
        r"(\frac{\Delta x_{\text{仪}}}{\sqrt{3}})^{2}} = "
        + rf"{u_d1:.3f}\,\mathrm{{mm}}"
    )
    doc.add_math(
        r"\Delta d = \sqrt{(\frac{1}{2}\Delta d_{1})^{2} + "
        r"(\frac{1}{2}\Delta d_{2})^{2}} = "
        + rf"{u_d:.3f}\,\mathrm{{mm}}"
    )

    doc.add_paragraph("F 的不确定度：")
    doc.add_math(
        r"\Delta F = F \cdot \sqrt{\frac{4T^{2}}{(T^{2} - T_{0}^{2})^{2}}"
        r"(\Delta T)^{2} + \frac{4T_{0}^{2}}{(T^{2} - T_{0}^{2})^{2}}"
        r"(\Delta T_{0})^{2}} = "
        + format_scientific(u_F, 3)
    )

    doc.add_paragraph("G 的不确定度：")
    doc.add_math(
        r"\Delta G = G \cdot \sqrt{(\frac{\Delta F}{F})^{2} + "
        r"(\frac{\Delta l}{l})^{2} + 16(\frac{\Delta d}{d})^{2}} = "
        + format_scientific(u_G, 3)
    )

    doc.add_paragraph("最终计算得：")
    doc.add_math(
        rf"G = ({G / 1e10:.3f} \pm {u_G / 1e10:.3f}) \times 10^{{10}}"
        + r"\,\mathrm{N/m²}"
    )

    # (3) 切变模量误差
    doc.add_heading("（3）切变模量误差", level=2)
    doc.add_paragraph("相对误差：")
    doc.add_math(rf"E = \frac{{\Delta G}}{{G}} = {E * 100:.2f}%")

    # ── 变体组合：误差分析 / 结论（有 variants.json 且应用传入选择时生效）──
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])
    if "结论" in variants:
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    # ── 四、问题讨论 ──
    doc.add_heading("四、问题讨论", level=1)

    doc.add_heading("1. 扭摆在转动过程中受到哪些阻尼作用？有什么影响？", level=2)
    doc.add_paragraph("答：扭摆在转动过程中受到的阻尼有空气阻尼和转轴间的摩擦阻尼。")
    doc.add_paragraph("")
    doc.add_run("周期 ")
    doc.add_inline_math(r"T_{0} = 2\pi\sqrt{\frac{J_{0}}{F}}")
    doc.add_run("，其中 ")
    doc.add_inline_math(r"J_{0}")
    doc.add_run("、F 为常量，故周期将会保持不变，扭摆所受的阻尼对实验没有影响。")

    doc.add_heading("2. 扭摆的转动周期是否与转动角度有关？选择多大转角合适？", level=2)
    doc.add_paragraph("")
    doc.add_run("答：周期 ")
    doc.add_inline_math(r"T_{0} = 2\pi\sqrt{\frac{J_{0}}{F}}")
    doc.add_run("，与转动角度无关。")
    doc.add_paragraph("为提供充足的初始势能，同时提高周期测量的准确度，"
                      "转角在 60~90° 左右为宜。")

    doc.add_heading("3. 实验中，对扭摆装置中钢丝的长度和直径有何要求？", level=2)
    doc.add_paragraph("")
    doc.add_run("答：为了满足切变模量公式 ")
    doc.add_inline_math(r"F = \frac{\pi \cdot d^{4}}{32l}G")
    doc.add_run("，钢丝长度 l 应满足 ")
    doc.add_inline_math(r"l \gg 4r")
    doc.add_run("，且钢丝直径应分布均匀。")

    # ── 保存 ──
    doc.save()
    doc.close()
    print(f"报告已生成: {output_path}")


def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "扭摆法测量切变模量实验.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    _generate_docx(data, DOCX_FILE)


if __name__ == "__main__":
    main()
