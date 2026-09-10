"""光栅光谱的测量实验 — 数据处理脚本。

用分光计测量汞灯 K=±1 级衍射谱线的衍射角，
由绿光（λ=546.1nm）求光栅常数 d 及其不确定度，
再反求各谱线波长及不确定度，估算最高衍射级数。
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

# ============================================================
# 物理常数 / 实验参数（按教材）
# ============================================================

K_ORDER = 1              # 谱线级次 K=1
T_FACTOR = 4.30          # t 分布因子 t_{0.95,2}（绿光 3 次测量）
DELTA_INSTR_MIN = 1.0    # 分光计最小分度 1′（仪器误差限）

# 谱线行标签（Excel 第 4~8 行，顺序固定）
LINE_LABELS = ["黄2光", "黄1光", "绿光1次", "绿光2次", "绿光3次"]


# ============================================================
# 角度工具
# ============================================================

def _fmt_dm(deg: float) -> str:
    """十进制度 → "9°27′"（四舍五入到整分）。"""
    total_min = round(deg * 60)
    d, m = divmod(total_min, 60)
    return f"{d}°{m}′"


def _half_diff(a: float, b: float) -> float:
    """|a - b| / 2，处理刻度盘过 360° 零点（差 >180° 时取 360°-差）。返回度。"""
    diff = abs(a - b)
    if diff > 180:
        diff = 360 - diff
    return diff / 2


# ============================================================
# Excel 模板生成
# ============================================================

# （方式三：_create_template 已移除，数据真相为 data.json）


# ============================================================
# 数据读取与计算
# ============================================================

def _read_data(data: dict):
    """从 data.json 字典读取角度表、给定波长、观察级数，含必填校验。

    angles：5 行 × 8 列（度/分交替），每行 [θA⁻¹度,θA⁻¹分,θB⁻¹度,θB⁻¹分,
      θA⁺¹度,θA⁺¹分,θB⁺¹度,θB⁺¹分]。
    返回 (angles, lambda_green, kmax_obs)；返回 None 表示有缺失（已打印缺失字段）。
    """
    angles_raw = data.get("angles")
    lambda_green = data.get("lambda_green")
    kmax_obs = data.get("kmax_obs")

    missing = []
    if angles_raw is None:
        missing.append("angles")
    else:
        for i, row in enumerate(angles_raw):
            for j, v in enumerate(row):
                if v is None:
                    missing.append(f"angles[{i}][{j}]")
    if lambda_green is None:
        missing.append("lambda_green")
    if kmax_obs is None:
        missing.append("kmax_obs")

    if missing:
        print("以下必填数据未填写，请补齐后重新运行：")
        for m in missing:
            print(f"  - {m}")
        return None

    # 度 + 分/60 → 十进制度；每行 [θA-1, θB-1, θA+1, θB+1]
    angles = []
    for row in angles_raw:
        angles.append([float(row[k]) + float(row[k + 1]) / 60
                       for k in range(0, 8, 2)])
    return angles, float(lambda_green), int(kmax_obs)


def _compute(angles, lambda_green):
    """完整计算链：衍射角 → 光栅常数 d 及不确定度 → 各谱线波长及不确定度。"""
    r = {}

    # ---- 1. 各谱线衍射角（消偏心差） ----
    r["phi_A"] = [_half_diff(t[0], t[2]) for t in angles]
    r["phi_B"] = [_half_diff(t[1], t[3]) for t in angles]
    r["phi"] = [(a + b) / 2 for a, b in zip(r["phi_A"], r["phi_B"])]

    # ---- 2. 绿光衍射角统计（3 次） ----
    green_phi = r["phi"][2:5]
    r["phi_green_mean"] = mean(green_phi)
    r["dev_min"] = [(p - r["phi_green_mean"]) * 60 for p in green_phi]  # 各次偏差/′
    r["sigma_min"] = std_dev(green_phi) * 60                            # σφ/′
    r["delta_A_min"] = T_FACTOR * r["sigma_min"] / math.sqrt(3)         # t 分布修正
    r["delta_B_min"] = DELTA_INSTR_MIN / math.sqrt(3)
    r["dphi_green_min"] = combine(r["delta_A_min"], r["delta_B_min"])   # 合成 Δφ/′

    # ---- 3. 光栅常数 d 及不确定度 ----
    phi_g = math.radians(r["phi_green_mean"])
    dphi_g = math.radians(r["dphi_green_min"] / 60)
    r["d_nm"] = K_ORDER * lambda_green / math.sin(phi_g)
    r["delta_d_nm"] = r["d_nm"] * abs(math.cos(phi_g) / math.sin(phi_g)) * dphi_g
    r["rel_d"] = r["delta_d_nm"] / r["d_nm"]

    # ---- 4. 各谱线波长及不确定度 ----
    # 黄光仅测 1 次，Δφ 只取 Δ_B；绿光取合成 Δφ
    specs = [
        ("黄2光", r["phi"][0], r["delta_B_min"]),
        ("黄1光", r["phi"][1], r["delta_B_min"]),
        ("绿光", r["phi_green_mean"], r["dphi_green_min"]),
    ]
    r["lines"] = []
    for name, phi_deg, dphi_min in specs:
        pr = math.radians(phi_deg)
        dpr = math.radians(dphi_min / 60)
        lam = r["d_nm"] * math.sin(pr) / K_ORDER
        dlam = math.sqrt((math.sin(pr) * r["delta_d_nm"]) ** 2
                         + (r["d_nm"] * math.cos(pr) * dpr) ** 2) / K_ORDER
        r["lines"].append((name, phi_deg, lam, dlam))

    # ---- 5. 最高衍射级数（理论，用绿光实测波长） ----
    lam_green_measured = r["lines"][2][2]
    r["kmax_ratio"] = r["d_nm"] / lam_green_measured
    r["kmax_theory"] = math.floor(r["kmax_ratio"])
    return r


# ============================================================
# docx 报告生成
# ============================================================

def _generate_docx(data: dict, output_path: str) -> bool:
    """从 data.json 读取数据 → 计算 → 输出 docx 报告。成功返回 True。"""
    parsed = _read_data(data)
    if parsed is None:
        return False
    angles, lambda_green, kmax_obs = parsed
    r = _compute(angles, lambda_green)
    # 变体章节（无 LAB_VARIANTS 选择时为空 dict，报告输出保持不变）
    variants = compose(SCRIPT_DIR, r)

    # d 结果表达式（μm）：不确定度 1~2 位有效数字，值末位对齐
    d_um = r["d_nm"] / 1000
    ud_um = r["delta_d_nm"] / 1000
    d_um_str = format_number(d_um, uncertainty=ud_um)
    decimals = len(d_um_str.split(".")[1]) if "." in d_um_str else 0
    ud_um_str = f"{ud_um:.{decimals}f}"

    # ---------- 控制台摘要 ----------
    print(f"\n{'=' * 56}")
    for i, label in enumerate(LINE_LABELS):
        print(f"  {label}: phi_A={_fmt_dm(r['phi_A'][i])}  "
              f"phi_B={_fmt_dm(r['phi_B'][i])}  phi={_fmt_dm(r['phi'][i])}")
    print(f"  green mean phi = {_fmt_dm(r['phi_green_mean'])}")
    print(f"  sigma={r['sigma_min']:.1f}'  Delta_A={r['delta_A_min']:.1f}'  "
          f"Delta_B={r['delta_B_min']:.2f}'  Delta_phi={r['dphi_green_min']:.1f}'")
    print(f"  d = {r['d_nm']:.1f} nm   Delta_d = {r['delta_d_nm']:.1f} nm   "
          f"Delta_d/d = {r['rel_d'] * 100:.2f}%")
    print(f"  d = ({d_um_str} +/- {ud_um_str}) um")
    for name, phi_deg, lam, dlam in r["lines"]:
        print(f"  {name}: phi={_fmt_dm(phi_deg)}  lambda={lam:.1f} nm  "
              f"Delta_lambda={dlam:.1f} nm")
    print(f"  K_max: theory d/lambda = {r['kmax_ratio']:.2f} -> {r['kmax_theory']}, "
          f"observed = {kmax_obs}")
    print(f"{'=' * 56}\n")

    # ---------- 生成 docx ----------
    doc = DocxReportWriter(output_path)

    # ---- 零、实验标题 ----
    doc.add_title("光栅光谱的测量")
    doc.add_student_info()

    # ---- 变体章节：实验原理 / 实验方法 ----
    if variants.get("实验原理"):
        doc.add_heading("实验原理", level=1)
        doc.add_paragraph_rich(variants["实验原理"])
    if variants.get("实验方法"):
        doc.add_heading("实验方法", level=1)
        doc.add_paragraph_rich(variants["实验方法"])

    # ---- 一、原始数据记录 ----
    doc.add_heading("一、原始数据记录", level=1)
    doc.add_paragraph("（请在此处粘贴原始数据记录照片。）")

    # ---- 二、数据处理 ----
    doc.add_heading("二、数据处理", level=1)

    # -- 1. 衍射角 --
    doc.add_heading("1. 衍射角的计算", level=2)
    doc.add_paragraph("通过公式")
    doc.add_math(r"\theta_{A}^{-1} - \theta_{A}^{+1} = 2\varphi_{A}")
    doc.add_math(r"\theta_{B}^{-1} - \theta_{B}^{+1} = 2\varphi_{B}")
    doc.add_paragraph("求得衍射角，并通过求平均值消除偏心差得到衍射角为")
    doc.add_math(r"\varphi = \frac{\varphi_{A} + \varphi_{B}}{2}"
                 r" = \frac{|\theta_{A}^{-1} - \theta_{A}^{+1}|"
                 r" + |\theta_{B}^{-1} - \theta_{B}^{+1}|}{4}")
    doc.add_paragraph("代入后得到处理后的数据表：")
    doc.add_table(
        headers=["角度＼光谱"] + LINE_LABELS,
        rows=[
            ["φA"] + [_fmt_dm(v) for v in r["phi_A"]],
            ["φB"] + [_fmt_dm(v) for v in r["phi_B"]],
            ["φ"] + [_fmt_dm(v) for v in r["phi"]],
        ],
        col_widths=[2.6, 2.2, 2.2, 2.2, 2.2, 2.2],
    )

    # -- 2. 光栅常数 d --
    doc.add_heading("2. 计算光栅常数 d", level=2)
    doc.add_paragraph("")
    doc.add_run("汞灯绿色谱线波长为 ")
    doc.add_inline_math(f"\\lambda = {lambda_green}\\ \\mathrm{{nm}}")
    doc.add_run("，取谱线级次 ")
    doc.add_inline_math(f"K = {K_ORDER}")
    doc.add_run("，将三次测量所得绿色谱线衍射角的平均值 ")
    doc.add_inline_math(f"\\overline{{\\varphi}} = {_fmt_dm(r['phi_green_mean'])}")
    doc.add_run(" 代入光栅方程 ")
    # 注意：行尾的 \lambda 会被 Word BuildUp 静默丢弃，须直接用 Unicode λ
    doc.add_inline_math(r"d\sin\varphi_{K} = Kλ")
    doc.add_run("，求得光栅常数")
    doc.add_math(f"\\overline{{d}} = \\frac{{K\\lambda}}{{\\sin\\overline{{\\varphi}}}}"
                 f" = \\frac{{{lambda_green}\\ \\mathrm{{nm}}}}"
                 f"{{\\sin {_fmt_dm(r['phi_green_mean'])}}}"
                 f" \\approx {r['d_nm']:.1f}\\ \\mathrm{{nm}}")
    doc.add_paragraph("绿光三次测量衍射角的样本标准差为")
    dev_terms = "+".join(f"({v:+.1f}′)^{{2}}" for v in r["dev_min"])
    doc.add_math(f"\\sigma_{{\\varphi}} = \\sqrt{{\\frac{{\\sum(\\delta\\varphi_{{i}})^{{2}}}}"
                 f"{{n-1}}}} = \\sqrt{{\\frac{{{dev_terms}}}{{2}}}}"
                 f" \\approx {r['sigma_min']:.1f}′")
    doc.add_paragraph("")
    doc.add_run("由于只有三次测量，采用 t 分布进行修正（")
    doc.add_inline_math(r"t_{0.95,2} \approx 4.30")
    doc.add_run("），则")
    doc.add_math(f"\\Delta_{{A}} = \\frac{{t \\cdot \\sigma_{{\\varphi}}}}{{\\sqrt{{n}}}}"
                 f" = \\frac{{4.30 \\times {r['sigma_min']:.1f}′}}{{\\sqrt{{3}}}}"
                 f" \\approx {r['delta_A_min']:.1f}′")
    doc.add_paragraph("考虑仪器的不确定度")
    doc.add_math(f"\\Delta_{{B}} = \\frac{{1′}}{{\\sqrt{{3}}}}"
                 f" \\approx {r['delta_B_min']:.2f}′")
    doc.add_paragraph("则合成不确定度为")
    doc.add_math(f"\\Delta\\varphi_{{K}} = \\sqrt{{\\Delta_{{A}}^{{2}} + \\Delta_{{B}}^{{2}}}}"
                 f" \\approx {r['dphi_green_min']:.1f}′")
    doc.add_paragraph("下面计算 d 的不确定度。由光栅方程得")
    doc.add_math(r"d = \frac{K\lambda}{\sin\varphi_{K}}")
    doc.add_paragraph("则")
    doc.add_math(r"\Delta d = \left|\frac{\partial d}{\partial \varphi_{K}}\right|"
                 r" \Delta\varphi_{K}")
    doc.add_paragraph("计算偏导数：")
    doc.add_math(r"\frac{\partial d}{\partial \varphi_{K}}"
                 r" = \frac{\partial}{\partial \varphi_{K}}"
                 r"\left(\frac{K\lambda}{\sin\varphi_{K}}\right)"
                 # \sin^{2}\varphi_{K} 会 BuildUp 出空参数函数节点，参数须整体包 {}
                 r" = -K\lambda \cdot \frac{\cos\varphi_{K}}{\sin^{2}{\varphi_{K}}}")
    doc.add_paragraph("绝对值为")
    doc.add_math(r"\left|\frac{\partial d}{\partial \varphi_{K}}\right|"
                 r" = K\lambda \cdot \frac{\left|\cos\varphi_{K}\right|}{\sin^{2}{\varphi_{K}}}")
    doc.add_paragraph("所以 d 的不确定度表示为")
    doc.add_math(f"\\Delta d = d \\cdot \\left|\\cot\\varphi_{{K}}\\right| \\cdot \\Delta\\varphi_{{K}}"
                 f" \\approx {r['delta_d_nm']:.0f}\\ \\mathrm{{nm}}")
    doc.add_paragraph("则相对不确定度为")
    doc.add_math(f"\\frac{{\\Delta d}}{{d}} \\approx {format_percent(r['rel_d'] * 100)}%")
    doc.add_paragraph("光栅常数的测量结果为")
    doc.add_math(f"d = ({d_um_str} \\pm {ud_um_str})\\ \\mathrm{{μm}}")

    # -- 3. 各谱线波长 --
    doc.add_heading("3. 计算汞灯各衍射谱线的波长", level=2)
    doc.add_paragraph(
        "将所求的光栅常数及黄1光、黄2光及绿光的衍射角代入光栅方程，"
        "求得对应波长及其不确定度和结果表达式。由光栅方程得")
    doc.add_math(r"\lambda = \frac{d\sin\varphi_{K}}{K}")
    doc.add_paragraph("根据传递公式")
    doc.add_math(r"\Delta\lambda = \sqrt{\left(\frac{\partial\lambda}{\partial d}\right)^{2}"
                 r"(\Delta d)^{2} + \left(\frac{\partial\lambda}{\partial\varphi_{K}}\right)^{2}"
                 r"(\Delta\varphi_{K})^{2}}")
    doc.add_paragraph("计算偏导数")
    doc.add_math(r"\frac{\partial\lambda}{\partial d} = \frac{\sin\varphi_{K}}{K}")
    doc.add_math(r"\frac{\partial\lambda}{\partial\varphi_{K}} = \frac{d\cos\varphi_{K}}{K}")
    doc.add_paragraph("代入公式")
    doc.add_math(r"\Delta\lambda = \sqrt{\left(\frac{\sin\varphi_{K}}{K}\right)^{2}"
                 r"(\Delta d)^{2} + \left(\frac{d\cos\varphi_{K}}{K}\right)^{2}"
                 r"(\Delta\varphi_{K})^{2}}")
    doc.add_paragraph("最终不确定度表达式为")
    doc.add_math(r"\Delta\lambda = \frac{1}{K}\sqrt{\sin^{2}{\varphi_{K}} \cdot (\Delta d)^{2}"
                 r" + d^{2}\cos^{2}{\varphi_{K}} \cdot (\Delta\varphi_{K})^{2}}")
    doc.add_paragraph("")
    doc.add_run("根据该公式，所得的结果如下表（黄光仅进行了一次测量，其 ")
    doc.add_inline_math(r"\Delta\varphi_{K}")
    doc.add_run(" 只考虑 ")
    doc.add_inline_math(r"\Delta_{B}")
    doc.add_run("）：")
    doc.add_table(
        headers=["波长＼光谱"] + [name for name, *_ in r["lines"]],
        rows=[
            ["λ/nm"] + [f"{lam:.0f}" for _, _, lam, _ in r["lines"]],
            ["Δλ/nm"] + [f"{max(dlam, 1):.0f}" for *_, dlam in r["lines"]],
            ["λ±Δλ/nm"] + [f"{lam:.0f}±{max(dlam, 1):.0f}"
                           for _, _, lam, dlam in r["lines"]],
        ],
        col_widths=[3.4, 3.2, 3.2, 3.2],
    )

    # -- 4. 最高衍射级数 --
    doc.add_heading("4. 最高衍射级数的估算", level=2)
    doc.add_paragraph("")
    doc.add_run("由 ")
    doc.add_inline_math(r"d\sin\varphi_{K} = Kλ")  # 行尾 \lambda 会被丢弃，用 Unicode λ
    doc.add_run(" 可得，当 ")
    doc.add_inline_math(r"\varphi_{K} = 90°")
    doc.add_run(" 时，K 取得最大值")
    doc.add_math(f"K_{{\\text{{max}}}} = \\frac{{d}}{{\\lambda}}"
                 f" = \\frac{{{r['d_nm']:.0f}}}{{{r['lines'][2][2]:.0f}}}"
                 f" \\approx {r['kmax_ratio']:.1f}")
    doc.add_paragraph("")
    doc.add_run("即理论上最高衍射级数为 ")
    doc.add_inline_math(f"K_{{\\text{{max}}}} = {r['kmax_theory']}")
    doc.add_run("，但经实验观察，实际能观察到的最高衍射级数为 ")
    doc.add_inline_math(f"K_{{\\text{{max}}}} = {kmax_obs}")
    doc.add_run("。")

    # ---- 变体章节：误差分析 ----
    if variants.get("误差分析"):
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])

    # ---- 三、实验结果分析 ----
    doc.add_heading("三、实验结果分析", level=1)
    doc.add_paragraph(
        "实验对汞灯的线状光谱进行了测量，测得了衍射角并通过公式求出了光栅常数 d "
        "以及各谱线的波长；在中央亮线的左右两侧分布着各级光谱，"
        "可见光栅具有将入射光分成按波长排列的光谱的功能。"
        "然而所得结果与理论有一定误差，可能是由于测量时对仪器的不熟悉、"
        "读数的不精确导致。")

    # ---- 变体章节：结论 ----
    if variants.get("结论"):
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    # ---- 四、课后思考题 ----
    doc.add_heading("四、课后思考题", level=1)

    doc.add_heading(
        "1. 同一光栅对不同波长的光，其最高衍射级数是否相同？不同波长的谱线宽度"
        "是否一致？同一波长不同衍射级数的光谱宽度是否相同？为什么？", level=2)
    doc.add_paragraph("")
    doc.add_run("答：同一光栅对不同波长的光，其最高衍射级数不相同。最高衍射级数由光栅方程 ")
    doc.add_inline_math(r"d\sin\theta = Kλ")  # 行尾 \lambda 会被丢弃，用 Unicode λ
    doc.add_run(" 决定，")
    doc.add_inline_math(r"K_{\text{max}} = ⌊d/\lambda⌋")
    doc.add_run("，波长越小，")
    doc.add_inline_math(r"K_{\text{max}}")
    doc.add_run(" 越高；波长越大，")
    doc.add_inline_math(r"K_{\text{max}}")
    doc.add_run(" 越低。不同波长的谱线宽度不一致。谱线宽度由光栅的角色散率和仪器函数决定：角色散率 ")
    doc.add_inline_math(r"D = d\theta/d\lambda = K/(d\cos\theta)")
    doc.add_run("，同一级次 K 下，波长越大，衍射角越大，因此 D 越大（色散更明显），"
                "谱线越宽；光栅的刻线数 N 固定时，分辨率 ")
    doc.add_inline_math(r"R = KN")
    doc.add_run("，但实际谱线宽度还受狭缝宽度、像差等因素影响。"
                "同一波长不同衍射级数的光谱宽度不相同。光谱宽度与衍射级次 K 直接相关：角色散率 ")
    doc.add_inline_math(r"D \propto K")
    doc.add_run("，高级次衍射的色散更大，谱线更宽；分辨率 ")
    doc.add_inline_math(r"R = KN")
    doc.add_run("，虽然分辨率提高，但谱线间距（色散）的增加更显著，导致谱线展宽。")

    doc.add_heading(
        "2. 试根据实验时同一级正负衍射光谱的对称性，判断光栅放置的位置；并利用"
        "这种现象将光栅调至正确的位置；当同一级正负衍射角不等时，试估算入射光束"
        "不垂直的程度（即求入射角的大小）。", level=2)
    doc.add_paragraph("")
    doc.add_run("答：当入射光束严格垂直于光栅平面时，同一衍射级 K 的正负方向衍射角应满足对称性 ")
    doc.add_inline_math(r"|\theta_{+K}| = |\theta_{-K}|")
    doc.add_run("；若光栅未垂直于入射光，正负级衍射角会不对称。"
                "因此可以通过测量同一级（如 K=1）的正负衍射角来判断光栅的放置位置：若 ")
    doc.add_inline_math(r"|\theta_{+1}| \neq |\theta_{-1}|")
    doc.add_run("，说明光栅未垂直于入射光。此时若 ")
    doc.add_inline_math(r"|\theta_{+1}| > |\theta_{-1}|")
    doc.add_run("，入射光偏向光栅法线的一侧，需旋转光栅使 ")
    doc.add_inline_math(r"\theta_{+1}")
    doc.add_run(" 减小或 ")
    doc.add_inline_math(r"\theta_{-1}")
    doc.add_run(" 增大，反复调整，直到二者相等。当正负衍射角不等时，可通过光栅方程推导入射角")
    doc.add_math(r"\alpha = \text{arcsin}\left(\frac{\sin\theta_{K}"
                 r" + \sin\theta_{-K}}{2}\right)")
    doc.add_paragraph("")
    doc.add_run("例如，若测得绿光 ")
    doc.add_inline_math(r"\theta_{+1} = 164°29′")
    doc.add_run("、")
    doc.add_inline_math(r"\theta_{-1} = 183°21′")
    doc.add_run("，代入得 ")
    doc.add_inline_math(r"\alpha \approx 6.0°")
    doc.add_run("，则应将光栅旋转约 6° 使入射角趋近于 0。")

    doc.save()
    doc.close()
    return True


# ============================================================
# 入口
# ============================================================

def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "光栅光谱的测量实验报告.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    if _generate_docx(data, DOCX_FILE):
        print(f"报告已生成: {DOCX_FILE}")


if __name__ == "__main__":
    main()
