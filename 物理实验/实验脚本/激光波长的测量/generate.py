"""迈克尔逊干涉仪测量激光波长 — 数据处理脚本。"""

import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import *
from common.docx_report import DocxReportWriter
from common.data_io import load_data
from common.variants import compose

# ── 物理常数与仪器参数（按教材 + 范例） ──
LAMBDA_0_MM = 632.8e-6          # He-Ne 激光标准波长 mm（632.8 nm）
DELTA_INST_MM = 5e-5            # 微调手轮 Δ仪 (mm)，可估读到 1e-5 mm
DELTA_INST_STR = r"5 \times 10^{-5}"  # Δ仪 在公式中的显示形式
N_ROWS = 8                      # 测量次数（教材表3-12-1）

# t_0.683 因子表（n ≤ 6 时使用；n > 6 时按范例取 t = 1）
T_TABLE = {2: 1.84, 3: 1.32, 4: 1.20, 5: 1.14, 6: 1.11}

# 预填已知量（教材实验步骤，用户可按实际修改）
N_FRINGES = 50                  # 冒出（缩进）条纹数 N


# （方式三：_create_template 已移除，数据真相为 data.json）


def _round_result(value: float, uncertainty: float):
    """结果表达取位：不确定度进位保留 1 位有效数字，均值对齐到同一位。

    返回 (均值字符串, 不确定度字符串)。
    """
    if uncertainty <= 0:
        return f"{value:.5f}", f"{uncertainty:.5f}"
    exp10 = math.floor(math.log10(uncertainty))
    u_round = math.ceil(uncertainty / 10 ** exp10 - 1e-9) * 10 ** exp10
    decs = max(0, -exp10)
    return f"{value:.{decs}f}", f"{u_round:.{decs}f}"


