# -*- coding: utf-8 -*-
"""静电场的模拟 — 数据处理脚本（从公众号"对策府库"物理实验计算器提取）。

参考源：
  - 数据录入结构：XDU物理实验小助手 实验定义 JSON（变量 U_r / r / U_r_U_a / ln_r）
  - 文件范式：模仿 物理实验/实验脚本/<实验名>/generate.py
实验原理：
  同轴电缆静电场 U(r) = U_a * ln(b/r) / ln(b/a)，即 ln(r) 与 U 呈线性关系。
  测量各等势线半径 r，作 ln(r) ~ U/U_a 图，线性拟合验证分布规律。
"""

import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import *
from common.docx_report import DocxReportWriter
from common.variants import compose
from common.plot_utils import plot_fit
from common.data_io import load_data

# ── 实验参数 ──
# 等势线电压（V），常量数组，对应 7V~1V
U_R_LIST = [7, 6, 5, 4, 3, 2, 1]
# 示例数据：对应等势线半径（cm）
R_DEFAULT = [1.65, 2.11, 2.65, 3.28, 3.95, 4.71, 5.52]


# （方式三：_create_template 已移除，数据真相为 data.json）


def _compute(data: dict) -> dict:
    """读取 data.json 数据并计算全部结果。"""
    # 读 U_r 和 r（长度 7 的数组，过滤未填，保持旧 read_column 行为）
    u_r = [float(v) for v in data["u_r"] if v is not None]
    r = [float(v) for v in data["r"] if v is not None]

    n = len(r)
    u_a = 10.0  # 外加电压 U_a = 10 V（与计算器一致：U_r_U_a = U_r / 10）
    u_r_ua = [u / u_a for u in u_r]  # U_r / U_a
    ln_r = [math.log(ri) for ri in r]  # ln(r)

    # 线性拟合：ln(r) = intercept + slope * (U_r / U_a)
    fit = linear_regression(u_r_ua, ln_r)

    return {
        "u_r": u_r, "r": r, "u_a": u_a,
        "u_r_ua": u_r_ua, "ln_r": ln_r,
        "slope": fit.slope, "slope_u": fit.slope_uncertainty,
        "intercept": fit.intercept, "intercept_u": fit.intercept_uncertainty,
        "r_squared": fit.r_squared, "r_corr": fit.r,
        "n": n,
    }


def _print_results(r: dict):
    """控制台打印计算结果。"""
    print("=" * 56)
    print("静电场的模拟 — 计算结果")
    print("=" * 56)
    print(f"U_a = {r['u_a']} V")
    print(f"{'U_r/V':>8} {'r/cm':>8} {'ln(r)':>10} {'U_r/U_a':>10}")
    for i in range(r["n"]):
        print(f"{r['u_r'][i]:8.1f} {r['r'][i]:8.2f} {r['ln_r'][i]:10.4f} {r['u_r_ua'][i]:10.3f}")
    print()
    print("线性拟合: ln(r) = a + b * (U_r/U_a)")
    print(f"  斜率 b = {r['slope']:.4f} ± {r['slope_u']:.4f}")
    print(f"  截距 a = {r['intercept']:.4f} ± {r['intercept_u']:.4f}")
    print(f"  相关系数 r = {r['r_corr']:.6f}")
    print(f"  决定系数 R² = {r['r_squared']:.6f}")
    print("=" * 56)


