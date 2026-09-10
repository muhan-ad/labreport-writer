"""牛顿环（平凸透镜曲率半径） — 数据处理脚本。"""

import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import *
from common.docx_report import DocxReportWriter
from common.variants import compose
from common.data_io import load_data

# ── 物理常数 ──
LAMBDA = 589.3e-6         # 钠光波长 (mm)，589.3 nm
DELTA_INSTRUMENT = 0.004   # 测量显微镜仪器误差 (mm)
SKIP_N = 5                 # 逐差法间隔
T_FACTOR = 1.15            # t 因子 (n=5, df=4, P=0.683)


# （方式三：_create_template 已移除，数据真相为 data.json）


def _compute(data: dict) -> dict:
    """由左右读数计算各暗环直径、逐差与不确定度，返回结果字典 r。"""
    rings = [int(v) for v in data["rings"]]          # 20, 19, ..., 11
    d_left = [float(v) for v in data["d_left"]]       # 左侧读数
    d_right = [float(v) for v in data["d_right"]]     # 右侧读数

    # 直径和直径平方
    D_m = [abs(d_right[i] - d_left[i]) for i in range(10)]
    D_m2 = [d ** 2 for d in D_m]

    # 逐差法（skip-5）：环 20~16 (idx 0~4) 对应 环 15~11 (idx 5~9)
    diffs = [D_m2[i] - D_m2[i + SKIP_N] for i in range(5)]
    avg_diff = mean(diffs)
    std_diff = std_dev(diffs)

    # 每组差对应的曲率半径
    R_individual = [d / (4 * SKIP_N * LAMBDA) for d in diffs]
    R_bar = mean(R_individual)

    # 不确定度分析
    n_pairs = 5

    # Type A：5 个 R_i 的标准误
    u_A = T_FACTOR * std_dev(R_individual) / math.sqrt(n_pairs)

    # Type B：由仪器误差传播
    # 每个位置读数：u(x) = Δ_仪 / √3
    # 直径 D = |x_R - x_L| → u(D) = √2 · u(x)
    # D² 的相对不确定度：u_rel(D²) ≈ 2 · u(D) / D
    # D²_m - D²_n：相对不确定度 ≈ √2 · u_rel(D²)
    u_pos = DELTA_INSTRUMENT / math.sqrt(3)
    avg_D = mean(D_m)
    u_D = math.sqrt(2) * u_pos
    u_rel_D2 = 2 * u_D / avg_D
    u_rel_diff = math.sqrt(2) * u_rel_D2
    u_B = u_rel_diff * R_bar

    # 合成不确定度
    u_c = combine(u_A, u_B)

    return {
        "rings": rings, "d_left": d_left, "d_right": d_right,
        "D_m": D_m, "D_m2": D_m2,
        "diffs": diffs, "avg_diff": avg_diff, "std_diff": std_diff,
        "R_individual": R_individual, "R_bar": R_bar,
        "avg_D": avg_D, "u_A": u_A, "u_B": u_B, "u_c": u_c,
        "rel_u": u_c / R_bar * 100,
    }


