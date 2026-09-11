"""电子元件伏安特性测量实验 — 数据处理脚本。"""

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
# 实验参数
# ============================================================

N_COLS = 10          # 每张表的数据列数（B~K 列）
MIN_POINTS_T3 = 3    # 表3（二极管）至少填写的数据点数
I_MAX_T3 = 20.0      # 二极管正向电流上限 / mA（教材规定）

# 模板单元格布局（_create_template 与读取区一一对应）
T1_TITLE, T1_US, T1_I, T1_U, T1_R = 3, 4, 5, 6, 7      # 表1 线性电阻
T2_TITLE, T2_US, T2_I, T2_U, T2_R = 9, 10, 11, 12, 13  # 表2 钨丝灯泡
T3_TITLE, T3_I, T3_U, T3_R = 15, 16, 17, 18            # 表3 二极管正向特性
T3_NOTE = 19

DATA_COLS = "BCDEFGHIJK"  # 数据区 10 列的列字母（错误提示中沿用列位置说法）

# data.json 数据键（与 schema.json / data.json 顶层键一一对应，方式三唯一契约）
#   表1: t1_us/t1_i/t1_u ← 原第 T1_US/T1_I/T1_U 行 B~K
#   表2: t2_us/t2_i/t2_u ← 原第 T2_US/T2_I/T2_U 行 B~K
#   表3: t3_i/t3_u       ← 原第 T3_I/T3_U 行 B~K（可不填满，尾部为 null）
# R 行（T1_R/T2_R/T3_R）为脚本自动计算值，不存数据。
# 以下行常量仅保留给 _create_template（xlsx 已降级为可选导出视图）。


# ============================================================
# Excel 模板生成
# ============================================================

# （方式三：_create_template 已移除，数据真相为 data.json）


# ============================================================
# 读取与校验（数据真相：data.json，见 schema.json 的 key）
# ============================================================

def _read_row(data: dict, key: str):
    """读取 data[key] 一行的 10 个数据点（对应原 B~K 共 10 列），不足定长补 None。"""
    values = list(data.get(key) or [])
    if len(values) < N_COLS:
        values += [None] * (N_COLS - len(values))
    return values[:N_COLS]


def _read_and_validate(data: dict):
    """读取三张数据表；校验失败打印原因并返回 None。"""
    missing = []

    def _require_full(key, name):
        values = _read_row(data, key)
        for j, v in enumerate(values):
            if v is None:
                missing.append(f"{name} 第 {j + 1} 个点（{DATA_COLS[j]} 列位）")
        return values

    t1_us = _require_full("t1_us", "表1 Us/V")
    t1_i = _require_full("t1_i", "表1 I/mA")
    t1_u = _require_full("t1_u", "表1 U/V")
    t2_us = _require_full("t2_us", "表2 Us/V")
    t2_i = _require_full("t2_i", "表2 灯泡电流 I/mA")
    t2_u = _require_full("t2_u", "表2 灯泡电压 U/V")

    # 表3：整列空 → 跳过（允许不填满 10 列）；只填一半 → 记入 missing
    t3_i_raw = _read_row(data, "t3_i")
    t3_u_raw = _read_row(data, "t3_u")
    t3 = []
    for j in range(N_COLS):
        iv, uv = t3_i_raw[j], t3_u_raw[j]
        if iv is None and uv is None:
            continue
        if iv is None:
            missing.append(f"表3 I/mA 第 {j + 1} 个点（{DATA_COLS[j]} 列位）")
        elif uv is None:
            missing.append(f"表3 U/V 第 {j + 1} 个点（{DATA_COLS[j]} 列位）")
        else:
            t3.append((float(iv), float(uv)))

    if missing:
        print("[错误] 以下必填数据为空（data.json / 应用表单），请填写后重新运行：")
        for m in missing:
            print(f"  - {m}")
        return None

    ok = True
    for name, i_row, u_row in (
        ("表1", t1_i, t1_u),
        ("表2", t2_i, t2_u),
    ):
        for j in range(N_COLS):
            if float(i_row[j]) <= 0:
                print(f"[错误] {name} I/mA 第 {j + 1} 个点 ({i_row[j]}) 必须为正值。")
                ok = False
            if float(u_row[j]) <= 0:
                print(f"[错误] {name} U/V 第 {j + 1} 个点 ({u_row[j]}) 必须为正值。")
                ok = False

    # 表2 首末两点用于两点法求 n、K，lg 分式要求比值不为 1
    if ok:
        if float(t2_i[0]) == float(t2_i[-1]) or float(t2_u[0]) == float(t2_u[-1]):
            print("[错误] 表2 首末两点的 I 或 U 相等，无法用两点法计算 n、K，请检查数据。")
            ok = False

    if len(t3) < MIN_POINTS_T3:
        print(f"[错误] 表3 至少需要填写 {MIN_POINTS_T3} 个数据点（当前 {len(t3)} 个）。")
        ok = False
    for iv, uv in t3:
        if iv > I_MAX_T3:
            print(f"[错误] 表3 电流 {iv} mA 超过教材规定的 {I_MAX_T3:.0f} mA 上限，请检查数据。")
            ok = False
        if iv < 0 or uv < 0:
            print(f"[错误] 表3 数据点 (I={iv} mA, U={uv} V) 出现负值，请检查数据。")
            ok = False
    if not ok:
        return None

    return {
        "t1": ([float(v) for v in t1_us], [float(v) for v in t1_i], [float(v) for v in t1_u]),
        "t2": ([float(v) for v in t2_us], [float(v) for v in t2_i], [float(v) for v in t2_u]),
        "t3": t3,
    }