def _generate_docx(data: dict, output_path: str):
    """从 data.json 读取数据，计算并生成 Word 实验报告。"""
    # 校验必填数据（required 字段为 null 或 array 含 null → 缺失）
    missing = []
    for k in ("u_r", "r"):
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
    _print_results(r)

    doc = DocxReportWriter(output_path)

    doc.add_title("静电场的模拟")
    doc.add_student_info()

    # ── 变体组合：实验原理 / 实验方法（存在 variants.json 且应用传入选择时生效）──
    variants = compose(SCRIPT_DIR, r)
    if "实验原理" in variants:
        doc.add_heading("实验原理", level=1)
        doc.add_paragraph_rich(variants["实验原理"])
    if "实验方法" in variants:
        doc.add_heading("实验方法", level=1)
        doc.add_paragraph_rich(variants["实验方法"])

    doc.add_heading("一、原始数据提交（拍照上传）", level=1)
    doc.add_paragraph("请在下方粘贴原始数据记录照片。")

    doc.add_heading("二、数据处理", level=1)

    doc.add_heading("1. 等势线半径测量", level=2)
    doc.add_paragraph("")
    doc.add_run("测量同轴电缆模型各等势线的半径 ")
    doc.add_inline_math("r")
    doc.add_run("，对应电压 ")
    doc.add_inline_math("U_r")
    doc.add_run(" 从 ")
    doc.add_inline_math(f"{r['u_a']:.0f} V")
    doc.add_run(" 依次降至 ")
    doc.add_inline_math(f"{min(r['u_r']):.0f} V")
    doc.add_run("。计算各点的 ")
    doc.add_inline_math(r"\ln(r)")
    doc.add_run(" 和归一化电压 ")
    doc.add_inline_math(r"U_r/U_a")
    doc.add_run("：")

    rows = []
    for i in range(r["n"]):
        rows.append([
            f"{r['u_r'][i]:.1f}",
            f"{r['r'][i]:.2f}",
            f"{r['ln_r'][i]:.4f}",
            f"{r['u_r_ua'][i]:.3f}",
        ])
    doc.add_table(["$U_r$ / V", "$r$ / cm", "$\\ln(r)$", "$U_r / U_a$"], rows,
                  col_widths=[2.5, 2.5, 2.5, 2.5])

    doc.add_heading("2. 线性拟合验证", level=2)
    doc.add_paragraph("")
    doc.add_run("以归一化电压 ")
    doc.add_inline_math(r"U_r/U_a")
    doc.add_run(" 为横坐标，")
    doc.add_inline_math(r"\ln(r)")
    doc.add_run(" 为纵坐标，作散点图并进行最小二乘线性拟合。")
    doc.add_paragraph("拟合方程：")
    doc.add_math(
        r"\ln(r) = a + b \cdot \frac{U_r}{U_a}"
    )
    doc.add_paragraph("")
    doc.add_run("拟合结果：")
    doc.add_math(
        r"b = " + format_number(r["slope"], r["slope_u"])
        + r",\quad a = " + format_number(r["intercept"], r["intercept_u"])
    )
    doc.add_paragraph("")
    doc.add_run("相关系数 ")
    doc.add_inline_math(f"r = {format_number(r['r_corr'])}")
    doc.add_run("，决定系数 ")
    doc.add_inline_math(f"R^2 = {format_number(r['r_squared'])}")
    doc.add_run("。")

    # 绘制线性拟合图
    fit_img_path = os.path.join(SCRIPT_DIR, "fit_plot.png")
    plot_fit(
        x=r["u_r_ua"], y=r["ln_r"],
        slope=r["slope"], intercept=r["intercept"],
        xlabel=r"$U_r / U_a$", ylabel=r"$\ln(r)$",
        title="静电场线性拟合验证",
        save_path=fit_img_path,
        r_squared=r["r_squared"],
    )
    doc.add_paragraph("")
    doc.add_run("线性拟合图如下：")
    doc.add_image(fit_img_path, width_cm=12)

    doc.add_heading("3. 静电场分布规律验证", level=2)
    doc.add_paragraph("")
    doc.add_run("对于无限长同轴电缆，静电场的理论分布为：")
    doc.add_math(
        r"U(r) = U_a \cdot \frac{\ln(b/r)}{\ln(b/a)}"
    )
    doc.add_paragraph("")
    doc.add_run("变形可得 ")
    doc.add_inline_math(r"\ln(r)")
    doc.add_run(" 与 ")
    doc.add_inline_math("U")
    doc.add_run(" 呈线性关系：")
    doc.add_math(
        r"\ln(r) = \ln(b) - \frac{\ln(b/a)}{U_a} \cdot U"
    )
    doc.add_paragraph("")
    doc.add_run("实验拟合的相关系数 ")
    doc.add_inline_math(f"r = {format_number(r['r_corr'])}")
    doc.add_run("，非常接近 1，说明 ")
    doc.add_inline_math(r"\ln(r)")
    doc.add_run(" 与 ")
    doc.add_inline_math(r"U_r/U_a")
    doc.add_run(" 之间存在良好的线性关系，")
    doc.add_run("验证了同轴电缆静电场的理论分布规律，即模拟法测绘静电场是可靠的。")

    doc.add_heading("三、实验结果分析", level=1)
    doc.add_paragraph("")
    doc.add_run("本次实验通过电流场模拟静电场，测量了同轴电缆模型各等势线的半径，")
    doc.add_run("并通过线性拟合验证了 ")
    doc.add_inline_math(r"\ln(r)")
    doc.add_run(" 与 ")
    doc.add_inline_math("U")
    doc.add_run(" 的线性关系。拟合相关系数 ")
    doc.add_inline_math(f"r = {format_number(r['r_corr'])}")
    doc.add_run("，表明实验数据与理论规律吻合良好。")

    doc.add_paragraph("")
    doc.add_run("误差来源分析：")
    doc.add_run("（1）导电介质的电导率不均匀，导致等势线发生畸变；")
    doc.add_run("（2）探针接触电阻和测量时的压力变化引入读数误差；")
    doc.add_run("（3）模型边界的有限尺寸效应，边缘处电场分布偏离无限长同轴电缆理论；")
    doc.add_run("（4）探针定位的视觉误差和坐标纸读数误差。")

    # ── 变体组合：误差分析 / 结论（存在 variants.json 且应用传入选择时生效）──
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])
    if "结论" in variants:
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    doc.add_heading("四、思考题", level=1)

    doc.add_heading("1. 为什么可以用稳恒电流场模拟静电场？", level=2)
    doc.add_paragraph(
        "答：稳恒电流场与静电场在一定条件下具有相似的空间分布。"
        "两者都满足拉普拉斯方程（∇²U = 0），且在相同的边界条件下具有相同的解。"
        "因此可以用容易测量的稳恒电流场来模拟难以直接测量的静电场。"
    )

    doc.add_heading("2. 实验中为什么要保持电极与导电介质良好接触？", level=2)
    doc.add_paragraph(
        "答：如果电极与导电介质接触不良，会产生接触电阻，导致电极附近的电流分布发生畸变，"
        "等势线不再是理想的同心圆，从而引入系统误差。良好的接触保证电极表面是等势面，"
        "使电流场分布与静电场的边界条件一致。"
    )

    doc.add_heading("3. 如果将同轴电缆的内外电极电压反接，等势线分布会如何变化？", level=2)
    doc.add_paragraph(
        "答：电压反接后，电场方向反转，但等势线的几何形状（同心圆）不变，"
        "只是各等势线对应的电压值符号相反。ln(r) 与 U 的线性关系仍然成立，"
        "只是拟合斜率的符号变为正（原斜率为负，因为 U 越大 r 越小）。"
    )

    doc.save()
    doc.close()


def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "静电场的模拟.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    _generate_docx(data, DOCX_FILE)
    print(f"报告已生成: {DOCX_FILE}")


if __name__ == "__main__":
    main()