def _generate_docx(data: dict, output_path: str):
    """从 data.json 读取数据，计算并生成 Word 实验报告。"""

    # ═══════════════════════════════════════════════
    # 1. 读取数据（含空值校验）
    # ═══════════════════════════════════════════════
    # 校验必填数据（required 字段为 null 或 array 含 null → 缺失）
    missing = []
    for k in ("rings", "d_left", "d_right"):
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

    # ═══════════════════════════════════════════════
    # 2. 数据处理：直径、逐差与不确定度（见 _compute）
    # ═══════════════════════════════════════════════
    r = _compute(data)
    R_bar = r["R_bar"]
    u_A = r["u_A"]
    u_B = r["u_B"]
    u_c = r["u_c"]
    n_pairs = len(r["diffs"])

    # ═══════════════════════════════════════════════
    # 5. 生成 docx 报告
    # ═══════════════════════════════════════════════
    doc = DocxReportWriter(output_path)

    # ── 零、实验标题 ──
    doc.add_title("平凸透镜曲率半径的测量")
    doc.add_student_info()

    # ── 变体组合：实验原理 / 实验方法（存在 variants.json 且应用传入选择时生效）──
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

    # ── 二、数据处理 ──
    doc.add_heading("二、数据处理", level=1)

    doc.add_paragraph("")  # 段落容器
    doc.add_run("采用逐差法处理数据，取环距 ")
    doc.add_inline_math(f"m - n = {SKIP_N}")
    doc.add_run("，将环序 20~16 与 15~11 逐项配对，计算 ")
    doc.add_inline_math("D_m^2 - D_{m-5}^2")
    doc.add_run(f" 的 {n_pairs} 组差值。")
    doc.add_paragraph("曲率半径平均值：")
    doc.add_math(
        r"\bar{R} = \frac{\overline{D_{m}^{2} - D_{m-5}^{2}}}"
        r"{4 \cdot 5 \cdot \lambda} = "
        + format_number(R_bar) + r"\,\mathrm{mm}"
    )

    doc.add_paragraph("A 类不确定度：")
    doc.add_math(
        r"\Delta\bar{R} = t \cdot \sqrt{"
        r"\frac{\sum_{i=1}^{5} (R_i - \bar{R})^{2}}{4 \cdot 5}} = "
        + format_number(u_A) + r"\,\mathrm{mm}"
    )

    doc.add_paragraph("合成不确定度：")
    doc.add_math(
        r"\Delta x = \sqrt{\Delta R_A^{2} + \Delta R_B^{2}} = "
        r"\sqrt{(\Delta\bar{R})^{2} + "
        r"(\frac{\Delta_{\text{仪}}}{\sqrt{3}})^{2}} = "
        + format_number(u_c) + r"\,\mathrm{mm}"
    )

    doc.add_paragraph("曲率半径测量结果：")
    R_display = format_number(R_bar, u_c)
    u_display = format_number(u_c, u_c)
    doc.add_math(
        r"R = \bar{R} \pm \Delta R = ("
        + R_display + r" \pm " + u_display + r")\,\mathrm{mm}"
    )

    # ── 三、实验结果分析 ──
    doc.add_heading("三、实验结果分析", level=1)
    doc.add_paragraph("")
    doc.add_run("本次测量曲率半径 ")
    doc.add_inline_math(f"R = {format_number(R_bar, u_c)} mm")
    doc.add_run("，合成不确定度 ")
    doc.add_inline_math(f"u_c = {format_number(u_c)} mm")
    doc.add_run(f"，相对不确定度 {format_number(u_c / R_bar * 100)}%。")

    doc.add_paragraph("")
    doc.add_run("误差主要来源于以下几个方面：")
    doc.add_run("（1）A 类不确定度占主导，来自 5 组逐差结果的统计涨落，")
    doc.add_run("反映在 R_i 的标准偏差较大（")
    doc.add_inline_math(f"u_A = {format_number(u_A)} mm")
    doc.add_run("）；（2）B 类不确定度来自测量显微镜的仪器误差，")
    doc.add_run("贡献较小（")
    doc.add_inline_math(f"u_B = {format_number(u_B)} mm")
    doc.add_run("）；（3）透镜与平板玻璃接触处的弹性形变和微量灰尘可能引入附加光程差，")
    doc.add_run("但采用逐差法后该系统误差已在 ")
    doc.add_inline_math("D_m^2")
    doc.add_run(" 差值中被消除；")
    doc.add_run("（4）测量过程中显微镜鼓轮未严格单方向旋转可能引入螺距差。")

    # ── 变体组合：误差分析 / 结论（存在 variants.json 且应用传入选择时生效）──
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])
    if "结论" in variants:
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    # ── 四、思考题 ──
    doc.add_heading("四、思考题", level=1)

    doc.add_heading("1. 牛顿环中心为何不是理想暗点？对 R 测量有无影响？", level=2)
    doc.add_paragraph(
        "答：实际实验中，平凸透镜和平面玻璃接触处存在弹性形变，"
        "导致接触处为一个小圆面而非理想点接触；此外镜面上可能有微量灰尘，"
        "引起附加光程差，使中心呈现或暗或明的圆斑。"
    )
    doc.add_paragraph("")
    doc.add_run("对 R 测量无影响。因为采用 ")
    doc.add_inline_math("D_m^2 - D_n^2")
    doc.add_run(" 的差值法处理数据时，附加厚度 a 在相减过程中被消除，不改变干涉条纹的级次差。")

    doc.add_heading("2. 说明牛顿环分布特点及干涉级次分布。", level=2)
    doc.add_paragraph("")
    doc.add_run("答：牛顿环中心为暗斑，周围交替分布明暗相间的同心圆环。")
    doc.add_run("环的分布特点是中央稀疏、边缘密集，呈内疏外密的不均匀排列。")
    doc.add_run("干涉级次分布：中央级次低（")
    doc.add_inline_math("m")
    doc.add_run(" 小），由内向外级次逐渐增大（")
    doc.add_inline_math("m")
    doc.add_run(" 增大），明环与暗环交替出现。")

    doc.add_heading("3. 牛顿环各环间距是否相等？根据以下原理进行解释。", level=2)
    doc.add_paragraph("")
    doc.add_run("测量原理：")
    doc.add_inline_math(r"R = \frac{D_m^2 - D_n^2}{4(m-n)\lambda}")
    doc.add_paragraph("")
    doc.add_run("答：不相等。空气膜厚度沿径向不均匀变化是根本原因。")
    doc.add_run("由几何关系 ")
    doc.add_inline_math("R^2 = (R-d)^2 + r^2")
    doc.add_run("，略去 d² 得 ")
    doc.add_inline_math(r"d = \frac{r^{2}}{2R}")
    doc.add_run("。")
    doc.add_paragraph("")
    doc.add_run("可见膜厚 ")
    doc.add_inline_math("d")
    doc.add_run(" 与 ")
    doc.add_inline_math("r^2")
    doc.add_run(" 成正比，即越远离中心，厚度增加越快，")
    doc.add_run("光程差变化越剧烈，导致相邻干涉环之间的间距越来越小，")
    doc.add_run("形成内疏外密的分布。")

    # ── 保存 ──
    doc.save()
    doc.close()


def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "平凸透镜曲率半径的测量.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    _generate_docx(data, DOCX_FILE)
    print(f"报告已生成: {DOCX_FILE}")


if __name__ == "__main__":
    main()
