"""重力加速度的测量（复摆）— 数据处理脚本。"""

import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import *
from common.docx_report import DocxReportWriter
from common.variants import compose
from common.data_io import load_data

# ── 物理常数与仪器参数（按教材） ──
G0_XIAN = 9.797               # 西安标准重力加速度 m/s²
DELTA_TIMER = 0.01            # 光电计时器 Δ_仪 (s)
N_HOLES = 9                   # 测量孔数
N_TRIALS = 8                  # 每孔 10 周期重复测量次数

# 支点位置预填值（范例，用户可按需修改，单位 cm）
DEFAULT_PIVOT_POSITIONS = [17.5, 15.5, 13.5, 11.5, 9.5, 7.5, 5.5, 3.5, 1.5]


def _plot_th_curve(h_values, T_avg, T0, h1, h2, output_path):
    """绘制 T-h 关系曲线图并保存为 PNG。

    Parameters
    ----------
    h_values : list[float]    — 悬距 h (cm)，按 h 从小到大排列
    T_avg : list[float]       — 对应单周期平均值 T (s)
    T0 : float                — 等值周期 (s)
    h1, h2 : float            — 对称点悬距 (cm)，h1 < h2
    output_path : str         — 输出图片路径
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    # 中文字体
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    # 按 h 从小到大排序（原始数据可能乱序）
    sorted_pairs = sorted(zip(h_values, T_avg))
    h_sorted = np.array([p[0] for p in sorted_pairs])
    T_sorted = np.array([p[1] for p in sorted_pairs])

    fig, ax = plt.subplots(figsize=(8, 5))

    # 平滑插值曲线
    try:
        from scipy.interpolate import CubicSpline
        cs = CubicSpline(h_sorted, T_sorted)
        h_dense = np.linspace(h_sorted[0], h_sorted[-1], 300)
        T_dense = cs(h_dense)
    except ImportError:
        # 后备：4 次多项式拟合
        z = np.polyfit(h_sorted, T_sorted, min(4, len(h_sorted) - 1))
        p = np.poly1d(z)
        h_dense = np.linspace(h_sorted[0], h_sorted[-1], 300)
        T_dense = p(h_dense)
    ax.plot(h_dense, T_dense, "-", color="steelblue", linewidth=1.5)

    # 原始数据点（红色圆点）
    ax.scatter(h_sorted, T_sorted, color="red", s=45, zorder=5)

    # 黑色虚线等 T 线（从 h₁ 左侧延伸到 h₂ 右侧）
    h_margin = (h_sorted[-1] - h_sorted[0]) * 0.05
    ax.hlines(y=T0, xmin=h1 - h_margin, xmax=h2 + h_margin,
              colors="black", linestyles="dashed", linewidth=1.2, alpha=0.8)

    # 标注对称点
    ax.scatter([h1, h2], [T0, T0], color="black", s=55, zorder=6)
    ax.annotate(f"({h1}, {T0})", (h1, T0),
                textcoords="offset points", xytext=(-10, 12), fontsize=9,
                arrowprops=dict(arrowstyle="->", color="gray", lw=0.8))
    ax.annotate(f"({h2}, {T0})", (h2, T0),
                textcoords="offset points", xytext=(8, 12), fontsize=9,
                arrowprops=dict(arrowstyle="->", color="gray", lw=0.8))

    # 坐标轴标签
    ax.set_xlabel("h / cm", fontsize=12)
    ax.set_ylabel("T / s", fontsize=12)
    ax.set_title("T-h 关系曲线", fontsize=13)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


# （方式三：_create_template 已移除，数据真相为 data.json）


def _compute(data: dict) -> dict:
    """由原始测量数据计算单周期平均值、等值单摆长、重力加速度与相对误差，返回结果字典 r。"""
    # 整理数据
    g0 = float(data["g0"])
    delta_instr = float(data["delta_instr"])
    pivot_positions = [float(v) for v in data["pivot"]]
    trials_10T = [[float(v) for v in hole] for hole in data["trials"]]
    h_values = [float(v) for v in data["h"]]
    T0 = float(data["T0"])
    h1 = float(data["h1"])
    h2 = float(data["h2"])
    cm_position = data.get("cm_position")

    # 计算单周期平均值
    T_avg = []
    for hole_data in trials_10T:
        avg_10T = mean(hole_data)
        T_avg.append(avg_10T / 10.0)

    # 卡特公式计算 g
    # 等值单摆长 (cm → m)
    l_cm = h1 + h2
    l_m = l_cm / 100.0

    # 退化形式：T₁=T₂=T₀
    g_calc = 4 * math.pi ** 2 * l_m / (T0 ** 2)

    # 相对误差
    delta_E = abs(g0 - g_calc) / g0 * 100

    return {
        "g0": g0, "delta_instr": delta_instr,
        "pivot_positions": pivot_positions, "trials_10T": trials_10T,
        "h_values": h_values, "T0": T0, "h1": h1, "h2": h2,
        "cm_position": cm_position,
        "T_avg": T_avg, "l_cm": l_cm, "l_m": l_m,
        "g_calc": g_calc, "delta_E": delta_E,
    }


def _generate_docx(data: dict, output_path: str):
    """从 data.json 读取数据，计算并生成 Word 实验报告。"""

    # ═══════════════════════════════════════════════
    # 1. 读取数据（含空值校验）
    # ═══════════════════════════════════════════════
    # 校验必填数据（required 字段为 null 或 array/matrix 含 null → 缺失）
    def _flat(v):
        if isinstance(v, list) and v and isinstance(v[0], list):
            return [x for row in v for x in row]
        return v if isinstance(v, list) else [v]

    missing = []
    for k in ("g0", "delta_instr", "pivot", "trials", "h", "T0", "h1", "h2"):
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

    # ═══════════════════════════════════════════════
    # 2~4. 数据处理：单周期平均、卡特公式计算 g（见 _compute）
    # ═══════════════════════════════════════════════
    r = _compute(data)
    g0 = r["g0"]
    delta_instr = r["delta_instr"]
    pivot_positions = r["pivot_positions"]
    trials_10T = r["trials_10T"]
    h_values = r["h_values"]
    T0 = r["T0"]
    h1 = r["h1"]
    h2 = r["h2"]
    cm_position = r["cm_position"]
    T_avg = r["T_avg"]
    l_cm = r["l_cm"]
    g_calc = r["g_calc"]
    delta_E = r["delta_E"]

    # ═══════════════════════════════════════════════
    # 5. 控制台输出
    # ═══════════════════════════════════════════════
    print(f"g = {g_calc:.4f} m/s^2,  |g0 - g| = {abs(g0 - g_calc):.4f} m/s^2,  delta_E = {delta_E:.3f}%")
    print("9-hole T_avg (s): " + "  ".join(f"{t:.3f}" for t in T_avg))
    print(f"l = {l_cm:.2f} cm")
    print()

    # ═══════════════════════════════════════════════
    # 5.5 绘制 T-h 关系曲线图
    # ═══════════════════════════════════════════════
    th_plot_path = os.path.join(SCRIPT_DIR, "T-h曲线.png")
    _plot_th_curve(h_values, T_avg, T0, h1, h2, th_plot_path)
    print(f"T-h 曲线已保存: {th_plot_path}")

    # ═══════════════════════════════════════════════
    # 6. 生成 docx 报告
    # ═══════════════════════════════════════════════
    doc = DocxReportWriter(output_path)

    # ── 零、实验标题 ──
    doc.add_title("重力加速度的测量（复摆）")
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

    # （一）实验数据记录
    doc.add_heading("（一）实验数据记录", level=2)

    # 构建数据表
    col_labels = [f"第{i+1}孔" for i in range(N_HOLES)]
    headers = [""] + col_labels

    rows = []
    # 支点位置行
    rows.append(["支点位置/cm"] + [f"{v:.1f}" for v in pivot_positions])
    # 8行10周期
    for trial in range(N_TRIALS):
        row_label = "10周期/s"
        row_data = [f"{trials_10T[hole][trial]:.2f}" for hole in range(N_HOLES)]
        rows.append([row_label] + row_data)
    # 单周期平均
    rows.append(["单周期平均 T/s"] + [f"{t:.3f}" for t in T_avg])
    # h/cm
    rows.append(["h/cm"] + [f"{h:.2f}" for h in h_values])

    # 列宽：标签列3.0cm + 9×数据列1.1cm ≈ 12.9cm
    col_widths = [3.0] + [1.1] * N_HOLES
    doc.add_table(headers, rows, col_widths=col_widths)

    # 质心位置注释
    cm_text = f"质心位置：{cm_position:.1f} cm" if cm_position is not None else "质心位置：______ cm"
    doc.add_paragraph(cm_text)

    # （二）T-h 关系图与对称点
    doc.add_heading("（二）T-h 关系图与对称点", level=2)
    doc.add_paragraph("根据测量数据，作摆动周期 T 与摆轴离中心距离 h 的关系图。")

    # 插入绘制的 T-h 曲线图
    doc.add_image(th_plot_path, width_cm=12)

    doc.add_paragraph("")
    doc.add_run("在 T-h 曲线上作水平线（图中黑色虚线），读取等周期对称点坐标：")
    doc.add_inline_math(f"T_0 = {T0:.3f}\\ \\mathrm{{s}}")
    doc.add_run("，")
    doc.add_inline_math(f"h_1 = {h1:.2f}\\ \\mathrm{{cm}}")
    doc.add_run("，")
    doc.add_inline_math(f"h_2 = {h2:.2f}\\ \\mathrm{{cm}}")
    doc.add_run("。")

    # （三）重力加速度计算
    doc.add_heading("（三）重力加速度计算", level=2)

    doc.add_paragraph("等值单摆长：")
    doc.add_math(r"l = h_1 + h_2 = " + f"{h1:.2f} + {h2:.2f} = {l_cm:.2f}" + r"\ \mathrm{cm}")

    doc.add_paragraph("将对称点代入卡特公式：")
    doc.add_math(
        r"\frac{4\pi^{2}}{g} = "
        r"\frac{T_{1}^{2} + T_{2}^{2}}{2(h_{1} + h_{2})} + "
        r"\frac{T_{1}^{2} - T_{2}^{2}}{2(h_{1} - h_{2})}"
    )

    doc.add_paragraph("由于所取为等周期点（同一水平线与 T-h 曲线的两个交点），有")
    doc.add_inline_math(f"T_1 = T_2 = T_0 = {T0:.3f}\\ \\mathrm{{s}}")
    doc.add_run("，上式第二项为零，退化为单摆形式，代入数值得：")

    doc.add_math(
        r"g \approx " + format_number(g_calc) + r"\ \mathrm{m/s^2}"
    )

    doc.add_paragraph("西安地区重力加速度精确值为 ")
    doc.add_inline_math(f"g_0 = {g0}")
    doc.add_run(r" m/s²，相对误差：")

    doc.add_math(
        r"\Delta E = \frac{|g_0 - g|}{g_0} \times 100\% = "
        r"\frac{|" + f"{g0:.3f} - {g_calc:.3f}" + r"|}{" + f"{g0:.3f}" + r"} \times 100\% = "
        + f"{delta_E:.3f}" + r"\%"
    )

    # ── 三、实验结果分析 ──
    doc.add_heading("三、实验结果分析", level=1)
    doc.add_paragraph(
        f"通过复摆实验测量重力加速度 g，实验结果得到 g = {g_calc:.3f} m/s²，"
        f"与西安标准值 g₀ = {g0} m/s² 相比，相对误差为 {delta_E:.2f}%。"
    )
    doc.add_paragraph(
        "误差来源主要包括：（1）从 T-h 曲线上读取对称点坐标时引入的读数误差，"
        "这是本实验最主要的误差来源；（2）摆角过大导致小角度近似不严格成立，"
        "周期公式为 sinθ ≈ θ 近似下的结果，大摆角会引入系统误差；"
        "（3）悬挂处孔与刀口接触不密切，摩擦影响周期测量；"
        "（4）光电计时器的计时精度及人工启动/停止的响应时间差异。"
    )

    # ── 变体组合：误差分析 / 结论（存在 variants.json 且应用传入选择时生效）──
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])
    if "结论" in variants:
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    # ── 四、思考题 ──
    doc.add_heading("四、思考题", level=1)

    # 第1题
    doc.add_heading("1. 试证明二次法测 g 的公式(3-3-11)等效于卡特公式(3-3-15)。", level=2)
    doc.add_paragraph("答：二次法公式为")
    doc.add_math(
        r"g = 4\pi^{2} \cdot \frac{h_{1}^{2} - h_{2}^{2}}{h_{1}T_{1}^{2} - h_{2}T_{2}^{2}}"
    )
    doc.add_paragraph("卡特公式为")
    doc.add_math(
        r"\frac{4\pi^{2}}{g} = "
        r"\frac{T_{1}^{2} + T_{2}^{2}}{2(h_{1} + h_{2})} + "
        r"\frac{T_{1}^{2} - T_{2}^{2}}{2(h_{1} - h_{2})}"
    )
    doc.add_paragraph("将卡特公式右端通分：")
    doc.add_math(
        r"\frac{4\pi^{2}}{g} = "
        r"\frac{(T_{1}^{2} + T_{2}^{2})(h_{1} - h_{2}) + (T_{1}^{2} - T_{2}^{2})(h_{1} + h_{2})}"
        r"{2(h_{1} + h_{2})(h_{1} - h_{2})}"
    )
    doc.add_paragraph("将分子展开：")
    doc.add_math(
        r"(T_{1}^{2} + T_{2}^{2})(h_{1} - h_{2}) + (T_{1}^{2} - T_{2}^{2})(h_{1} + h_{2}) = "
        r"2T_{1}^{2}h_{1} - 2T_{2}^{2}h_{2}"
    )
    doc.add_paragraph("分母为：")
    doc.add_math(r"2(h_{1} + h_{2})(h_{1} - h_{2}) = 2(h_{1}^{2} - h_{2}^{2})")
    doc.add_paragraph("因此")
    doc.add_math(
        r"\frac{4\pi^{2}}{g} = \frac{2(T_{1}^{2}h_{1} - T_{2}^{2}h_{2})}{2(h_{1}^{2} - h_{2}^{2})} = "
        r"\frac{T_{1}^{2}h_{1} - T_{2}^{2}h_{2}}{h_{1}^{2} - h_{2}^{2}}"
    )
    doc.add_paragraph("取倒数即得二次法公式：")
    doc.add_math(
        r"g = 4\pi^{2} \cdot \frac{h_{1}^{2} - h_{2}^{2}}{h_{1}T_{1}^{2} - h_{2}T_{2}^{2}}"
    )
    doc.add_paragraph("故二次法测 g 的公式与卡特公式完全等效。")

    # 第2题
    doc.add_heading(
        "2. 为什么不能用图3-3-2中 C 点的 (T₁, h₁) 和 F 点的 (T₂, h₂) 来计算重力加速度 g，"
        "而须用 (F, D) 或 (F, E) 来计算？",
        level=2,
    )
    doc.add_paragraph(
        "答：在 T-h 关系曲线中，A、B 两点为共轭的周期极小值点。"
        "在极小值以上作水平线（等 T 线），交曲线于 C、D、E、F 四个点。"
        "其中，C 与 D 位于同一侧（构成一对等值单摆长 l = h_C + h_D），"
        "E 与 F 位于同一侧（构成另一对等值单摆长 l = h_E + h_F）。"
    )
    doc.add_paragraph(
        "若取 C 点和 F 点，它们分属两侧不同支，其悬距之和 h_C + h_F 并不等于正确的等值单摆长，"
        "因此无法正确求出 g。"
    )
    doc.add_paragraph(
        "此外，C 点位于极小值 A 附近，此处 T 随 h 的变化十分剧烈，"
        "微小的 h 读数误差即会导致显著的周期偏差，从而引入较大的计算误差。"
        "而 F 点是离极小值最远的点，T 随 h 变化平缓，测量最为稳定。"
        "因此应选取最大的 F 点与同侧的对称点 D（或另一侧的对称点 E）构成等值单摆长来计算 g，"
        "以获得最精确的结果。"
    )

    # 第3题
    doc.add_heading(
        "3. 试述用摆动法测量任意形状物体对任一指定轴的转动惯量的实验步骤"
        "（设当地的重力加速度 g 已知）。",
        level=2,
    )
    doc.add_paragraph("答：实验步骤如下：")
    doc.add_paragraph(
        "（1）确定转轴与支点：将物体悬挂于指定转轴，确保转轴水平固定且支点稳定，"
        "使物体可在铅直面内自由摆动。"
    )
    doc.add_paragraph(
        "（2）测量摆动周期 T：使物体在小角度（小于 1°）下作自由摆动，"
        "用光电计时器多次测量摆动周期（建议以 10T 计数），取平均值作为单周期 T。"
    )
    doc.add_paragraph(
        "（3）测量质量与质心位置：用天平称出物体质量 M；"
        "用杠杆平衡原理确定物体质心 C 的位置，测量支点 O 到质心 C 的距离 h。"
    )
    doc.add_paragraph("（4）计算绕支点的转动惯量：由复摆周期公式")
    doc.add_math(r"T = 2\pi\sqrt{\frac{J_0}{Mgh}}")
    doc.add_paragraph("解出")
    doc.add_math(r"J_0 = \frac{MghT^{2}}{4\pi^{2}}")
    doc.add_paragraph("")
    doc.add_run("再利用平行轴定理 ")
    doc.add_inline_math("J_c = J_0 - Mh^{2}")
    doc.add_run(" 求出物体绕质心轴的转动惯量。")
    doc.add_paragraph(
        "（5）多次测量取平均：改变支点位置重复上述步骤，"
        "对多次测量结果取平均值，分析误差来源（摆角、摩擦、计时精度等），"
        "以提高转动惯量的测量精度。"
    )

    # ── 保存 ──
    doc.save()
    doc.close()


def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "重力加速度的测量（复摆）.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    _generate_docx(data, DOCX_FILE)
    print(f"报告已生成: {DOCX_FILE}")


if __name__ == "__main__":
    main()
