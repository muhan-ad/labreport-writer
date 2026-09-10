# -*- coding: utf-8 -*-
"""电子束的电磁偏转 — 数据处理脚本。"""
import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import *
from common.docx_report import DocxReportWriter
from common.data_io import load_data

# 给定量（教材，预填入模板）
D_VALS = [-16.0, -12.0, -8.0, -4.0, 0.0, 4.0, 8.0, 12.0, 16.0]  # 屏上偏转量 D/mm
U2_LIST = (1000, 900, 800)  # 阳极加速电压 U2/V（三张表相同）

# ---- 数据.xlsx 布局（模板与读取区共用，行号一一对应）----
T1_TITLE, T1_D, T1_R1000, T1_R900, T1_R800 = 3, 4, 5, 6, 7      # 表1 X轴电偏转 U_dx/V
T2_TITLE, T2_D, T2_R1000, T2_R900, T2_R800 = 9, 10, 11, 12, 13  # 表2 Y轴电偏转 U_dy/V
T3_TITLE, T3_D, T3_R1000, T3_R900, T3_R800 = 15, 16, 17, 18, 19  # 表3 磁偏转 I_m/mA
DATA_START_COL, DATA_END_COL = "B", "J"  # 每表 9 个数据列
N_POINTS = 9


# （方式三：_create_template 已移除，数据真相为 data.json）


def _row_values(data, row_no):
    """从 data.json（load_data 得到的 dict）取某数据表行的 9 个测量值。

    三张表各含：给定偏转量 D（array）与 3 行测量值（matrix，第 0/1/2 行对应
    U2=1000/900/800V）。键名与 schema.json、data.json 保持一致。
    """
    return {
        T1_D: data["D_x"],
        T1_R1000: data["Udx"][0], T1_R900: data["Udx"][1], T1_R800: data["Udx"][2],
        T2_D: data["D_y"],
        T2_R1000: data["Udy"][0], T2_R900: data["Udy"][1], T2_R800: data["Udy"][2],
        T3_D: data["D_m"],
        T3_R1000: data["Im"][0], T3_R900: data["Im"][1], T3_R800: data["Im"][2],
    }[row_no]


