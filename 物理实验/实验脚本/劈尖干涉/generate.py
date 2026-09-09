"""劈尖干涉 — 数据处理脚本。

用等厚干涉原理（空气劈尖）测量细丝直径。
教材：实验 24，公式 (3-24-1)~(3-24-4)、数据表 3-24-1。
"""

import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import *
from common.docx_report import DocxReportWriter
from common.data_io import load_data

# ── 物理常数 ──
LAMBDA_NM = 589.3              # 钠光灯波长 (nm)
LAMBDA_MM = 589.3e-6           # 钠光灯波长 (mm)
DELTA_INSTRUMENT = 0.004       # 15J 测量显微镜仪器误差 (mm)
SKIP_N = 40                    # 逐差法间隔（条）
T_FACTOR = 1.2                 # t 因子 (n=4, df=3, P=0.683)

# 注：方式三迁移后数据来自 data.json（schema.json 定义），
# 读取坐标为：x_k ← B5:B12，X1 ← A16，X2 ← B16（见 _create_template 模板布局）。


# ═══════════════════════════════════════════════════════════════════
# Excel 模板创建（方式三迁移后不再调用，仅保留模板结构备查）
# ═══════════════════════════════════════════════════════════════════

# （方式三：_create_template 已移除，数据真相为 data.json）


# ═══════════════════════════════════════════════════════════════════
# 数据处理与 docx 生成
# ═══════════════════════════════════════════════════════════════════

def _validate_data(data: dict) -> list[str]:
    """检查必填数据是否已填写（required 字段为 null 或 array 含 null → 缺失）。

    返回缺失字段列表，空列表表示全部已填。
    """
    missing = []

    # 检查暗纹位置读数 x_0 ~ x_70
    x_k = data.get("x_k") or []
    k_labels = ["x_0", "x_10", "x_20", "x_30", "x_40", "x_50", "x_60", "x_70"]
    for i, label in enumerate(k_labels):
        if i >= len(x_k) or x_k[i] is None:
            missing.append(label)

    # 检查劈尖长度
    for key, label in [("X1", "X1 (劈尖棱边)"), ("X2", "X2 (细丝位置)")]:
        if data.get(key) is None:
            missing.append(label)

    return missing