# ============================================================
# 数值计算辅助
# ============================================================

def _pchip_interp(x, y, x_new):
    """单调三次 Hermite 插值（Fritsch–Carlson），纯 numpy 实现。"""
    import numpy as np

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(x)
    h = np.diff(x)
    delta = np.diff(y) / h

    m = np.zeros(n)
    m[0], m[-1] = delta[0], delta[-1]
    for k in range(1, n - 1):
        if delta[k - 1] * delta[k] <= 0:
            m[k] = 0.0
        else:
            w1 = 2 * h[k] + h[k - 1]
            w2 = h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / delta[k - 1] + w2 / delta[k])

    idx = np.clip(np.searchsorted(x, x_new, side="right") - 1, 0, n - 2)
    t = (np.asarray(x_new, dtype=float) - x[idx]) / h[idx]
    h00 = 2 * t ** 3 - 3 * t ** 2 + 1
    h10 = t ** 3 - 2 * t ** 2 + t
    h01 = -2 * t ** 3 + 3 * t ** 2
    h11 = t ** 3 - t ** 2
    return h00 * y[idx] + h10 * h[idx] * m[idx] + h01 * y[idx + 1] + h11 * h[idx] * m[idx + 1]


def _sorted_unique_xy(x, y):
    """按 x 升序排序，重复 x 合并取 y 均值（pchip 要求 x 严格递增）。"""
    pairs = sorted(zip(x, y))
    xs, ys = [], []
    for xv, yv in pairs:
        if xs and math.isclose(xv, xs[-1]):
            ys[-1] = (ys[-1] + yv) / 2
        else:
            xs.append(xv)
            ys.append(yv)
    return xs, ys


# ============================================================
# 图表绘制
# ============================================================

def _plot_setup():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def _plot_linear_resistor(u, i_ma, output_path: str):
    """线性电阻伏安特性：散点 + 最小二乘拟合直线。"""
    plt = _plot_setup()

    fig, ax = plt.subplots(figsize=(8, 5.5))

    fit = linear_regression(u, i_ma)
    x_line = [0.0, max(u) * 1.05]
    y_line = [fit.intercept + fit.slope * xv for xv in x_line]
    ax.plot(x_line, y_line, color="steelblue", linewidth=1.5, label="线性拟合")
    ax.scatter(u, i_ma, color="steelblue", s=60, zorder=5, label="实验数据")

    ax.set_xlabel("U / V", fontsize=13)
    ax.set_ylabel("I / mA", fontsize=13)
    ax.set_title("线性电阻伏安特性曲线", fontsize=13)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.legend(fontsize=10, loc="upper left")

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def _plot_smooth_curve(u, i_ma, title: str, output_path: str):
    """非线性元件伏安特性：散点 + 单调平滑曲线（钨丝灯泡 / 二极管共用）。"""
    import numpy as np
    plt = _plot_setup()

    fig, ax = plt.subplots(figsize=(8, 5.5))

    xs, ys = _sorted_unique_xy(u, i_ma)
    if len(xs) >= 3:
        x_s = np.linspace(xs[0], xs[-1], 500)
        ax.plot(x_s, _pchip_interp(xs, ys, x_s), color="steelblue", linewidth=1.5)
    else:
        ax.plot(xs, ys, color="steelblue", linewidth=1.5)
    ax.scatter(u, i_ma, color="steelblue", s=60, zorder=5, label="实验数据")

    ax.set_xlabel("U / V", fontsize=13)
    ax.set_ylabel("I / mA", fontsize=13)
    ax.set_title(title, fontsize=13)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.legend(fontsize=10, loc="upper left")

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


