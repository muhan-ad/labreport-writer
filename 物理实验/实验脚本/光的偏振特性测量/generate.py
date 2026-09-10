"""偏振光鉴别与马吕斯定律验证实验 — 数据处理脚本。"""

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
# 物理常数 / 实验参数
# ============================================================

# 马吕斯定律验证的角度序列（教材表 3-11-3）
THETA_DEG = [0, 15, 30, 45, 60, 75, 90]

# cos²θ 理论值（预计算，保留 3 位小数）
COS2_THETA = [round(math.cos(math.radians(t)) ** 2, 3) for t in THETA_DEG]
# → [1.0, 0.933, 0.75, 0.5, 0.25, 0.067, 0.0]

# 仪器参数（半导体激光器 λ=650nm，光功率计分辨率）
DELTA_INSTRUMENT = 0.001  # 光功率计仪器误差 / mW


# ============================================================
# Excel 模板生成
# ============================================================

# （方式三：_create_template 已移除，数据真相为 data.json）


# ============================================================
# 图表绘制
# ============================================================

def _plot_malus(cos2theta: list[float], p_diff: list[float],
                slope: float, r_squared: float, output_path: str):
    """绘制 (P-Pmin) ~ cos²θ 验证马吕斯定律曲线图。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    # 中文字体
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    x = np.array(cos2theta)
    y = np.array(p_diff)

    fig, ax = plt.subplots(figsize=(8, 5.5))

    # 数据点（蓝色圆点）
    ax.scatter(x, y, color="steelblue", s=60, zorder=5, label="实验数据")

    # 线性拟合线（红色虚线）
    x_fit = np.linspace(0, 1.05, 100)
    y_fit = slope * x_fit
    ax.plot(x_fit, y_fit, "--", color="red", linewidth=1.5,
            label=f"线性拟合 $y = {slope:.4f}x$\n$R^2 = {r_squared:.4f}$")

    # 坐标轴
    ax.set_xlabel(r"$\cos^2(\theta)$", fontsize=13)
    ax.set_ylabel(r"$P - P_{\min}$ / mW", fontsize=13)
    ax.set_title(r"验证马吕斯定律 $(P-P_{\min}) \sim \cos^2(\theta)$ 变化关系曲线", fontsize=13)
    ax.set_xlim(-0.02, 1.05)
    ax.set_ylim(bottom=-0.02)

    # 网格
    ax.grid(True, alpha=0.3, linestyle="--")

    # 图例
    ax.legend(fontsize=10, loc="upper left")

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


# ============================================================
# 数据处理计算
# ============================================================

def _compute(data: dict) -> dict:
    """由各角度透射功率读数计算 P_min、P-P_min 与线性回归，返回结果字典 r。"""
    p_values = [float(v) for v in data["p_values"]]
    cos2_values = [float(v) for v in data["cos2_values"]]

    # P_min = P 在 θ=90° (最后一列, cos²θ=0) 处的值
    p_min = p_values[-1]

    # P - P_min
    p_diff = [p - p_min for p in p_values]
    p_min_rounded = round(p_min, 4) if p_min >= 0.001 else round(p_min, 4)

    # 线性回归 y = a + bx (y: P-Pmin, x: cos²θ)
    reg = linear_regression(cos2_values, p_diff)

    return {
        "p_values": p_values, "cos2_values": cos2_values,
        "p_min": p_min, "p_diff": p_diff,
        "p_max": p_values[0],
        "slope": reg.slope, "slope_uncertainty": reg.slope_uncertainty,
        "intercept": reg.intercept, "intercept_uncertainty": reg.intercept_uncertainty,
        "r_squared": reg.r_squared, "corr_r": reg.r,
        "intercept_ok": abs(reg.intercept) < 2.0 * reg.intercept_uncertainty,
    }


# ============================================================
# docx 报告生成
# ============================================================

def _generate_docx(data: dict, output_path: str):
    """从 data.json 读取数据，计算并输出 docx 报告。"""
    # ---------- 1. 读取数据（含空值校验） ----------
    # 校验必填数据（required 字段为 null 或 array 含 null → 缺失）
    missing = []
    for k in ("p_values", "cos2_values"):
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

    # ---------- 2. 计算（见 _compute） ----------
    r = _compute(data)
    cos2_values = r["cos2_values"]
    p_diff = r["p_diff"]
    p_min = r["p_min"]
    slope = r["slope"]
    slope_uncertainty = r["slope_uncertainty"]
    intercept = r["intercept"]
    intercept_uncertainty = r["intercept_uncertainty"]
    r_squared = r["r_squared"]
    corr_r = r["corr_r"]

    # 打印到控制台
    print(f"\n{'='*50}")
    print(f"P_min = {p_min} mW  (theta=90 deg, P value)")
    print(f"\nLinear regression (y = a + bx):")
    print(f"  intercept a = {intercept:.6f} +/- {intercept_uncertainty:.6f} mW")
    print(f"  slope b     = {slope:.6f} +/- {slope_uncertainty:.6f} mW")
    print(f"  R^2 = {r_squared:.6f}")
    print(f"  r   = {corr_r:.6f}")
    print(f"\nMalus's Law: P-Pmin = k * cos^2(theta)  (through origin)")
    print(f"  Experiment: P-Pmin = {intercept:.4f} + {slope:.4f} * cos^2(theta)")
    if abs(intercept) < 2.0 * intercept_uncertainty:
        print(f"  => Intercept within 2 sigma of zero, Malus's Law verified.")
    else:
        print(f"  => Intercept deviates significantly from zero, check experiment conditions.")
    print(f"{'='*50}\n")

    # ---------- 3. 绘制图表 ----------
    plot_path = os.path.join(SCRIPT_DIR, "马吕斯定律验证图.png")
    _plot_malus(cos2_values, p_diff, slope, r_squared, plot_path)
    print(f"Chart saved: {plot_path}")

    # ---------- 4. 生成 docx ----------
    doc = DocxReportWriter(output_path)

    # ---- 零、实验标题 ----
    doc.add_title("光的偏振特性测量")
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

    doc.add_paragraph("验证马吕斯定律：以 P - Pmin 为纵坐标、cos²θ 为横坐标作图。")
    doc.add_paragraph("若图线为通过坐标原点的直线，则表明马吕斯定律已被验证。")

    # 仅插入图表，不输出数学公式
    doc.add_image(plot_path, width_cm=14)

    # 简单附注回归结果
    doc.add_paragraph("")
    doc.add_run("线性拟合结果：截距 a = ")
    doc.add_inline_math(f"{intercept:.6f}\\ \\mathrm{{mW}}")
    doc.add_run("，斜率 b = ")
    doc.add_inline_math(f"{slope:.4f}\\ \\mathrm{{mW}}")
    doc.add_run("，")
    doc.add_inline_math(f"R^2 = {r_squared:.4f}")
    doc.add_run("。")

    # ---- 三、实验结果分析 ----
    doc.add_heading("三、实验结果分析", level=1)

    # 根据截距是否在 2σ 范围内判零，使用 add_run + add_inline_math 混合排版
    intercept_ok = abs(intercept) < 2.0 * intercept_uncertainty

    # 开头公共段落
    doc.add_paragraph("")
    doc.add_run("由 ")
    doc.add_inline_math(r"(P - P_{\min}) \sim \cos^2(\theta)")
    doc.add_run(" 关系图可见，实验数据点基本分布在一条")

    if intercept_ok:
        doc.add_run("过原点的直线上（拟合截距 ")
        doc.add_inline_math(f"a = {intercept:.4f}\\ \\mathrm{{mW}}")
        doc.add_run("，在 2σ 范围内与零一致），线性相关系数 ")
    else:
        doc.add_run("直线上，但拟合截距 ")
        doc.add_inline_math(f"a = {intercept:.4f}\\ \\mathrm{{mW}}")
        doc.add_run("，偏离零值超过 2σ，线性相关系数 ")

    doc.add_inline_math(f"R^2 = {r_squared:.4f}")
    doc.add_run("，线性关系良好。")

    if intercept_ok:
        doc.add_run("实验结果表明，透射光功率差 ")
        doc.add_inline_math("P - P_{\\min}")
        doc.add_run(" 与 ")
        doc.add_inline_math(r"\cos^2(\theta)")
        doc.add_run(" 成正比关系，验证了马吕斯定律 ")
        doc.add_inline_math(r"I = I_0 \cos^2(\theta)")
        doc.add_run("。")
    else:
        doc.add_run("截距偏离零值表明存在一定系统误差，但整体线性趋势仍基本符合马吕斯定律。")

    doc.add_paragraph(
        "误差来源分析：（1）半导体激光器的光功率可能存在微小波动，影响测量稳定性；"
        "（2）偏振片旋转角度的读数误差，手工旋转偏振片难以精确定位角度；"
        "（3）环境杂散光对光功率计的影响，尤其在 P 接近 Pmin 时杂散光占比增大；"
        "（4）光路未严格同轴，导致部分光束偏离光功率计探头中心。"
    )

    # ---- 变体组合：误差分析 / 结论（存在 variants.json 且应用传入选择时生效）----
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])
    if "结论" in variants:
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    # ---- 四、课后思考题 ----
    doc.add_heading("四、课后思考题", level=1)

    doc.add_heading("1. 为什么自然光经过 1/4 波片后透射光仍然为自然光？", level=2)
    doc.add_paragraph(
        "自然光是由许多不同方向振动的光波组成的，其偏振方向是随机的。"
        "1/4 波片的作用是使两个相互垂直的偏振分量产生 90° 的相位差，"
        "但自然光中包含无数个随机方向的偏振分量，"
        "因此经过 1/4 波片后，这些偏振分量的相位差变化是随机的，"
        "整体上仍然表现为无规律的偏振状态，即自然光。"
    )

    doc.add_heading("2. 实验室里有偏振片、1/4波片和1/2波片各一块，如何将它们区分开？", level=2)
    doc.add_paragraph(
        "首先，将每个元件分别放置在自然光源前，旋转该元件，观察透过元件的光强变化。"
        "当旋转时透射光强出现明显变化的是偏振片，剩下的两个是波片。"
        "然后，将已知的偏振片作为起偏器放置在光源前，调整偏振方向使光强达到最大。"
        "将两波片分别放置在偏振片后面，再将检偏器放置在该波片后面。"
        "旋转波片，观察透过检偏器的光强变化。"
        "如果旋转波片时光强没有明显变化，则该波片是 1/4 波片；"
        "如果旋转波片时光强有明显变化，则该波片是 1/2 波片。"
    )

    doc.save()
    doc.close()


# ============================================================
# 入口
# ============================================================

def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "光的偏振特性测量实验报告.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    _generate_docx(data, DOCX_FILE)
    print(f"报告已生成: {DOCX_FILE}")


if __name__ == "__main__":
    main()