def _generate_docx(data: dict, output_path: str):
    """读取 data.json 数据，计算并生成 Word 实验报告。"""

    # ── 1. 读取数据 ──
    x_k = [float(v) for v in data["x_k"]]  # x_0, x_10, ..., x_70
    X1 = float(data["X1"])
    X2 = float(data["X2"])

    # ── 2. 逐差法计算 ──
    # l_k = |x_{k+40} - x_k|，k = 0, 10, 20, 30（共 4 组）
    l_k = [abs(x_k[i + 4] - x_k[i]) for i in range(4)]
    # 40 条暗纹间距的平均值
    l_bar_k = mean(l_k)
    # 相邻暗纹间距（教材中的 l̄）
    s = l_bar_k / SKIP_N
    # 劈尖长度
    L = abs(X1 - X2)
    # 细丝直径（公式 3-24-4）
    d_bar = L / s * (LAMBDA_MM / 2)

    # ── 3. 不确定度分析 ──
    # A 类不确定度
    s_l = std_dev(l_k)                        # 四个 l_k 的标准差
    sigma_l = s_l * T_FACTOR                  # P=0.683 置信扩展
    sigma3 = 3 * sigma_l                       # 3σ 检验阈值
    abs_dev_max = max(abs(li - l_bar_k) for li in l_k)
    no_outlier = abs_dev_max < sigma3          # True = 经检验无坏值
    u_A = sigma_l / math.sqrt(4)              # 平均值的 A 类不确定度

    # B 类不确定度
    u_B = type_b(DELTA_INSTRUMENT)            # Δ_仪 / √3

    # 合成不确定度（对 l̄_k 的）
    u_l = combine(u_A, u_B)

    # 误差传递到直径 d ∝ 1/l̄_k
    u_d = u_l / l_bar_k * d_bar

    # 结果格式化
    d_display = format_number(d_bar, u_d)
    u_d_display = format_number(u_d, u_d)

    # ── 4. 生成 docx 报告 ──
    doc = DocxReportWriter(output_path)

    # ════════════════════════════════
    # 零、实验标题
    # ════════════════════════════════
    doc.add_title("劈尖干涉测量细丝直径")
    doc.add_student_info()

    # ════════════════════════════════
    # 一、原始数据记录
    # ════════════════════════════════
    doc.add_heading("一、原始数据记录", level=1)
    doc.add_paragraph("请在下方粘贴劈尖干涉条纹原始数据记录照片。")

    doc.add_heading("1.1 实验数据记录表", level=2)

    # 数据表
    table_headers = ["$k$", "$x_k$ / mm", "$l_k = |x_{k+40} - x_k|$ / mm"]
    # 构建表格行：k=0~30 行有 l_k，k=40~70 行 l_k 留空
    table_rows = []
    k_labels = [0, 10, 20, 30, 40, 50, 60, 70]
    for i, kl in enumerate(k_labels):
        if i < 4:
            table_rows.append([
                str(kl),
                format_number(x_k[i]),
                format_number(l_k[i]),
            ])
        else:
            table_rows.append([
                str(kl),
                format_number(x_k[i]),
                "—",
            ])
    doc.add_table(table_headers, table_rows, col_widths=[1.5, 4, 5])

    doc.add_paragraph("")
    doc.add_run("劈尖长度测量：")
    doc.add_inline_math(f"X_1 = {format_number(X1)}\\,\\mathrm{{mm}}")
    doc.add_run("，")
    doc.add_inline_math(f"X_2 = {format_number(X2)}\\,\\mathrm{{mm}}")
    doc.add_run("，")
    doc.add_inline_math(f"L = |X_1 - X_2| = {format_number(L)}\\,\\mathrm{{mm}}")

    # ════════════════════════════════
    # 二、数据处理
    # ════════════════════════════════
    doc.add_heading("二、数据处理", level=1)

    # ── 已知参数 ──
    doc.add_heading("2.1 已知参数", level=2)
    doc.add_paragraph("")
    doc.add_run("钠光灯波长 ")
    doc.add_inline_math(fr"\lambda = {LAMBDA_NM}\,\mathrm{{nm}} = {format_scientific(LAMBDA_MM)}\,\mathrm{{mm}}")
    doc.add_run("，仪器误差 ")
    doc.add_inline_math(r"\Delta_{\text{仪}} = " + format_number(DELTA_INSTRUMENT) + r"\,\mathrm{mm}")
    doc.add_run("。")

    # ── 逐差法 ──
    doc.add_heading("2.2 逐差法求相邻暗纹间距", level=2)

    doc.add_paragraph("")
    doc.add_run("每移动 10 条暗纹记录一次位置 x_k，共 8 个读数。采用逐差法，间隔 40 条暗纹配对：")

    # 列出 4 组 l_k
    k_indices = [0, 10, 20, 30]
    for i, ki in enumerate(k_indices):
        doc.add_paragraph("")
        doc.add_run(f"第 {i+1} 组（k={ki} 与 k={ki+40}）：")
        doc.add_inline_math(
            f"l_{{{ki}}} = |x_{{{ki+40}}} - x_{{{ki}}}| "
            f"= |{format_number(x_k[i+4])} - {format_number(x_k[i])}| "
            f"= {format_number(l_k[i])}\\,\\mathrm{{mm}}"
        )

    doc.add_paragraph("40 条暗纹间距的平均值：")
    doc.add_math(
        r"\bar{l}_k = \frac{l_0 + l_{10} + l_{20} + l_{30}}{4} = "
        + format_number(l_bar_k) + r"\,\mathrm{mm}"
    )

    doc.add_paragraph("相邻暗纹间距：")
    doc.add_math(
        r"\bar{l} = \frac{\bar{l}_k}{40} = "
        + format_number(s) + r"\,\mathrm{mm}"
    )

    # ── 细丝直径 ──
    doc.add_heading("2.3 细丝直径", level=2)

    doc.add_paragraph("由劈尖干涉公式（3-24-4）：")
    doc.add_math(
        r"\bar{d} = \frac{L}{\bar{l}} \cdot \frac{\lambda}{2}"
        r" = \frac{" + format_number(L) + r"}{" + format_number(s) + r"}"
        r" \cdot \frac{" + format_scientific(LAMBDA_MM) + r"}{2}"
        r" = " + format_number(d_bar) + r"\,\mathrm{mm}"
    )

    # ── A 类不确定度 ──
    doc.add_heading("2.4 A 类不确定度", level=2)

    doc.add_paragraph("对 4 组 l_k 值进行统计分析：")
    doc.add_math(
        r"s = \sqrt{\frac{1}{4-1} \sum_{i=0}^{3} (\bar{l}_k - l_{10i})^{2}} = "
        + format_number(s_l) + r"\,\mathrm{mm}"
    )
    doc.add_paragraph("")
    doc.add_run("小样本（n = 4），取 t 因子 ")
    doc.add_inline_math(f"t = {T_FACTOR}")
    doc.add_run("（df = 3，P = 0.683）：")
    doc.add_math(
        r"\sigma = s \cdot t = " + format_number(s_l) + r" \times " + str(T_FACTOR)
        + r" = " + format_number(sigma_l) + r"\,\mathrm{mm}"
    )
    doc.add_paragraph("")
    doc.add_run("3σ 检验：")
    doc.add_inline_math(f"3\\sigma = {format_number(sigma3)}\\,\\mathrm{{mm}}")
    doc.add_run(
        f"，各组偏差绝对值最大为 {format_number(abs_dev_max)} mm"
        + (" < 3σ" if no_outlier else " ≥ 3σ!!!")
        + "，经检验无坏值。" if no_outlier else "，存在坏值，请检查数据！"
    )
    doc.add_paragraph("平均值的 A 类不确定度：")
    doc.add_math(
        r"\Delta x_A = \frac{\sigma}{\sqrt{4}} = "
        + format_number(u_A) + r"\,\mathrm{mm}"
    )

    # ── B 类不确定度 ──
    doc.add_heading("2.5 B 类不确定度", level=2)

    doc.add_paragraph("由测量显微镜仪器误差引入，按均匀分布处理：")
    doc.add_math(
        r"\Delta x_B = \frac{\Delta_{\text{仪}}}{\sqrt{3}}"
        r" = \frac{" + format_number(DELTA_INSTRUMENT) + r"}{\sqrt{3}}"
        r" = " + format_number(u_B) + r"\,\mathrm{mm}"
    )

    # ── 合成不确定度 ──
    doc.add_heading("2.6 合成不确定度与测量结果", level=2)

    doc.add_paragraph("l̄_k 的合成不确定度：")
    doc.add_math(
        r"\Delta l = \sqrt{\Delta x_A^{2} + \Delta x_B^{2}}"
        r" = \sqrt{" + format_number(u_A) + r"^{2} + " + format_number(u_B) + r"^{2}}"
        r" = " + format_number(u_l) + r"\,\mathrm{mm}"
    )

    doc.add_paragraph("不确定度传递到细丝直径（d ∝ 1/l̄_k）：")
    doc.add_math(
        r"\Delta d = \frac{\Delta l}{\bar{l}_k} \cdot \bar{d}"
        r" = \frac{" + format_number(u_l) + r"}{" + format_number(l_bar_k) + r"}"
        r" \times " + format_number(d_bar)
        + r" = " + format_number(u_d) + r"\,\mathrm{mm}"
    )

    doc.add_paragraph("细丝直径测量结果：")
    doc.add_math(
        r"d = \bar{d} \pm \Delta d = ("
        + d_display + r" \pm " + u_d_display + r")\,\mathrm{mm}"
    )

    # ════════════════════════════════
    # 三、课后思考题
    # ════════════════════════════════
    doc.add_heading("三、课后思考题", level=1)

    doc.add_heading(
        "1. 如果形成空气劈尖的两块玻璃板内表面凹凸不平，空气薄膜的等厚干涉条纹还平行于棱边吗？为什么？",
        level=2,
    )
    doc.add_paragraph(
        "答：不会平行于棱边。因为玻璃板的内表面凹凸不平会导致空气薄膜厚度不均匀，"
        "光程差不再简单地沿棱边方向线性变化，从而导致干涉条纹形状也发生变化，"
        "不再是平行直条纹，而是呈现出与表面凹凸对应的弯曲形态。"
    )

    doc.add_heading(
        "2. 如果形成空气劈尖的两块玻璃板上板为标准平面，如何根据等厚干涉条纹的形状判断下板某处是凹还是凸？",
        level=2,
    )
    doc.add_paragraph(
        "答：可以通过观察条纹的弯曲方向来判断。若干涉条纹向劈尖棱边方向（空气层较薄一侧）弯曲，"
        "则表明该处下板表面为凸起（该处空气膜偏薄，同级干涉条纹向薄处偏移）；"
        "相反，若干涉条纹背离棱边方向（空气层较厚一侧）弯曲，则该处为凹陷。"
    )

    # ── 保存 ──
    doc.save()
    doc.close()


# ═══════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════

def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "劈尖干涉实验报告.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    # 检查数据是否已填写
    missing = _validate_data(data)
    if missing:
        print()
        print("=" * 50)
        print("  [!] 数据未填写完整，请先填写以下数据后重新运行：")
        print("=" * 50)
        for label in missing:
            print(f"    - {label}")
        print("=" * 50)
        print()
        print(f"  文件位置: {DATA_FILE}")
        print()
        return

    _generate_docx(data, DOCX_FILE)
    print(f"报告已生成: {DOCX_FILE}")


if __name__ == "__main__":
    main()