# ============================================================
# docx 报告生成
# ============================================================

def _write_va_table(doc, rows):
    """输出横排数据表（照范例横排，拆成两半；首行作表头行）。

    rows = [(标签, [值字符串, ...]), ...]
    """
    n = len(rows[0][1])
    h1 = math.ceil(n / 2)
    for lo, hi in ((0, h1), (h1, n)):
        if lo >= hi:
            continue
        cols = hi - lo
        doc.add_table(
            headers=[rows[0][0]] + rows[0][1][lo:hi],
            rows=[[lab] + vals[lo:hi] for lab, vals in rows[1:]],
            col_widths=[3.2] + [2.15] * cols,
        )


def _generate_docx(data: dict, output_path: str) -> bool:
    """校验 data.json 数据 → 计算 → 绘图 → 输出 docx 报告。返回是否成功。"""
    # ---------- 1. 读取并校验数据（data.json） ----------
    parsed = _read_and_validate(data)
    if parsed is None:
        return False

    t1_us, t1_i, t1_u = parsed["t1"]
    t2_us, t2_i, t2_u = parsed["t2"]
    t3 = parsed["t3"]

    # ---------- 2. 计算 ----------
    # 表1/表2 逐点电阻 R = U/I（V / mA → ×1000 得 Ω）
    t1_r = [u / i * 1000.0 for i, u in zip(t1_i, t1_u)]
    t2_r = [u / i * 1000.0 for i, u in zip(t2_i, t2_u)]

    # 钨丝灯泡 U = K·I^n，两点法取首末两点（照范例）
    # n、K 均用文档中显示的舍入值链计算，保证文档内数值自洽
    u1, u2 = round(t2_u[0], 2), round(t2_u[-1], 2)
    i1, i2 = round(t2_i[0], 1), round(t2_i[-1], 1)
    lg_u = math.log10(u1 / u2)
    lg_i = math.log10(i1 / i2)
    n_disp = round(lg_u / lg_i, 3)
    i1_a = round(i1 / 1000.0, 4)  # 代入 K 时电流用安培
    K_disp = round(u1 * i1_a ** (-n_disp), 1)

    # 表3 逐点电阻 R = U/I（V / mA → 直除得 kΩ）；I=0 的点电阻无定义，记 "\"
    t3_r = [(u / i if i > 0 else None) for i, u in t3]

    # ---------- 3. 控制台输出 ----------
    print(f"\n{'=' * 50}")
    print(f"表1 线性电阻 R/Ohm: {[round(v, 1) for v in t1_r]}")
    print(f"表2 灯泡电阻 R/Ohm: {[round(v, 1) for v in t2_r]}")
    print(f"两点法: U1={u1} V, U2={u2} V, I1={i1} mA, I2={i2} mA")
    print(f"n = {n_disp}, K = {K_disp}")
    t3_r_disp = [("\\" if v is None else round(v, 3)) for v in t3_r]
    print(f"表3 二极管电阻 R/kOhm: {t3_r_disp}")
    print(f"{'=' * 50}\n")

    # ---------- 4. 绘制图表 ----------
    plot_t1 = os.path.join(SCRIPT_DIR, "线性电阻伏安特性曲线.png")
    plot_t2 = os.path.join(SCRIPT_DIR, "钨丝灯泡伏安特性曲线.png")
    plot_t3 = os.path.join(SCRIPT_DIR, "二极管正向伏安特性曲线.png")
    _plot_linear_resistor(t1_u, t1_i, plot_t1)
    _plot_smooth_curve(t2_u, t2_i, "钨丝灯泡伏安特性曲线", plot_t2)
    _plot_smooth_curve([u for _i, u in t3], [i for i, _u in t3],
                       "二极管正向伏安特性曲线", plot_t3)
    for p in (plot_t1, plot_t2, plot_t3):
        print(f"图已保存: {p}")

    # ---------- 5. 生成 docx ----------
    doc = DocxReportWriter(output_path)

    # ---- 零、实验标题 ----
    doc.add_title("电子元件伏安特性的测量")
    doc.add_student_info()

    # 变体组合：实验原理 / 实验方法（有 variants.json 且应用传入选择时生效）
    r1_mean = round(sum(t1_r) / len(t1_r), 1) if t1_r else 0.0
    r = {
        "u1": u1, "u2": u2, "i1": i1, "i2": i2,
        "n_disp": n_disp, "K_disp": K_disp, "r1_mean": r1_mean,
    }
    variants = compose(SCRIPT_DIR, r)
    if "实验原理" in variants:
        doc.add_heading("实验原理", level=1)
        doc.add_paragraph_rich(variants["实验原理"])
    if "实验方法" in variants:
        doc.add_heading("实验方法", level=1)
        doc.add_paragraph_rich(variants["实验方法"])

    # ---- 一、实验数据记录 ----
    doc.add_heading("一、实验数据记录", level=1)
    doc.add_paragraph("（请在此处粘贴原始数据记录照片。）")

    # ---- 二、数据处理 ----
    doc.add_heading("二、数据处理", level=1)

    # 1. 线性电阻
    doc.add_heading("1. 线性电阻的伏安特性", level=2)
    _write_va_table(doc, [
        ("Us/V", [f"{v:.2f}" for v in t1_us]),
        ("I/mA", [f"{v:.1f}" for v in t1_i]),
        ("U/V", [f"{v:.2f}" for v in t1_u]),
        ("R/Ω", [f"{v:.1f}" for v in t1_r]),
    ])
    doc.add_paragraph("由数据得到线性电阻的伏安特性曲线如下：")
    doc.add_image(plot_t1, width_cm=14)

    # 2. 钨丝灯泡
    doc.add_heading("2. 钨丝灯泡的伏安特性", level=2)
    _write_va_table(doc, [
        ("Us/V", [f"{v:.2f}" for v in t2_us]),
        ("灯泡电流I/mA", [f"{v:.1f}" for v in t2_i]),
        ("灯泡电压U/V", [f"{v:.2f}" for v in t2_u]),
        ("灯泡电阻计算值/Ω", [f"{v:.1f}" for v in t2_r]),
    ])
    doc.add_paragraph("由数据得到钨丝灯泡的伏安特性曲线如下：")
    doc.add_image(plot_t2, width_cm=14)

    doc.add_paragraph("")
    doc.add_run("求 n、K：由 ")
    doc.add_inline_math(r"U = KI^{n}")
    doc.add_run("，取 ")
    doc.add_inline_math(rf"U_{{1}} = {u1:.2f}\ \mathrm{{V}}")
    doc.add_run("；")
    doc.add_inline_math(rf"U_{{2}} = {u2:.2f}\ \mathrm{{V}}")
    doc.add_run("；")
    doc.add_inline_math(rf"I_{{1}} = {i1:.1f}\ \mathrm{{mA}}")
    doc.add_run("；")
    doc.add_inline_math(rf"I_{{2}} = {i2:.1f}\ \mathrm{{mA}}")
    doc.add_run("，可解得：")
    doc.add_math(
        r"n = \frac{\mathrm{lg}\frac{U_{1}}{U_{2}}}{\mathrm{lg}\frac{I_{1}}{I_{2}}}"
        rf" = \frac{{\mathrm{{lg}}\frac{{{u1:.2f}}}{{{u2:.2f}}}}}"
        rf"{{\mathrm{{lg}}\frac{{{i1:.1f}}}{{{i2:.1f}}}}}"
        rf" = \frac{{\mathrm{{lg}}{u1 / u2:.2f}}}{{\mathrm{{lg}}{i1 / i2:.2f}}}"
        rf" = \frac{{{lg_u:.3f}}}{{{lg_i:.3f}}} = {n_disp:.3f}"
    )
    doc.add_math(
        rf"K = U_{{1}} \cdot I_{{1}}^{{-n}} = {u1:.2f} \times {i1_a:.4f}^{{{-n_disp:.3f}}}"
        rf" \approx {K_disp:.1f}"
    )

    # 3. 二极管正向特性
    doc.add_heading("3. 二极管正向伏安特性", level=2)
    _write_va_table(doc, [
        ("I/mA", [f"{i:.1f}" for i, _u in t3]),
        ("U/V", [f"{u:.3f}" for _i, u in t3]),
        ("电阻计算值/kΩ", ["\\" if v is None else f"{v:.3f}" for v in t3_r]),
    ])
    doc.add_paragraph("由数据得到二极管的正向伏安特性曲线如下：")
    doc.add_image(plot_t3, width_cm=14)

    # 变体组合：误差分析 / 结论
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])
    if "结论" in variants:
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    # ---- 三、课后思考题 ----
    doc.add_heading("三、课后思考题", level=1)

    doc.add_paragraph("1. 比较 100Ω 电阻与白炽灯的伏安特性曲线，可得出什么结论？")
    doc.add_paragraph(
        "答：100Ω 电阻是线性元件，其伏安特性曲线是过原点的直线，"
        "表明电压与电流成正比，电阻值恒定为 100Ω。"
    )
    doc.add_paragraph(
        "白炽灯灯丝，其伏安特性曲线是曲线。随着电压升高，电流增大，灯丝温度升高，"
        "电阻率增大，电阻增大，即灯丝电阻随温度升高而增大。"
    )
    doc.add_paragraph(
        "比较二者可得出：100Ω 电阻阻值不随电压、电流变化；"
        "白炽灯电阻随电压、电流增大（灯丝温度升高）而增大，是非线性元件。"
    )

    doc.add_paragraph("2. 试从钨丝灯泡的伏安特性曲线解释，为什么在开灯的时候容易烧坏？")
    doc.add_paragraph(
        "答：钨丝灯泡的伏安特性曲线表明其电阻随温度变化。开灯瞬间，钨丝温度低，"
        "由伏安特性曲线可知此时电阻较小。"
    )
    doc.add_paragraph("")
    doc.add_run("根据欧姆定律 ")
    doc.add_inline_math(r"I = U/R")
    doc.add_run("（家庭电路电压 U 基本恒定），电阻 R 小则电流 I 较大。")
    doc.add_paragraph(
        "较大的电流会在瞬间产生较多热量，使钨丝温度急剧上升，钨丝受到较大的热冲击，"
        "加之此时钨丝温度低、韧性等物理性能相对较差，所以在开灯的时候容易烧坏。"
    )

    doc.add_paragraph("3. 二极管反向电阻和正向电阻差异如此大，其物理原理是什么？")
    doc.add_paragraph("答：二极管是由半导体材料制成，其内部结构包含一个 PN 结。")
    doc.add_paragraph(
        "从物理原理来看，正向导通时：当在二极管两端加上正向电压（P 区接高电位，"
        "N 区接低电位），外电场方向与 PN 结内电场方向相反，削弱了内电场。"
        "内电场原本会阻碍多子（P 区的空穴和 N 区的电子）的扩散运动，"
        "内电场被削弱后，多子扩散运动加剧，大量的电子-空穴对复合，"
        "形成较大的正向电流，此时二极管呈现出较小的电阻，即正向电阻较小。"
    )
    doc.add_paragraph(
        "反向截止时：当在二极管两端加上反向电压（P 区接低电位，N 区接高电位），"
        "外电场方向与 PN 结内电场方向相同，增强了内电场。"
        "这使得多子的扩散运动难以进行，少子（P 区的电子和 N 区的空穴）"
        "在电场作用下产生漂移运动，但由于少子数量很少，只能形成极其微弱的反向电流，"
        "几乎可以忽略不计，此时二极管呈现出很大的电阻，即反向电阻很大。"
    )
    doc.add_paragraph(
        "综上所述，由于 PN 结在不同外加电压下对多子和少子运动的影响不同，"
        "导致了二极管反向电阻和正向电阻差异巨大。"
    )

    doc.save()
    doc.close()
    return True


# ============================================================
# 入口
# ============================================================

def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "电子元件伏安特性的测量实验报告.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    # 必填项 None 检查（schema.json 中 required=true 的键）
    required_missing = [k for k in ("t1_us", "t1_i", "t1_u", "t2_us", "t2_i", "t2_u")
                        if data.get(k) is None]
    if required_missing:
        print("以下必填数据未填写（data.json 中为 null），请在应用中补齐后重新运行：")
        for k in required_missing:
            print(f"  - {k}")
        return

    if _generate_docx(data, DOCX_FILE):
        print(f"报告已生成: {DOCX_FILE}")


if __name__ == "__main__":
    main()