def _plot_fit_pair(x1000, reg1000, x800, reg800, d1000, d800,
                   xlabel, sym, val1000, val800, unit, fig_path):
    """一张坐标系画 U2=1000V/800V 两组数据点 + 拟合直线，并标注灵敏度"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
    plt.rcParams["axes.unicode_minus"] = False
    C1000, C800 = "#2c5f9e", "#e07b39"  # 蓝/橙，CVD 安全对

    fig, ax = plt.subplots(figsize=(5.5, 3.8), dpi=200)
    for x, reg, d, color, u2 in ((x1000, reg1000, d1000, C1000, 1000),
                                 (x800, reg800, d800, C800, 800)):
        ax.plot(x, d, "o" if u2 == 1000 else "s", color=color, markersize=6,
                linestyle="", label=f"$U_2$={u2}V")
        x_fit = [min(x), max(x)]
        y_fit = [reg.slope * xi + reg.intercept for xi in x_fit]
        ax.plot(x_fit, y_fit, "-", color=color, linewidth=1.5,
                label=f"$U_2$={u2}V 拟合直线")
    ax.text(0.03, 0.97, f"$U_2$=1000V: ${sym}$={val1000:.3f} {unit}",
            transform=ax.transAxes, va="top", color=C1000, fontsize=9)
    ax.text(0.03, 0.89, f"$U_2$=800V:  ${sym}$={val800:.3f} {unit}",
            transform=ax.transAxes, va="top", color=C800, fontsize=9)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("D/mm")
    ax.grid(True, linestyle="--", linewidth=0.5, color="#cccccc")
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_color("#999999")
    ax.legend(frameon=False, loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(fig_path, facecolor="white")
    plt.close(fig)


def _generate_docx(data: dict, output_path: str):
    """读取 → 计算 → 输出 docx"""
    # ---- 1. 读取 + 空值校验 ----
    rows = {}
    layout = (
        ("表1 D", T1_D), ("表1 U2=1000V Udx", T1_R1000),
        ("表1 U2=900V Udx", T1_R900), ("表1 U2=800V Udx", T1_R800),
        ("表2 D", T2_D), ("表2 U2=1000V Udy", T2_R1000),
        ("表2 U2=900V Udy", T2_R900), ("表2 U2=800V Udy", T2_R800),
        ("表3 D", T3_D), ("表3 U2=1000V Im", T3_R1000),
        ("表3 U2=900V Im", T3_R900), ("表3 U2=800V Im", T3_R800),
    )
    check_cells = {}
    for name, row_no in layout:
        values = _row_values(data, row_no)
        rows[row_no] = values
        for j, v in enumerate(values):
            check_cells[f"{name} 第{j + 1}点"] = v
    missing = sorted(k for k, v in check_cells.items() if v is None)
    if missing:
        print("data.json 以下测量数据尚未填写，请补齐后重新运行：")
        for m in missing:
            print(f"  {m}")
        return

    rows = {k: [float(v) for v in vals] for k, vals in rows.items()}

    # ---- 2. 最小二乘拟合（照教材/范例只用 U2=1000V 和 800V 两组，900V 不参与拟合）----
    # x = 偏转电压/电流（自变量），y = D（因变量），斜率即灵敏度 ΔD/Δx
    reg_x_1000 = linear_regression(rows[T1_R1000], rows[T1_D])
    reg_x_800 = linear_regression(rows[T1_R800], rows[T1_D])
    reg_y_1000 = linear_regression(rows[T2_R1000], rows[T2_D])
    reg_y_800 = linear_regression(rows[T2_R800], rows[T2_D])
    reg_m_1000 = linear_regression(rows[T3_R1000], rows[T3_D])
    reg_m_800 = linear_regression(rows[T3_R800], rows[T3_D])
    # 磁偏转灵敏度按范例取绝对值 δm = |ΔD/ΔIm|
    dm_1000, dm_800 = abs(reg_m_1000.slope), abs(reg_m_800.slope)

    # ---- 3. 控制台摘要（便于誊抄）----
    print("表1 D-Udx 拟合（X 轴电偏转灵敏度）：")
    print(f"  U2=1000V: εx = {reg_x_1000.slope:.3f} mm/V, r = {reg_x_1000.r:.5f}")
    print(f"  U2=800V:  εx = {reg_x_800.slope:.3f} mm/V, r = {reg_x_800.r:.5f}")
    print("表2 D-Udy 拟合（Y 轴电偏转灵敏度）：")
    print(f"  U2=1000V: εy = {reg_y_1000.slope:.3f} mm/V, r = {reg_y_1000.r:.5f}")
    print(f"  U2=800V:  εy = {reg_y_800.slope:.3f} mm/V, r = {reg_y_800.r:.5f}")
    print("表3 D-Im 拟合（磁偏转灵敏度）：")
    print(f"  U2=1000V: δm = {dm_1000:.3f} mm/mA, r = {reg_m_1000.r:.5f}")
    print(f"  U2=800V:  δm = {dm_800:.3f} mm/mA, r = {reg_m_800.r:.5f}")

    # ---- 4. 绘图 ----
    fig1_path = os.path.join(SCRIPT_DIR, "_fig_D_Udx.png")
    fig2_path = os.path.join(SCRIPT_DIR, "_fig_D_Udy.png")
    fig3_path = os.path.join(SCRIPT_DIR, "_fig_D_Im.png")
    try:
        _plot_fit_pair(rows[T1_R1000], reg_x_1000, rows[T1_R800], reg_x_800,
                       rows[T1_D], rows[T1_D], "$U_{dx}$/V", r"\varepsilon_x",
                       reg_x_1000.slope, reg_x_800.slope, "mm/V", fig1_path)
        _plot_fit_pair(rows[T2_R1000], reg_y_1000, rows[T2_R800], reg_y_800,
                       rows[T2_D], rows[T2_D], "$U_{dy}$/V", r"\varepsilon_y",
                       reg_y_1000.slope, reg_y_800.slope, "mm/V", fig2_path)
        _plot_fit_pair(rows[T3_R1000], reg_m_1000, rows[T3_R800], reg_m_800,
                       rows[T3_D], rows[T3_D], "$I_m$/mA", r"\delta_m",
                       dm_1000, dm_800, "mm/mA", fig3_path)
    except ImportError:
        print("未安装 matplotlib，无法绘制曲线图。请先执行: pip install matplotlib")
        return

    # ---- 5. docx 输出 ----
    doc = DocxReportWriter(output_path)
    doc.add_title("电子偏转特性的测量")
    doc.add_student_info()

    doc.add_heading("一、原始数据记录", level=1)
    doc.add_paragraph("请在下方粘贴原始数据记录照片。")

    doc.add_heading("二、数据处理", level=1)

    # X 轴电偏转
    doc.add_paragraph("依据表1，用 ")
    doc.add_inline_math(r"U_{2} = 1000\,\mathrm{V}")
    doc.add_run(" 和 ")
    doc.add_inline_math(r"U_{2} = 800\,\mathrm{V}")
    doc.add_run(" 两组数据在同一坐标系中作 ")
    doc.add_inline_math(r"D - U_{dx}")
    doc.add_run(" 曲线，对数据点作最小二乘线性拟合，直线斜率即为 X 轴的电偏转灵敏度：")
    doc.add_math(r"\varepsilon_{x} = \frac{\Delta D}{\Delta U_{dx}}")
    doc.add_image(fig1_path, width_cm=12)
    doc.add_paragraph("图1 ")
    doc.add_inline_math(r"D - U_{dx}")
    doc.add_run(" 关系曲线")
    doc.add_paragraph("拟合得 ")
    doc.add_inline_math(r"U_{2} = 1000\,\mathrm{V}")
    doc.add_run(" 时 ")
    doc.add_inline_math(f"\\varepsilon_{{x}} = {reg_x_1000.slope:.3f}" + r"\,\mathrm{mm/V}")
    doc.add_run("（相关系数 ")
    doc.add_inline_math(f"r = {reg_x_1000.r:.5f}")
    doc.add_run("）；")
    doc.add_inline_math(r"U_{2} = 800\,\mathrm{V}")
    doc.add_run(" 时 ")
    doc.add_inline_math(f"\\varepsilon_{{x}} = {reg_x_800.slope:.3f}" + r"\,\mathrm{mm/V}")
    doc.add_run("（相关系数 ")
    doc.add_inline_math(f"r = {reg_x_800.r:.5f}")
    doc.add_run("）。可见加速电压 ")
    doc.add_inline_math(r"U_{2}")
    doc.add_run(" 越小，X 轴的电偏转灵敏度 ")
    doc.add_inline_math(r"\varepsilon_{x}")
    doc.add_run(" 越大。")

    # Y 轴电偏转
    doc.add_paragraph("依据表2，同上作 ")
    doc.add_inline_math(r"D - U_{dy}")
    doc.add_run(" 曲线并作最小二乘线性拟合，直线斜率即为 Y 轴的电偏转灵敏度：")
    doc.add_math(r"\varepsilon_{y} = \frac{\Delta D}{\Delta U_{dy}}")
    doc.add_image(fig2_path, width_cm=12)
    doc.add_paragraph("图2 ")
    doc.add_inline_math(r"D - U_{dy}")
    doc.add_run(" 关系曲线")
    doc.add_paragraph("拟合得 ")
    doc.add_inline_math(r"U_{2} = 1000\,\mathrm{V}")
    doc.add_run(" 时 ")
    doc.add_inline_math(f"\\varepsilon_{{y}} = {reg_y_1000.slope:.3f}" + r"\,\mathrm{mm/V}")
    doc.add_run("（相关系数 ")
    doc.add_inline_math(f"r = {reg_y_1000.r:.5f}")
    doc.add_run("）；")
    doc.add_inline_math(r"U_{2} = 800\,\mathrm{V}")
    doc.add_run(" 时 ")
    doc.add_inline_math(f"\\varepsilon_{{y}} = {reg_y_800.slope:.3f}" + r"\,\mathrm{mm/V}")
    doc.add_run("（相关系数 ")
    doc.add_inline_math(f"r = {reg_y_800.r:.5f}")
    doc.add_run("）。可见加速电压 ")
    doc.add_inline_math(r"U_{2}")
    doc.add_run(" 越小，Y 轴的电偏转灵敏度 ")
    doc.add_inline_math(r"\varepsilon_{y}")
    doc.add_run(" 越大，电偏转灵敏度与 ")
    doc.add_inline_math(r"U_{2}")
    doc.add_run(" 成反比。")

    # 磁偏转
    doc.add_paragraph("依据表3，同上作 ")
    doc.add_inline_math(r"D - I_{m}")
    doc.add_run(" 曲线并作最小二乘线性拟合，直线斜率的绝对值即为磁偏转灵敏度：")
    doc.add_math(r"\delta_{m} = \left| \frac{\Delta D}{\Delta I_{m}} \right|")
    doc.add_image(fig3_path, width_cm=12)
    doc.add_paragraph("图3 ")
    doc.add_inline_math(r"D - I_{m}")
    doc.add_run(" 关系曲线")
    doc.add_paragraph("拟合得 ")
    doc.add_inline_math(r"U_{2} = 1000\,\mathrm{V}")
    doc.add_run(" 时 ")
    doc.add_inline_math(f"\\delta_{{m}} = {dm_1000:.3f}" + r"\,\mathrm{mm/mA}")
    doc.add_run("（相关系数 ")
    doc.add_inline_math(f"r = {reg_m_1000.r:.5f}")
    doc.add_run("）；")
    doc.add_inline_math(r"U_{2} = 800\,\mathrm{V}")
    doc.add_run(" 时 ")
    doc.add_inline_math(f"\\delta_{{m}} = {dm_800:.3f}" + r"\,\mathrm{mm/mA}")
    doc.add_run("（相关系数 ")
    doc.add_inline_math(f"r = {reg_m_800.r:.5f}")
    doc.add_run("）。可见加速电压 ")
    doc.add_inline_math(r"U_{2}")
    doc.add_run(" 越小，磁偏转灵敏度 ")
    doc.add_inline_math(r"\delta_{m}")
    doc.add_run(" 越大，磁偏转灵敏度与 ")
    doc.add_inline_math(r"\sqrt{U_{2}}")
    doc.add_run(" 成反比。")

    doc.add_heading("三、课后思考题", level=1)
    doc.add_paragraph("1. 由电偏转灵敏度的计算结果，能得出 ")
    doc.add_inline_math(r"\varepsilon")
    doc.add_run(" 与 ")
    doc.add_inline_math(r"U_{2}")
    doc.add_run(" 有什么关系？")
    doc.add_paragraph("答：由式")
    doc.add_math(r"\varepsilon = k_{e}\frac{1}{U_{2}}")
    doc.add_paragraph("知，")
    doc.add_inline_math(r"U_{2}")
    doc.add_run(" 越大，")
    doc.add_inline_math(r"\varepsilon")
    doc.add_run(" 越小，即 ")
    doc.add_inline_math(r"\varepsilon")
    doc.add_run(" 与 ")
    doc.add_inline_math(r"U_{2}")
    doc.add_run(" 成反比关系。")

    doc.add_paragraph("2. 偏转量的大小与光点的亮度是否有关？为什么？")
    doc.add_paragraph("答：有关，偏转量的大小会影响聚焦，从而影响光点亮度。")

    doc.add_paragraph("3. 地球表面的磁场对电子显像管中电子的运动有多大影响？能否忽略？")
    doc.add_paragraph("答：地磁场强度为 ")
    doc.add_inline_math(r"(2.5 \sim 6.5) \times 10^{-5}\,\mathrm{T}")
    doc.add_run("，与电子显像管中磁场相比，磁场强度很弱，因此地磁场对电子显像管中"
                "电子的运动影响很小，从而可以忽略。")

    doc.save()
    doc.close()
    for p in (fig1_path, fig2_path, fig3_path):
        if os.path.exists(p):
            os.remove(p)
    print(f"报告已生成: {output_path}")


def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "电子偏转特性的测量实验报告.docx")
    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return
    _generate_docx(data, DOCX_FILE)


if __name__ == "__main__":
    main()
