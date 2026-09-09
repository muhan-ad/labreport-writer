"""电容与高电阻的测量实验 — 数据处理脚本。"""

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
# 实验参数（教材实验23）
# ============================================================

# 表 1 冲击法测电容的电压序列（教材表 3-23-1）
U_VALUES = [2.00, 4.00, 6.00, 8.00, 10.00, 12.00, 14.00, 16.00]

# 表 2 冲击法测高阻的数据组数（教材表 3-23-2）
N_POINTS_R = 16


# ============================================================
# Excel 模板生成
# ============================================================

# （方式三：_create_template 已移除，数据真相为 data.json）


# ============================================================
# 图表绘制
# ============================================================

def _plot_lnq_t(t_values: list[float], lnq_values: list[float],
                slope: float, intercept: float, output_path: str):
    """绘制 lnQ ~ t 关系图（数据点连线 + 直线拟合，复刻范例 Matlab 图）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    # 中文字体
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    x = np.array(t_values)
    y = np.array(lnq_values)

    fig, ax = plt.subplots(figsize=(8, 5.5))

    # 数据点连线（蓝色实线 + 圆点，对应范例 plot(x, y, '-o')）
    ax.plot(x, y, "-o", color="steelblue", markersize=5, linewidth=1.2,
            zorder=5, label="数据点连线")

    # 最小二乘拟合直线（红色虚线；图例不标数值，正文斜率用两点法）
    x_fit = np.linspace(x[0], x[-1], 100)
    y_fit = slope * x_fit + intercept
    ax.plot(x_fit, y_fit, "--", color="red", linewidth=1.5, label="拟合直线")

    # 坐标轴
    ax.set_xlabel("t(s)", fontsize=13)
    ax.set_ylabel("lnQ", fontsize=13)
    ax.set_title("数据点与直线拟合", fontsize=13)

    ax.grid(True, alpha=0.3, linestyle="--")
    ax.legend(fontsize=10, loc="upper right")

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


# ============================================================
# 数据处理（计算）
# ============================================================

def _compute(data: dict) -> dict:
    """由原始数据计算各物理量，返回数值键字典（供正文与变体 %%DATA 注入）。"""

    c_n = float(data["c_n"])          # 标准电容 / μF
    r_0 = float(data["r_0"])          # 电阻标称值 / MΩ
    q_n = [float(v) for v in data["q_n"]]
    q_x = [float(v) for v in data["q_x"]]
    t_values = [float(v) for v in data["t_values"]]
    q_values = [float(v) for v in data["q_values"]]

    # 表 1：逐点电容 C_x = (Q_x / Q_N) * C_N，再取平均
    c_x = [qx / qn * c_n for qx, qn in zip(q_x, q_n)]
    c_x_bar = mean(c_x)

    # 表 2：lnQ（表中保留 3 位小数，斜率用表中值计算，与范例一致）
    lnq = [round(math.log(v), 3) for v in q_values]

    # 两点法斜率（首末两点，范例做法）
    k_slope = (lnq[-1] - lnq[0]) / (t_values[-1] - t_values[0])
    k_abs = round(abs(k_slope), 4)          # 正文公式代入 4 位小数值
    r_mohm = 1.0 / (k_abs * c_n * 1e-6) / 1e6   # 高电阻 / MΩ
    delta_e = abs(r_mohm / r_0 - 1.0) * 100.0   # 相对误差 / %

    # 最小二乘拟合（仅用于绘制拟合直线）
    reg = linear_regression(t_values, lnq)

    return {
        "c_n": c_n, "r_0": r_0,
        "q_n": q_n, "q_x": q_x,
        "t_values": t_values, "q_values": q_values,
        "c_x": c_x, "c_x_bar": c_x_bar,
        "lnq": lnq,
        "k_slope": k_slope, "k_abs": k_abs,
        "r_mohm": r_mohm, "delta_e": delta_e,
        "reg": reg,
    }


# ============================================================
# docx 报告生成
# ============================================================

def _generate_docx(data: dict, output_path: str):
    """从 data.json 读取数据 → 计算 → 输出 docx 报告。"""

    # ---------- 1. 读取数据（含必填校验） ----------
    # 校验必填数据（required 字段为 null 或 array 含 null → 缺失）
    missing = []
    for k in ("c_n", "q_n", "q_x", "r_0", "t_values", "q_values"):
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

    # ---------- 2. 计算 ----------
    r = _compute(data)
    c_n = r["c_n"]
    r_0 = r["r_0"]
    q_n = r["q_n"]
    q_x = r["q_x"]
    t_values = r["t_values"]
    q_values = r["q_values"]
    c_x = r["c_x"]
    c_x_bar = r["c_x_bar"]
    lnq = r["lnq"]
    k_slope = r["k_slope"]
    k_abs = r["k_abs"]
    r_mohm = r["r_mohm"]
    delta_e = r["delta_e"]
    reg = r["reg"]

    # 打印到控制台
    print(f"\n{'=' * 50}")
    print("Table 1: capacitance by ballistic galvanometer")
    print(f"  C_x per point (uF): {[f'{v:.3f}' for v in c_x]}")
    print(f"  C_x mean = {c_x_bar:.2f} uF")
    print("\nTable 2: high resistance by RC discharge")
    print(f"  two-point slope K = {k_slope:.4f} (per s)")
    print(f"  least-squares slope = {reg.slope:.4f}, R^2 = {reg.r_squared:.4f}")
    print(f"  R = {r_mohm:.2f} MOhm  (nominal R_0 = {r_0:g} MOhm)")
    print(f"  relative error = {delta_e:.1f} %")
    print(f"{'=' * 50}\n")

    # ---------- 3. 绘制图表 ----------
    plot_path = os.path.join(SCRIPT_DIR, "lnQ-t图.png")
    _plot_lnq_t(t_values, lnq, reg.slope, reg.intercept, plot_path)
    print(f"Chart saved: {plot_path}")

    # ---------- 4. 生成 docx ----------
    doc = DocxReportWriter(output_path)

    # ---- 变体组合（存在 variants.json 且应用传入选择时生效）----
    variants = compose(SCRIPT_DIR, r)

    # ---- 零、实验标题 ----
    doc.add_title("电容与高电阻的测量实验")
    doc.add_student_info()

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

    # -- 1. 冲击法测电容 --
    doc.add_heading("1. 数字式冲击法测量电容值", level=2)

    doc.add_paragraph("")
    doc.add_run("由给定标准电容 ")
    doc.add_inline_math(rf"C_{{N}} = {c_n:.1f}\ \mathrm{{μF}}")
    doc.add_run("，按下式逐点计算被测电容：")
    doc.add_math(r"C_{x} = \frac{Q_{x}}{Q_{N}} \cdot C_{N}")

    doc.add_table(
        headers=["$U$ / V"] + [f"{u:.2f}" for u in U_VALUES],
        rows=[
            ["$Q_N$ / μC"] + [f"{v:.4g}" for v in q_n],
            ["$Q_x$ / μC"] + [f"{v:.3g}" for v in q_x],
            ["$C_x$ / μF"] + [f"{v:.3f}" for v in c_x],
        ],
        col_widths=[2.0] + [1.4] * 8,
    )

    doc.add_paragraph("取平均值：")
    doc.add_math(
        rf"\overline{{C_{{x}}}} = \frac{{1}}{{8}} \sum_{{i=1}}^{{8}} C_{{xi}}"
        rf" = {c_x_bar:.2f}\ \mathrm{{μF}}"
    )

    # -- 2. 冲击法测高阻 --
    doc.add_heading("2. 数字式冲击电流计测高阻", level=2)

    doc.add_paragraph("电容放电规律取对数后为")
    doc.add_math(r"\ln Q = -\frac{t}{RC} + \ln Q_{0}")

    doc.add_paragraph("")
    doc.add_run("以 t 为横坐标、")
    doc.add_inline_math(r"\ln Q")
    doc.add_run(" 为纵坐标作图，直线斜率即为 ")
    doc.add_inline_math(r"-\frac{1}{RC}")
    doc.add_run("。各点 ")
    doc.add_inline_math(r"\ln Q")
    doc.add_run(" 计算如下：")

    for start in (0, 8):
        seg = slice(start, start + 8)
        doc.add_table(
            headers=["序号"] + [str(i + 1) for i in range(start, start + 8)],
            rows=[
                ["t/s"] + [f"{v:.2f}" for v in t_values[seg]],
                ["Q/μC"] + [f"{v:.2f}" for v in q_values[seg]],
                ["lnQ"] + [f"{v:.3f}" for v in lnq[seg]],
            ],
            col_widths=[1.8] + [1.4] * 8,
        )

    doc.add_paragraph("根据上表数据作 lnQ-t 图：")
    doc.add_image(plot_path, width_cm=14)

    doc.add_paragraph("取首末两点计算直线斜率：")
    doc.add_math(
        rf"K = \frac{{\ln Q_{{16}} - \ln Q_{{1}}}}{{t_{{16}} - t_{{1}}}}"
        rf" = \frac{{{lnq[-1]:.3f} - {lnq[0]:.3f}}}{{{t_values[-1]:.2f} - {t_values[0]:.2f}}}"
        rf" \approx {k_slope:.4f} = -\frac{{1}}{{RC}}"
    )

    doc.add_paragraph("由斜率求得高电阻：")
    doc.add_math(
        rf"R = \frac{{1}}{{|K|C}} = \frac{{1}}{{{k_abs:.4f} \cdot {c_n:.1f} \cdot 10^{{-6}}}}"
        rf" \approx {r_mohm:.2f}\ \mathrm{{MΩ}}"
    )

    doc.add_paragraph("相对误差：")
    doc.add_math(
        rf"\Delta E = \left| \frac{{R}}{{R_{{0}}}} - 1 \right| \times 100%"
        rf" = {delta_e:.1f}%"
    )

    # ---- 变体组合：误差分析 / 结论 ----
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])
    if "结论" in variants:
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    # ---- 三、思考题 ----
    doc.add_heading("三、思考题", level=1)

    doc.add_heading(
        "1. 在冲击法测量高阻实验中，标准电容的单位为 μC，"
        "这个数量级是否会影响最终的测量结果？", level=2)
    doc.add_paragraph("")
    doc.add_run("不会。由公式 ")
    doc.add_inline_math(r"|k| = \left| \frac{\ln Q_{0} - \ln Q_{t}}{t_{0} - t_{t}} \right|")
    doc.add_run(" 化简变形可得 ")
    doc.add_inline_math(r"|k| = \left| \frac{\ln \frac{Q_{0}}{Q_{t}}}{t_{0} - t_{t}} \right|")
    doc.add_run("，")
    doc.add_inline_math(r"Q_{0}")
    doc.add_run(" 和 ")
    doc.add_inline_math(r"Q_{t}")
    doc.add_run(" 上下比值相消，不影响最终的测量结果。")

    doc.add_heading("2. 放电法测量高阻阻值，最长放电时间的选择依据是什么？", level=2)
    doc.add_paragraph("")
    doc.add_inline_math(r"\ln Q = -\frac{t}{RC} + \ln Q_{0}")
    doc.add_run("，当 ")
    doc.add_inline_math(r"\ln Q = 0")
    doc.add_run(" 时，")
    doc.add_inline_math(r"t = RC \cdot \ln Q_{0}")
    doc.add_run("，且 ")
    doc.add_inline_math(r"Q_{0} = C_{n} u")
    doc.add_run("，故最长放电时间的选择依据是 t、")
    doc.add_inline_math(r"C_{n}")
    doc.add_run(" 和 u。应保证最长放电时间不超过 16~17 s。")

    doc.save()
    doc.close()


# ============================================================
# 入口
# ============================================================

def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "电容与高电阻的测量实验报告.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    _generate_docx(data, DOCX_FILE)
    print(f"报告已生成: {DOCX_FILE}")


if __name__ == "__main__":
    main()
