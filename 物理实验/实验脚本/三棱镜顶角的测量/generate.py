"""分光计测量三棱镜顶角实验 — 数据处理脚本。

反射法：平行光管射出的平行光照射三棱镜的两个折射面，望远镜分别转至
位置Ⅰ、Ⅱ对准左右两侧反射光，由对径双游标 A、B 读数消除偏心差，
α = φ/2 = ¼(|θA−θ′A| + |θB−θ′B|)，4 组测量求平均并评定不确定度。
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

# ============================================================
# 实验参数（按教材）
# ============================================================

N_MEAS = 4               # 测量组数（教材表 3-9-2）
T_FACTOR = 1.20          # t_0.683 因子（n=4，见迈克尔逊脚本 T_TABLE）
DELTA_INSTR_MIN = 1.0    # JJY 分光计分度值 1′（仪器误差限）

# data.json 中 readings 矩阵（4 组 × 8 列）的列名，顺序与原表 B~I 列一致
COL_LABELS = ["θA 度", "θA 分", "θB 度", "θB 分",
              "θ′A 度", "θ′A 分", "θ′B 度", "θ′B 分"]


# ============================================================
# 角度工具
# ============================================================

def _fmt_dm(deg: float) -> str:
    """十进制度 → "60°02′"（修约到整分，分两位补零）。仅用于非负角。"""
    total_min = round(deg * 60)
    d, m = divmod(total_min, 60)
    return f"{d}°{m:02d}′"


def _fmt_min(minutes: float) -> str:
    """不确定度（分）的显示格式：≥1′ 一位小数，<1′ 两位小数。

    与结果表达 delta_report_str 的精度分支保持一致，避免同一数值
    在推导式与结果式中出现两种写法。
    """
    return f"{minutes:.1f}" if minutes >= 1 else f"{minutes:.2f}"


def _diff_deg(theta: float, theta_p: float):
    """|θ − θ′|，处理刻度盘过 360° 零点（差 >180° 时加减 360°）。

    返回 (修正后差值/度, corr)。corr ∈ {0, +360, −360} 为显式加在
    (θ − θ′) 上的修正项，供 docx 代入公式重现 ±360° 写法，
    保证"算的"与"写的"同源。
    """
    d = theta - theta_p
    corr = 0
    if d > 180:
        corr = -360
    elif d < -180:
        corr = 360
    return abs(d + corr), corr


def _corr_latex(corr: int) -> str:
    """过零修正项的公式片段（紧跟被修正的读数写出）。

    corr=+360 → θ 是小数据，加 360°；corr=−360 → θ 是大数据，减 360°。
    修正项必须放在组内两读数之间：若放在 |…| 组末尾（"…360°|"），
    Word BuildUp 会解析失败，公式保持线性格式不再转换。
    """
    if corr > 0:
        return " + 360°"
    if corr < 0:
        return " - 360°"
    return ""


# ============================================================
# Excel 模板生成
# ============================================================

# （方式三：_create_template 已移除，数据真相为 data.json）


# ============================================================
# 数据读取与计算
# ============================================================

def _read_data(data: dict):
    """读取 data["readings"]（4 组 × 8 列，度、分交替），含空值与合法性校验。

    返回 4×4 十进制度列表（每行 [θA, θB, θ′A, θ′B]）；
    返回 None 表示形状不符、有缺失或含非法值（已打印组号与列名）。
    """
    raw = data["readings"]

    if (len(raw) != N_MEAS
            or any(not isinstance(row, list) or len(row) != 8 for row in raw)):
        print(f"[ERROR] readings 形状不正确：应为 {N_MEAS} 组 × 8 列（每角 度、分 两列）。")
        return None

    missing, invalid = [], []
    for i, row in enumerate(raw):
        for j, v in enumerate(row):
            addr = f"第{i + 1}组 {COL_LABELS[j]}"
            if v is None:
                missing.append(addr)
                continue
            try:
                x = float(v)
            except (TypeError, ValueError):
                invalid.append(f"{addr} (not a number)")
                continue
            if j % 2 == 0:  # 度列
                if not 0 <= x < 360:
                    invalid.append(f"{addr} (degree must be in [0, 360))")
            else:           # 分列
                if not 0 <= x < 60:
                    invalid.append(f"{addr} (minute must be in [0, 60))")

    if missing:
        print("[ERROR] The following readings are empty. "
              "Please fill in data and re-run:")
        for m in missing:
            print(f"  - {m}")
    if invalid:
        print("[ERROR] The following readings contain invalid values:")
        for m in invalid:
            print(f"  - {m}")
    if missing or invalid:
        return None

    # 度 + 分/60 → 十进制度；每行 [θA, θB, θ′A, θ′B]
    angles = []
    for row in raw:
        angles.append([float(row[k]) + float(row[k + 1]) / 60
                       for k in range(0, 8, 2)])
    return angles


def _compute(angles):
    """完整计算链：|θ−θ′|（过零修正）→ α_i → 平均 → 不确定度。

    返回结果字典 r，键与量纲：
      dA_deg / dB_deg / alpha_deg / alpha_mean —— 度（十进制度）
      corrA / corrB                            —— 过零修正项（度，取值 0/±360）
      dev_min / s_min / delta_bad_min / delta_A_min / delta_B_min / delta_min —— 分（′）
      delta_deg                                —— 度（= delta_min / 60）
      rel_percent                              —— 百分数（%）
      bad                                      —— 坏值组号列表（无量纲）
      zero_cross_count                         —— 需 ±360° 修正的读数对数（无量纲）
      delta_report_str                         —— 结果表达用的不确定度字符串（含 ′）
    标量键可直接被 variants.json 的 %%DATA:key:fmt%% 占位符引用。
    """
    r = {}

    # ---- 1. 各组望远镜转角与顶角 ----
    dA = [_diff_deg(t[0], t[2]) for t in angles]   # 游标 A：(|θA−θ′A|, corr)
    dB = [_diff_deg(t[1], t[3]) for t in angles]   # 游标 B：(|θB−θ′B|, corr)
    r["dA_deg"] = [v for v, _ in dA]
    r["corrA"] = [c for _, c in dA]
    r["dB_deg"] = [v for v, _ in dB]
    r["corrB"] = [c for _, c in dB]
    r["alpha_deg"] = [(a + b) / 4 for a, b in zip(r["dA_deg"], r["dB_deg"])]

    # ---- 2. 平均值与偏差 ----
    r["alpha_mean"] = mean(r["alpha_deg"])
    r["dev_min"] = [(a - r["alpha_mean"]) * 60 for a in r["alpha_deg"]]

    # ---- 3. 不确定度（单位：分） ----
    r["s_min"] = std_dev(r["alpha_deg"]) * 60            # 贝塞尔样本标准差
    r["delta_bad_min"] = T_FACTOR * r["s_min"]           # δ = s·t（3δ 坏值判据）
    r["bad"] = [i + 1 for i, d in enumerate(r["dev_min"])
                if abs(d) > 3 * r["delta_bad_min"]]
    r["delta_A_min"] = T_FACTOR * r["s_min"] / math.sqrt(N_MEAS)
    r["delta_B_min"] = type_b(DELTA_INSTR_MIN, "uniform")
    r["delta_min"] = combine(r["delta_A_min"], r["delta_B_min"])
    r["rel_percent"] = r["delta_min"] / (r["alpha_mean"] * 60) * 100
    # 供变体章节引用的标量键：以度表示的合成不确定度、过零修正次数
    r["delta_deg"] = r["delta_min"] / 60
    r["zero_cross_count"] = sum(1 for c in r["corrA"] + r["corrB"] if c)

    # 结果表达：不确定度进位到整分与 ᾱ 末位对齐；不足 1′ 保留两位小数
    if r["delta_min"] >= 1:
        r["delta_report_str"] = f"{math.ceil(r['delta_min'])}′"
    else:
        r["delta_report_str"] = f"{r['delta_min']:.2f}′"
    return r


def _subst_latex(i: int, t, corr_a: int, corr_b: int, alpha: float) -> str:
    """第 i 组代入计算公式串（过零组显式写出 ±360° 修正项）。

    结果修约到整分，故用 \\approx 连接（α_i 常带 .25′/.5′/.75′ 残差）。
    """
    return (f"\\alpha_{{{i}}} = \\frac{{1}}{{4}}\\left("
            f"|{_fmt_dm(t[0])}{_corr_latex(corr_a)} - {_fmt_dm(t[2])}|"
            f" + |{_fmt_dm(t[1])}{_corr_latex(corr_b)} - {_fmt_dm(t[3])}|"
            f"\\right) \\approx {_fmt_dm(alpha)}")


# ============================================================
# docx 报告生成
# ============================================================

def _generate_docx(data: dict, output_path: str) -> bool:
    """从 data.json 读取 → 计算 → 输出 docx 报告。成功返回 True，数据缺失返回 False。"""
    # 校验必填数据（required 字段为 null 或 matrix 含 null → 缺失）
    v = data.get("readings")
    flat = ([x for row in v for x in row]
            if isinstance(v, list) and v and isinstance(v[0], list) else v)
    if v is None or (isinstance(flat, list) and any(x is None for x in flat)):
        print("以下必填数据未填写，请补齐后重新运行：")
        print("  - readings")
        return False

    angles = _read_data(data)
    if angles is None:
        return False
    r = _compute(angles)

    # ---------- 控制台摘要 ----------
    print(f"\n{'=' * 56}")
    for i in range(N_MEAS):
        zc = [name for name, c in (("A", r["corrA"][i]), ("B", r["corrB"][i])) if c]
        note = f"  (zero-cross: vernier {','.join(zc)})" if zc else ""
        print(f"  n={i + 1}: |dA|={_fmt_dm(r['dA_deg'][i])}  "
              f"|dB|={_fmt_dm(r['dB_deg'][i])}  "
              f"alpha={_fmt_dm(r['alpha_deg'][i])}{note}")
    print(f"  mean alpha = {_fmt_dm(r['alpha_mean'])}")
    bad_note = ("no bad values" if not r["bad"]
                else f"BAD VALUES in group(s) {r['bad']}!")
    print(f"  s={r['s_min']:.1f}'  3delta={3 * r['delta_bad_min']:.1f}'  {bad_note}")
    print(f"  Delta_A={r['delta_A_min']:.1f}'  Delta_B={r['delta_B_min']:.2f}'  "
          f"Delta_alpha={r['delta_min']:.1f}'  rel={r['rel_percent']:.2f}%")
    print(f"  alpha = {_fmt_dm(r['alpha_mean'])} +/- {r['delta_report_str']}")
    print(f"{'=' * 56}\n")

    # ---------- 生成 docx ----------
    doc = DocxReportWriter(output_path)

    # ---- 零、实验标题 ----
    doc.add_title("三棱镜顶角的测量")
    doc.add_student_info()

    # ---- 变体组合：实验原理 / 实验方法（存在 variants.json 且应用传入选择时生效）----
    variants = compose(SCRIPT_DIR, r)
    if "实验原理" in variants:
        doc.add_heading("实验原理", level=1)
        doc.add_paragraph_rich(variants["实验原理"])
    if "实验方法" in variants:
        doc.add_heading("实验方法", level=1)
        doc.add_paragraph_rich(variants["实验方法"])

    # ---- 一、原始数据记录 ----
    doc.add_heading("一、原始数据记录", level=1)
    doc.add_paragraph("（请在此处粘贴原始数据记录照片。）")

    # ---- 二、数据处理 ----
    doc.add_heading("二、数据处理", level=1)

    # -- 1. 各组顶角 --
    doc.add_heading("1. 各组顶角的计算", level=2)
    doc.add_paragraph(
        "平行光管射出的平行光照射在三棱镜的两个折射面上，将望远镜分别转至"
        "位置Ⅰ、Ⅱ对准左、右两侧反射光，由游标 A、B 读出方位角 θ 与 θ′。"
        "对两个游标所测转角取平均以消除刻度盘偏心差，顶角为")
    doc.add_math(r"\alpha = \frac{\varphi}{2} = \frac{1}{4}"
                 r"\left(|\theta_{A} - θ′_{A}| + |\theta_{B} - θ′_{B}|\right)")
    doc.add_paragraph(
        "当两次读数跨过刻度盘 360° 零点时，须将小数据加 360°"
        "（或大数据减 360°），下式中已显式写出修正项。将四组数据分别代入：")
    for i in range(N_MEAS):
        doc.add_math(_subst_latex(i + 1, angles[i], r["corrA"][i],
                                  r["corrB"][i], r["alpha_deg"][i]))
    doc.add_paragraph("各组顶角汇总如下：")
    doc.add_table(
        headers=["n"] + [str(i + 1) for i in range(N_MEAS)],
        rows=[["αᵢ"] + [_fmt_dm(a) for a in r["alpha_deg"]]],
        col_widths=[2.0] + [2.6] * N_MEAS,
    )
    doc.add_paragraph("求得顶角平均值")
    sum_terms = " + ".join(_fmt_dm(a) for a in r["alpha_deg"])
    doc.add_math(f"\\overline{{\\alpha}} = \\frac{{1}}{{{N_MEAS}}}"
                 f"\\sum_{{i=1}}^{{{N_MEAS}}}\\alpha_{{i}}"
                 f" = \\frac{{{sum_terms}}}{{{N_MEAS}}}"
                 f" \\approx {_fmt_dm(r['alpha_mean'])}")

    # -- 2. 不确定度评定 --
    doc.add_heading("2. 不确定度评定", level=2)
    doc.add_paragraph("")
    doc.add_run("各组顶角相对平均值的偏差 ")
    doc.add_inline_math(r"\Delta\alpha_{i} = \alpha_{i} - \overline{\alpha}")
    doc.add_run(" 及其平方列于下表（以分为单位）：")
    doc.add_table(
        headers=["n"] + [str(i + 1) for i in range(N_MEAS)],
        rows=[
            ["αᵢ"] + [_fmt_dm(a) for a in r["alpha_deg"]],
            ["Δαᵢ/′"] + [f"{d:+.1f}" for d in r["dev_min"]],
            ["(Δαᵢ)²/′²"] + [f"{d ** 2:.1f}" for d in r["dev_min"]],
        ],
        col_widths=[2.4] + [2.5] * N_MEAS,
    )
    doc.add_paragraph("样本标准差为")
    dev_terms = " + ".join(f"({d:+.1f}′)^{{2}}" for d in r["dev_min"])
    doc.add_math(f"s_{{\\alpha}} = \\sqrt{{\\frac{{\\sum(\\Delta\\alpha_{{i}})^{{2}}}}"
                 f"{{n-1}}}} = \\sqrt{{\\frac{{{dev_terms}}}{{{N_MEAS - 1}}}}}"
                 f" \\approx {r['s_min']:.1f}′")
    doc.add_paragraph("")
    doc.add_run("取 ")
    doc.add_inline_math(f"t_{{0.683}} = {T_FACTOR:.2f}")
    doc.add_run(f"（n = {N_MEAS}），作 3δ 坏值检验：")
    doc.add_math(f"\\delta = s_{{\\alpha}} \\times t_{{0.683}}"
                 f" = {r['s_min']:.1f}′ \\times {T_FACTOR:.2f}"
                 f" \\approx {r['delta_bad_min']:.1f}′")
    doc.add_math(f"3\\delta \\approx {3 * r['delta_bad_min']:.1f}′")
    if r["bad"]:
        bad_str = "、".join(str(b) for b in r["bad"])
        doc.add_paragraph(
            f"经检验，第 {bad_str} 组的偏差超过 3δ，为坏值，"
            "应剔除该组数据并补测后重新处理。")
    else:
        doc.add_paragraph("经检验，各组偏差均小于 3δ，无坏值。")
    doc.add_paragraph("A 类不确定度为")
    doc.add_math(f"\\Delta_{{A}} = \\frac{{t \\cdot s_{{\\alpha}}}}{{\\sqrt{{n}}}}"
                 f" = \\frac{{{T_FACTOR:.2f} \\times {r['s_min']:.1f}′}}"
                 f"{{\\sqrt{{{N_MEAS}}}}}"
                 f" \\approx {r['delta_A_min']:.1f}′")
    doc.add_paragraph("B 类（仪器）不确定度为")
    doc.add_math(f"\\Delta_{{B}} = \\frac{{\\Delta_{{\\text{{仪}}}}}}{{\\sqrt{{3}}}}"
                 f" = \\frac{{1′}}{{\\sqrt{{3}}}}"
                 f" \\approx {r['delta_B_min']:.2f}′")
    doc.add_paragraph("合成不确定度为")
    doc.add_math(f"\\Delta\\alpha = \\sqrt{{\\Delta_{{A}}^{{2}} + \\Delta_{{B}}^{{2}}}}"
                 f" = \\sqrt{{({r['delta_A_min']:.1f}′)^{{2}}"
                 f" + ({r['delta_B_min']:.2f}′)^{{2}}}}"
                 f" \\approx {_fmt_min(r['delta_min'])}′")
    doc.add_paragraph("相对不确定度为")
    doc.add_math(f"\\frac{{\\Delta\\alpha}}{{\\overline{{\\alpha}}}}"
                 f" = \\frac{{{_fmt_min(r['delta_min'])}′}}"
                 f"{{{_fmt_dm(r['alpha_mean'])}}}"
                 f" \\times 100% \\approx {format_percent(r['rel_percent'])}%")

    # -- 3. 测量结果 --
    doc.add_heading("3. 测量结果", level=2)
    if r["delta_min"] >= 1:
        doc.add_paragraph("将不确定度按进位法取整到 1′，三棱镜顶角的测量结果为")
    else:
        doc.add_paragraph("三棱镜顶角的测量结果为")
    doc.add_math(f"\\alpha = \\overline{{\\alpha}} \\pm \\Delta\\alpha"
                 f" = {_fmt_dm(r['alpha_mean'])} \\pm {r['delta_report_str']}")
    doc.add_paragraph(f"相对不确定度为 {format_percent(r['rel_percent'])}%。")

    # ---- 三、实验结果分析 ----
    doc.add_heading("三、实验结果分析", level=1)
    doc.add_paragraph(
        f"本实验用反射法测得三棱镜顶角为 {_fmt_dm(r['alpha_mean'])}，"
        "与三棱镜 60° 的标称顶角接近。测量中利用对径放置的双游标 A、B "
        "读数取平均，消除了刻度盘的偏心误差。误差主要来源于载物台调平"
        "不完善使反射像偏离叉丝中心、望远镜竖直叉丝与狭缝像的对准偏差"
        "以及游标读数的估读；可通过仔细调整分光计、使两折射面的反射像"
        "等高、增加测量次数等方法进一步减小误差。")

    # ---- 变体组合：误差分析 / 结论（存在 variants.json 且应用传入选择时生效）----
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])
    if "结论" in variants:
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    # ---- 四、课后思考题 ----
    doc.add_heading("四、课后思考题", level=1)

    doc.add_heading("1. 在载物台上放置三棱镜时，为什么要使折射面垂直于"
                    "载物台调平螺丝的连线？", level=2)
    doc.add_paragraph(
        "答：（1）调节关系明确：当折射面垂直于两颗调平螺丝的连线时，"
        "升降这两颗螺丝只改变该折射面法线的俯仰，螺丝的调节量与折射面"
        "倾角之间有明确的几何对应关系，便于精准调节。")
    doc.add_paragraph(
        "（2）两折射面的调节互不干扰：此时每个折射面的俯仰只由对应的"
        "调平螺丝控制，调节自由度解耦——调平一个折射面时不会破坏另一个"
        "已调好的折射面，用各半调节法能迅速完成载物台调平。")
    doc.add_paragraph(
        "（3）保证测量精度：若折射面不垂直于连线，调节任一螺丝都会使"
        "反射像同时产生上下和左右的复合偏移，难以判断像的中心位置，"
        "会引入额外的对准误差。")

    doc.add_heading("2. 不使用汞灯和平行光管，利用望远镜自身产生的平行光来"
                    "测三棱镜顶角的方法称为自准法。试用自准法测三棱镜顶角，"
                    "并说明测量原理和方法。", level=2)
    doc.add_paragraph(
        "答：测量原理——望远镜目镜中的叉丝分划板被小灯照亮后，经物镜"
        "射出平行光；当望远镜光轴与三棱镜某折射面垂直时，平行光沿原路"
        "返回，在分划板上形成清晰的亮十字自准像并与叉丝重合，由此可以"
        "确定该折射面法线的方位。")
    doc.add_paragraph("")
    doc.add_run("设两折射面法线的方位角分别为 ")
    doc.add_inline_math(r"\varphi_{1}")
    doc.add_run(" 和 ")
    doc.add_inline_math(r"\varphi_{2}")
    doc.add_run("，则两法线的夹角为 ")
    doc.add_inline_math(r"θ = |φ_{1} - φ_{2}|")
    doc.add_run("，顶角为其补角：")
    doc.add_math(r"α = 180° - θ")
    doc.add_paragraph(
        "测量方法：①按正常步骤调整分光计，使望远镜适合观察平行光、其"
        "光轴垂直于仪器中心轴，并调平载物台；②将三棱镜置于载物台上，"
        "转动望远镜正对折射面 AB，微调至亮十字自准像与叉丝上方交点重合，"
        "从两个游标分别读出方位角 φ₁；③再转动望远镜正对另一折射面 AC，"
        "同法读出方位角 φ₂；④由上式求出顶角 α，重复测量数次取平均。"
        "计算转角时同样取双游标读数的平均以消除偏心差，读数跨过刻度盘"
        "零点时作 360° 修正。")

    doc.save()
    doc.close()
    return True


# ============================================================
# 入口
# ============================================================

def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "三棱镜顶角的测量实验报告.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    if _generate_docx(data, DOCX_FILE):
        print(f"报告已生成: {DOCX_FILE}")


if __name__ == "__main__":
    main()
