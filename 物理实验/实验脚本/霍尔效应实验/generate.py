# -*- coding: utf-8 -*-
"""霍尔效应测量磁场 — 数据处理脚本。"""
import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import *
from common.docx_report import DocxReportWriter
from common.data_io import load_data
from common.variants import compose

# 给定量（教材/仪器标称，预填入模板）
I_WORK_MA = 10.0    # 表1 固定工作电流 I/mA
IM_FIXED_MA = 500.0  # 表2 固定励磁电流 Im/mA
IM_LIST_MA = [200, 300, 400, 500, 600, 700, 800, 900, 1000]  # 表1 励磁电流 Im/mA
I_LIST_MA = [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]   # 表2 工作电流 I/mA

# ---- 数据.xlsx 模板布局（仅供 _create_template 生成模板使用，读取已改为 data.json）----
ROW_KH = 3        # B3: 霍尔片灵敏度 K_H/(V/(A·T))，用户按元件标称值填写
ROW_I_WORK = 4    # B4: 表1 工作电流 I/mA（预填 10.0）
ROW_IM_FIXED = 5  # B5: 表2 励磁电流 Im/mA（预填 500）

T1_TITLE, T1_IM, T1_U1, T1_U2, T1_UH, T1_B = 7, 8, 9, 10, 11, 12
T2_TITLE, T2_I, T2_U1, T2_U2, T2_UH, T2_B = 14, 15, 16, 17, 18, 19
DATA_START_COL, DATA_END_COL = "B", "J"  # 每表 9 个数据列
N_POINTS = 9


# （方式三：_create_template 已移除，数据真相为 data.json）