def _compute(data: dict) -> dict:
    """由 data.json 计算各测量量与不确定度，返回结果字典 r。

    %%DATA:key%% 占位符仅能引用本函数返回的键。
    """
    measurements = [[float(v) for v in row] for row in data["measurements"]]
    l1_vals = [row[0] for row in measurements]
    l2_vals = [row[1] for row in measurements]
    N = float(data["N"])

    # d = |l1 - l2|，3σ 坏值检验
    d_vals = [abs(a - b) for a, b in zip(l1_vals, l2_vals)]
    n_all = len(d_vals)
    d_bar_all = mean(d_vals)
    sigma_all = std_dev(d_vals, ddof=0)
    low = d_bar_all - 3 * sigma_all
    high = d_bar_all + 3 * sigma_all
    bad = [(i + 1, d) for i, d in enumerate(d_vals) if not (low <= d <= high)]
    d_kept = [d for i, d in enumerate(d_vals) if (i + 1, d) not in bad]
    n = len(d_kept)
    d_bar = mean(d_kept)

    # d 的不确定度
    s_val = std_dev(d_kept)
    t_factor = 1.0 if n > 6 else T_TABLE[n]
    u_A = t_factor * s_val / math.sqrt(n)
    u_B = type_b(DELTA_INST_MM, "uniform")
    u_d = combine(u_A, u_B)

    # 波长、相对误差与波长不确定度
    lam_bar = 2 * d_bar / N
    eta = abs(LAMBDA_0_MM - lam_bar) / LAMBDA_0_MM * 100
    u_lam = 2 * u_d / N
    lam_str, u_lam_str = _round_result(lam_bar, u_lam)
    bias_word = "偏大" if lam_bar > LAMBDA_0_MM else "偏小"
    in_range = abs(lam_bar - LAMBDA_0_MM) <= u_lam

    return {
        "measurements": measurements, "l1_vals": l1_vals, "l2_vals": l2_vals,
        "N": N, "d_vals": d_vals, "n_all": n_all, "d_bar_all": d_bar_all,
        "sigma_all": sigma_all, "low": low, "high": high, "bad": bad,
        "d_kept": d_kept, "n": n, "d_bar": d_bar, "s_val": s_val,
        "t_factor": t_factor, "u_A": u_A, "u_B": u_B, "u_d": u_d,
        "lam_bar": lam_bar, "eta": eta, "u_lam": u_lam,
        "lam_str": lam_str, "u_lam_str": u_lam_str,
        "bias_word": bias_word, "in_range": in_range,
        "lambda0_nm": LAMBDA_0_MM * 1e6,
        "lam_bar_nm": lam_bar * 1e6, "u_lam_nm": u_lam * 1e6,
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
    for k in ("measurements", "N"):
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

    # 计算并取出全部结果量（与 variants.json 的 %%DATA:key%% 共用同一字典 r）
    r = _compute(data)
    measurements = r["measurements"]; l1_vals = r["l1_vals"]; l2_vals = r["l2_vals"]
    N = r["N"]; d_vals = r["d_vals"]; n_all = r["n_all"]
    d_bar_all = r["d_bar_all"]; sigma_all = r["sigma_all"]
    low = r["low"]; high = r["high"]; bad = r["bad"]; d_kept = r["d_kept"]
    n = r["n"]; d_bar = r["d_bar"]; s_val = r["s_val"]; t_factor = r["t_factor"]
    u_A = r["u_A"]; u_B = r["u_B"]; u_d = r["u_d"]
    lam_bar = r["lam_bar"]; eta = r["eta"]; u_lam = r["u_lam"]
    lam_str = r["lam_str"]; u_lam_str = r["u_lam_str"]
    bias_word = r["bias_word"]; in_range = r["in_range"]

    # ═══════════════════════════════════════════════
    # 5. 控制台输出
    # ═══════════════════════════════════════════════
    print("=== 迈克尔逊干涉仪测量激光波长 数据处理 ===")
    if bad:
        print(f"3sigma 检验发现坏值：第 {[i for i, _ in bad]} 次测量，已剔除")
    else:
        print("3sigma 检验无坏值")
    print(f"d_bar = {d_bar:.6f} mm (n={n})")
    print(f"s     = {s_val:.6f} mm")
    print(f"u_A   = {u_A:.8f} mm, u_B = {u_B:.7f} mm, u_d = {u_d:.6f} mm")
    print(f"lambda_bar = {lam_bar:.8f} mm")
    print(f"相对误差 = {eta:.2f}%")
    print(f"u_lambda = {u_lam:.8f} mm")
    print(f"结果: lambda = {lam_str} ± {u_lam_str} mm")

    # ═══════════════════════════════════════════════
    # 6. 生成 docx 报告
    # ═══════════════════════════════════════════════
    doc = DocxReportWriter(output_path)

    # ── 零、实验标题 ──
    doc.add_title("激光波长的测量")
    doc.add_student_info()

    # ── 变体组合：实验原理 / 实验方法（存在 variants.json 且应用传入选择时生效）──
    variants = compose(SCRIPT_DIR, r)
    if "实验原理" in variants:
        doc.add_heading("实验原理", level=1)
        doc.add_paragraph_rich(variants["实验原理"])
    if "实验方法" in variants:
        doc.add_heading("实验方法", level=1)
        doc.add_paragraph_rich(variants["实验方法"])

    # ── 一、实验数据记录 ──
    doc.add_heading("一、实验数据记录", level=1)
    doc.add_paragraph("请在下方粘贴原始数据记录照片。")

    # ═══════════════════════════════════════════════
    # ── 二、数据处理 ──
    # ═══════════════════════════════════════════════
    doc.add_heading("二、数据处理", level=1)

    # ── 1. 数据计算 ──
    doc.add_heading("1. 数据计算", level=2)

    doc.add_paragraph("下面根据 3σ 原则对测量数据进行检验。")

    doc.add_paragraph("计算平均值：")
    doc.add_math(
        r"\overline{d} = \frac{1}{n} \sum_{i=1}^{n} d_{i} \approx "
        + f"{d_bar_all:.6f}" + r"\,\mathrm{mm}"
    )

    doc.add_paragraph("计算标准差：")
    doc.add_math(
        r"\sigma = \sqrt{\frac{1}{n} \sum_{i=1}^{n} (d_{i} - \overline{d})^{2}}"
        r" \approx " + f"{sigma_all:.7f}" + r"\,\mathrm{mm}"
    )

    if not bad:
        doc.add_paragraph(
            f"根据 3σ 原则，可接受的最大数据约为 {high:.5f}mm，"
            "则可以认为检验无坏值。"
        )
    else:
        bad_desc = "、".join(f"第 {i} 次测量值 {d:.5f}mm" for i, d in bad)
        doc.add_paragraph(
            f"根据 3σ 原则，可接受的最大数据约为 {high:.5f}mm，"
            f"检验发现{bad_desc}为坏值，予以剔除。剔除后重新计算平均值："
        )
        doc.add_math(
            r"\overline{d} = \frac{1}{n} \sum_{i=1}^{n} d_{i} \approx "
            + f"{d_bar:.6f}" + r"\,\mathrm{mm}"
        )

    doc.add_paragraph("下面对数据进行进一步的处理，根据数据求得标准偏差：")
    doc.add_math(
        r"s = \sqrt{\frac{1}{n-1} \sum_{i=1}^{n} (d_{i} - \overline{d})^{2}}"
        r" \approx " + f"{s_val:.6f}" + r"\,\mathrm{mm}"
    )

    if n > 6:
        doc.add_paragraph(
            "采用 t 分布因子求得标准偏差的最佳估计，由于 n > 6，这里取 t = 1："
        )
    else:
        doc.add_paragraph(
            f"采用 t 分布因子求得标准偏差的最佳估计，n = {n}，"
            f"这里取 t = {t_factor}："
        )
    doc.add_math(
        r"\sigma_{\bar{x}} = \Delta X_{A} = t \cdot \frac{s}{\sqrt{n}}"
        r" \approx " + f"{u_A:.8f}" + r"\,\mathrm{mm}"
    )

    doc.add_paragraph("B类不确定度：")
    doc.add_math(
        r"\Delta X_{B} = \frac{\Delta_{\text{仪}}}{\sqrt{3}}"
        r" = \frac{" + DELTA_INST_STR + r"}{\sqrt{3}}"
        r" \approx " + f"{u_B:.7f}" + r"\,\mathrm{mm}"
    )

    doc.add_paragraph("合成不确定度：")
    doc.add_math(
        r"\Delta X = \sqrt{(\Delta X_{A})^{2} + (\Delta X_{B})^{2}}"
        r" \approx " + f"{u_d:.6f}" + r"\,\mathrm{mm}"
    )

    # ── 2. 计算波长 ──
    doc.add_heading("2. 计算波长", level=2)

    doc.add_paragraph("根据公式：")
    doc.add_math(
        r"\overline{\lambda} = \frac{2\overline{d}}{N} = "
        + f"{lam_bar:.8f}" + r"\,\mathrm{mm}"
    )

    doc.add_paragraph("与标准值 ")
    doc.add_inline_math(r"\lambda_{0} = 632.8\,\mathrm{nm}")
    doc.add_run(" 比较，相对误差为：")
    doc.add_math(
        r"\eta = \frac{|\lambda_{0} - \overline{\lambda}|}{\lambda_{0}}"
        r" \approx " + f"{eta:.2f}" + "%"
    )

    # ── 3. 计算波长的不确定度 ──
    doc.add_heading("3. 计算波长的不确定度", level=2)

    doc.add_paragraph("波长 λ 的不确定度：")
    doc.add_math(
        r"\Delta \lambda = \frac{2 \Delta d}{N} = "
        + f"{u_lam:.8f}" + r"\,\mathrm{mm}"
    )

    doc.add_paragraph("那么，最终的结果表示如下")
    lam_power = math.floor(math.log10(r["lam_bar"]))
    doc.add_math(
        r"\lambda = (" + format_number(r["lam_bar"] / 10 ** lam_power, r["u_lam"] / 10 ** lam_power)
        + r" \pm " + format_number(r["u_lam"] / 10 ** lam_power, r["u_lam"] / 10 ** lam_power)
        + r") \times 10^{" + f"{lam_power}" + r"}\,\mathrm{mm}"
    )

    # ═══════════════════════════════════════════════
    # ── 三、实验结果分析 ──
    # ═══════════════════════════════════════════════
    doc.add_heading("三、实验结果分析", level=1)

    if in_range:
        doc.add_paragraph(
            f"测量值{bias_word}，相对误差为 {eta:.2f}%，"
            "标准值在测量不确定度范围内，测量结果与标准值符合较好。"
            "可能的误差来源包括："
        )
    else:
        doc.add_paragraph(
            f"测量值{bias_word}，相对误差较大（{eta:.2f}%），"
            "且标准值不在测量不确定度范围内，说明存在显著的系统误差。"
            "可能误差来源包括："
        )

    doc.add_paragraph(
        f"1. 条纹计数误差：实验中假定 N={int(N)}，但实际条纹计数可能不准确。"
        "如果由于视觉误差条纹计数偏小，会导致计算出的波长偏大。"
    )
    doc.add_paragraph(
        "2. 仪器误差：空程差，即迈克尔逊干涉仪的微动螺丝存在空程差，"
        "在改变镜子位置时，实际移动距离与读数可能不一致，导致测量值偏差；"
        "镜子不平行，如果两镜不严格垂直，干涉条纹可能不是理想的等倾干涉，"
        "从而引入误差。"
    )
    doc.add_paragraph(
        "3. 测量误差：d 的测量虽然经过 3σ 原则检验，但个别测量值仍可能"
        "由于操作不熟练或环境干扰产生偏差。B 类不确定度主要来源于仪器分辨率，"
        "合成不确定度较小，表明随机误差控制较好。"
    )
    doc.add_paragraph(
        "4. 环境因素：实验过程中，温度波动、振动或气流可能导致干涉条纹抖动，"
        "影响条纹计数和 d 的测量精度。"
    )
    doc.add_paragraph(
        "总体而言，实验流程和数据处理基本合理。不确定度计算表明随机误差较小，"
        "系统误差需进一步消除。"
    )

    # ── 变体组合：误差分析 / 结论（存在 variants.json 且应用传入选择时生效）──
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])
    if "结论" in variants:
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    # ═══════════════════════════════════════════════
    # ── 四、思考题 ──
    # ═══════════════════════════════════════════════
    doc.add_heading("四、思考题", level=1)

    doc.add_paragraph(
        "1. 在什么条件下产生等倾干涉条纹？在什么条件下产生等厚干涉条纹？"
    )
    doc.add_paragraph(
        "答：等倾干涉条纹要求两镜严格垂直，形成同心圆条纹；"
        "等厚干涉条纹要求两镜有微小夹角，形成直线条纹。本实验应追求等倾条件。"
    )

    doc.add_paragraph(
        "2. 迈克尔逊干涉仪产生的等倾干涉条纹与牛顿环有何不同？"
    )
    doc.add_paragraph(
        "答：迈克尔逊干涉仪产生的是等倾干涉，条纹定域在无穷远；"
        "牛顿环是等厚干涉，条纹定域在接触点。"
    )

    doc.add_paragraph(
        "3. 调节迈克尔逊干涉仪时，看到的亮点为什么是两排而不是两个？"
        "两排亮点是怎样形成的？"
    )
    doc.add_paragraph(
        "答：两排亮点是由于分光板和后镜的反射像不重合，"
        "调节时应使两排亮点重合，从而形成干涉条纹。"
    )

    # ── 保存 ──
    doc.save()
    doc.close()
    print(f"报告已生成: {output_path}")


def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "激光波长的测量实验报告.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    _generate_docx(data, DOCX_FILE)


if __name__ == "__main__":
    main()