def _plot_curves(im_ma, b1, i_ma, b2, slope, intercept, fig1_path, fig2_path):
    """matplotlib 绘制 B–Im（散点+拟合直线）与 B–I（散点连线）曲线图"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
    plt.rcParams["axes.unicode_minus"] = False
    POINT_COLOR, FIT_COLOR = "#2c5f9e", "#e07b39"  # 蓝/橙，CVD 安全对

    def _style(ax):
        ax.grid(True, linestyle="--", linewidth=0.5, color="#cccccc")
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_color("#999999")

    # 图1：B–Im 散点 + 拟合直线（两系列，配图例）
    fig, ax = plt.subplots(figsize=(5.5, 3.8), dpi=200)
    ax.plot(im_ma, b1, "o", color=POINT_COLOR, markersize=6, label="测量点")
    x_fit = [min(im_ma), max(im_ma)]
    y_fit = [slope * x / 1000.0 + intercept for x in x_fit]  # 斜率按 Im/A 拟合
    ax.plot(x_fit, y_fit, "-", color=FIT_COLOR, linewidth=1.5, label="拟合直线")
    ax.set_xlabel("励磁电流 $I_m$/mA")
    ax.set_ylabel("B/T")
    _style(ax)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(fig1_path, facecolor="white")
    plt.close(fig)

    # 图2：B–I 散点连线（单系列，标题即说明，无图例）
    fig, ax = plt.subplots(figsize=(5.5, 3.8), dpi=200)
    ax.plot(i_ma, b2, "o-", color=POINT_COLOR, markersize=6, linewidth=1.5)
    ax.set_xlabel("工作电流 I/mA")
    ax.set_ylabel("B/T")
    ax.set_ylim(0, max(b2) * 1.4)  # 纵轴从 0 起，直观体现 B 基本恒定
    _style(ax)
    fig.tight_layout()
    fig.savefig(fig2_path, facecolor="white")
    plt.close(fig)


def _generate_docx(data: dict, output_path: str):
    """读取 data.json → 计算 → 输出 docx"""
    # ---- 1. 读取 + 空值校验（required 字段为 null 或 array 含 null → 缺失）----
    labels = {
        "kh": "霍尔片灵敏度 K_H",
        "i_work": "表1 工作电流 I",
        "im_fixed": "表2 励磁电流 Im",
        "t1_im": "表1 励磁电流 Im",
        "t1_u1": "表1 (+B,+I) U1",
        "t1_u2": "表1 (+B,−I) U2",
        "t2_i": "表2 工作电流 I",
        "t2_u1": "表2 (+B,+I) U1",
        "t2_u2": "表2 (+B,−I) U2",
    }
    missing = []
    for k, name in labels.items():
        v = data.get(k)
        if v is None or (isinstance(v, list) and (not v or any(x is None for x in v))):
            missing.append(f"{k}（{name}）")
    if missing:
        print("以下必填数据未填写，请补齐后重新运行：")
        for m in missing:
            print(f"  - {m}")
        return

    kh = float(data["kh"])
    i_work = float(data["i_work"])
    im_fixed = float(data["im_fixed"])
    t1_im = [float(v) for v in data["t1_im"]]
    t1_u1 = [float(v) for v in data["t1_u1"]]
    t1_u2 = [float(v) for v in data["t1_u2"]]
    t2_i = [float(v) for v in data["t2_i"]]
    t2_u1 = [float(v) for v in data["t2_u1"]]
    t2_u2 = [float(v) for v in data["t2_u2"]]

    # ---- 2. 计算：电流换向法 U_H = (U1+|U2|)/2；B = U_H/(K_H·I) ----
    # 单位：U/mV、K_H/(V/(A·T))≡(mV/(mA·T))、I/mA → B/T
    t1_uh = [(u1 + abs(u2)) / 2 for u1, u2 in zip(t1_u1, t1_u2)]
    t1_b = [uh / (kh * i_work) for uh in t1_uh]
    t2_uh = [(u1 + abs(u2)) / 2 for u1, u2 in zip(t2_u1, t2_u2)]
    t2_b = [uh / (kh * i) for uh, i in zip(t2_uh, t2_i)]

    # ---- 3. B–Im 线性回归（Im 换算为 A，斜率单位 T/A）----
    im_a = [v / 1000.0 for v in t1_im]
    reg = linear_regression(im_a, t1_b)
    b2_mean = mean(t2_b)

    # ---- 4. 控制台摘要（便于誊抄到纸质数据表）----
    print("表1 磁感应强度的测量（I = %.1f mA, K_H = %g V/(A·T)）" % (i_work, kh))
    print("  Im/mA: " + "  ".join(f"{v:g}" for v in t1_im))
    print("  U_H/mV:" + "  ".join(f"{v:.3f}" for v in t1_uh))
    print("  B/T:   " + "  ".join(f"{v:.3f}" for v in t1_b))
    print("表2 磁感应强度与工作电流的关系（Im = %g mA）" % im_fixed)
    print("  I/mA:  " + "  ".join(f"{v:g}" for v in t2_i))
    print("  U_H/mV:" + "  ".join(f"{v:.3f}" for v in t2_uh))
    print("  B/T:   " + "  ".join(f"{v:.3f}" for v in t2_b))
    print(f"B–Im 回归斜率 k = {reg.slope:.4f} T/A，相关系数 r = {reg.r:.5f}")
    print(f"表2 B 平均值 = {b2_mean:.3f} T")

    # ---- 5. 绘图 ----
    fig1_path = os.path.join(SCRIPT_DIR, "_fig_B_Im.png")
    fig2_path = os.path.join(SCRIPT_DIR, "_fig_B_I.png")
    try:
        _plot_curves(t1_im, t1_b, t2_i, t2_b, reg.slope, reg.intercept,
                     fig1_path, fig2_path)
    except ImportError:
        print("未安装 matplotlib，无法绘制曲线图。请先执行: pip install matplotlib")
        return

    # ---- 6. docx 输出 ----
    doc = DocxReportWriter(output_path)
    doc.add_title("霍尔效应实验")
    doc.add_student_info()

    # 变体组合：实验原理 / 实验方法（有 variants.json 且应用传入选择时生效）
    r = {
        "kh": kh, "i_work": i_work, "im_fixed": im_fixed,
        "k": reg.slope, "r_coef": reg.r, "b2_mean": b2_mean,
    }
    variants = compose(SCRIPT_DIR, r)
    if "实验原理" in variants:
        doc.add_heading("实验原理", level=1)
        doc.add_paragraph_rich(variants["实验原理"])
    if "实验方法" in variants:
        doc.add_heading("实验方法", level=1)
        doc.add_paragraph_rich(variants["实验方法"])

    doc.add_heading("一、原始数据记录", level=1)
    doc.add_paragraph("请在下方粘贴原始数据记录照片。")

    doc.add_heading("二、数据处理", level=1)
    doc.add_paragraph("采用电流换向法消除不等位电压的影响，霍尔电压为")
    doc.add_math(r"U_{H} = \frac{1}{2}(U_{1} + |U_{2}|)")
    doc.add_paragraph("磁感应强度为")
    doc.add_math(r"B = \frac{U_{H}}{K_{H} I}")
    doc.add_paragraph("以表1第1列数据为例，代入数据：")
    doc.add_math(r"U_{H} = \frac{1}{2} \times (" + f"{t1_u1[0]:.3f} + {abs(t1_u2[0]):.3f}"
                 + r") = " + f"{t1_uh[0]:.3f}" + r"\,\mathrm{mV}")
    doc.add_math(r"B = \frac{" + f"{t1_uh[0]:.3f}" + r"}{" + f"{kh:g} \\times {i_work:g}"
                 + r"} \approx " + f"{t1_b[0]:.3f}" + r"\,\mathrm{T}")
    doc.add_paragraph("以表2第1列数据为例，代入数据：")
    doc.add_math(r"B = \frac{" + f"{t2_uh[0]:.3f}" + r"}{" + f"{kh:g} \\times {t2_i[0]:g}"
                 + r"} \approx " + f"{t2_b[0]:.3f}" + r"\,\mathrm{T}")
    doc.add_paragraph("其余各列同法计算，B–Im 与 B–I 关系曲线如下图所示。")

    doc.add_image(fig1_path, width_cm=12)
    doc.add_paragraph("图1 B–Im 关系曲线")
    doc.add_paragraph("对 B–Im 数据用最小二乘法作线性回归，得直线斜率")
    doc.add_math(r"k = " + f"{reg.slope:.4f}" + r"\,\mathrm{T/A}")
    doc.add_paragraph("相关系数 ")
    doc.add_inline_math(f"r = {reg.r:.5f}")
    doc.add_run("，B 与励磁电流 Im 呈良好的线性关系。")

    doc.add_image(fig2_path, width_cm=12)
    doc.add_paragraph("图2 B–I 关系曲线")
    doc.add_paragraph("由图2 可见，改变工作电流 I 时磁感应强度 B 基本保持恒定（平均值 ")
    doc.add_inline_math(f"\\bar{{B}} = {b2_mean:.3f}" + r"\,\mathrm{T}")
    doc.add_run("），验证了磁感应强度与工作电流无关。")

    # 变体组合：误差分析 / 结论
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])
    if "结论" in variants:
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    doc.add_heading("三、课后思考题", level=1)
    doc.add_paragraph("1. 若磁感应强度跟霍尔元件不完全正交，则按 B = U_H/(K_H·I) 计算出的"
                      "磁感应强度比实际值大还是小？要准确测量磁场应如何操作？")
    doc.add_paragraph("答：偏小。当霍尔片平面与磁场不完全正交时，只有垂直于霍尔片平面的"
                      "磁场分量对霍尔电压有贡献，测得的霍尔电压偏小，按公式计算出的磁感应"
                      "强度比实际值小。要准确测量磁场，应缓慢转动霍尔元件的方位，使霍尔"
                      "电压达到最大，此时霍尔片平面与磁场方向严格正交，测得的才是真实磁场。")
    doc.add_paragraph("2. 如何用霍尔效应法判断 N 型半导体和 P 型半导体？")
    doc.add_paragraph("答：在相同的工作电流方向和磁场方向下，N 型半导体（载流子为电子）与"
                      "P 型半导体（载流子为空穴）产生的霍尔电压极性相反。将待测半导体通入"
                      "已知方向的工作电流并置于已知方向的磁场中，测出霍尔电压的正负，即可"
                      "判断载流子的符号：与空穴导电情形一致的为 P 型半导体，反之为 N 型半导体。")

    doc.save()
    doc.close()
    for p in (fig1_path, fig2_path):
        if os.path.exists(p):
            os.remove(p)
    print(f"报告已生成: {output_path}")


def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "霍尔效应实验报告.docx")
    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return
    _generate_docx(data, DOCX_FILE)


if __name__ == "__main__":
    main()
