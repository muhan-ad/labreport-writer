"""RLC电路的稳态特性研究实验 — 数据处理脚本。"""

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

N_POINTS = 13        # 模板频率点行数（照范例）
MIN_POINTS = 5       # 每张表至少填写的频率点数

# 模板单元格布局（方式三：仅供 _create_template 生成空白模板；数据真相为 data.json）
ROW_L, ROW_C, ROW_R, ROW_F0P = 3, 4, 5, 6   # 给定量 B 列
T1_HEAD, T1_FIRST = 9, 10                    # 表1 表头行 / 首数据行（B~D 列）
T2_HEAD, T2_FIRST = 25, 26                   # 表2 表头行 / 首数据行（B~D 列）


# ============================================================
# Excel 模板生成
# ============================================================

# （方式三：_create_template 已移除，数据真相为 data.json）


# ============================================================
# 读取与校验
# ============================================================

def _read_table(matrix, col_labels, table_name: str, missing: list):
    """读取一张数据表（来自 data[key] 的 13 行 × 3 列定长矩阵）。

    整行空 → 跳过；部分空 → 记入 missing。返回 [(行号, b, c, d), ...]。
    方式三：不再读 Excel，matrix 为 data.json 中的二维数组。
    """
    points = []
    if not isinstance(matrix, list):
        return points
    for i, row in enumerate(matrix):
        idx = i + 1
        cells = list(row)[:3] if isinstance(row, list) else [row]
        cells += [None] * (3 - len(cells))
        b, c, d = cells
        if b is None and c is None and d is None:
            continue  # 未使用的行
        for lbl, v in zip(col_labels, (b, c, d)):
            if v is None:
                missing.append(f"{table_name} 第 {idx} 行「{lbl}」")
        if b is not None and c is not None and d is not None:
            points.append((idx, float(b), float(c), float(d)))
    return points


def _read_and_validate(data: dict):
    """读取给定量与两张数据表（均来自 data.json）；校验失败打印原因并返回 None。"""
    given = {}
    missing = []
    # 必填标量（required 字段为 null → 缺失）
    for key in ("L", "C", "R", "f0p"):
        v = data.get(key)
        if v is None:
            missing.append(f"给定量 {key}")
        else:
            given[key] = float(v)

    # 矩阵（整行空跳过，部分空记入 missing）
    t1 = _read_table(data.get("t1"), ("f", "Ui", "VR"), "表1", missing)
    t2 = _read_table(data.get("t2"), ("f", "A格Ui", "B格UR"), "表2", missing)

    if missing:
        print("[错误] 以下数据项为空，请在应用中填写后重新运行：")
        for m in missing:
            print(f"  - {m}")
        return None

    ok = True
    if len(t1) < MIN_POINTS:
        print(f"[错误] 表1 至少需要填写 {MIN_POINTS} 个频率点（当前 {len(t1)} 个）。")
        ok = False
    if len(t2) < MIN_POINTS:
        print(f"[错误] 表2 至少需要填写 {MIN_POINTS} 个频率点（当前 {len(t2)} 个）。")
        ok = False
    for row_no, _f, a, b in t2:
        if b > a:
            print(f"[错误] 表2 第 {row_no} 行：B格读数 ({b}) 大于 A格读数 ({a})，"
                  "超出 arcsin 定义域，请检查数据。")
            ok = False
    if not ok:
        return None

    return {"given": given, "t1": t1, "t2": t2}


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


def _find_bandwidth(f_sorted, i_sorted):
    """求半功率点：I_max/√2 与折线（原始数据线性内插）的左右交点。

    返回 (thr, f1, f2)；某侧数据未降到阈值以下时对应值为 None。
    """
    i_max = max(i_sorted)
    thr = i_max / math.sqrt(2)
    peak = i_sorted.index(i_max)

    def _cross(k):
        return f_sorted[k] + (thr - i_sorted[k]) * \
            (f_sorted[k + 1] - f_sorted[k]) / (i_sorted[k + 1] - i_sorted[k])

    f1 = f2 = None
    for k in range(peak - 1, -1, -1):  # 峰值左侧，向左找上穿点
        if i_sorted[k] <= thr <= i_sorted[k + 1] and i_sorted[k] != i_sorted[k + 1]:
            f1 = _cross(k)
            break
    for k in range(peak, len(i_sorted) - 1):  # 峰值右侧，向右找下穿点
        if i_sorted[k] >= thr >= i_sorted[k + 1] and i_sorted[k] != i_sorted[k + 1]:
            f2 = _cross(k)
            break
    return thr, f1, f2


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


def _plot_amplitude(f, i_ma, thr, f1, f2, output_path: str):
    """绘制幅频特性 I~f 曲线，标注 I_max/√2 阈值线与通频带。"""
    import numpy as np
    plt = _plot_setup()

    fig, ax = plt.subplots(figsize=(8, 5.5))

    x_s = np.linspace(f[0], f[-1], 500)
    ax.plot(x_s, _pchip_interp(f, i_ma, x_s), color="steelblue", linewidth=1.5)
    ax.scatter(f, i_ma, color="steelblue", s=60, zorder=5, label="实验数据")

    ax.axhline(thr, color="red", linestyle="--", linewidth=1.2,
               label=r"$I_{max}/\sqrt{2}$" + f" ≈ {thr:.2f} mA")

    if f1 is not None and f2 is not None:
        y_arrow = thr * 0.55
        ax.axvline(f1, color="gray", linestyle=":", linewidth=1)
        ax.axvline(f2, color="gray", linestyle=":", linewidth=1)
        ax.annotate("", xy=(f1, y_arrow), xytext=(f2, y_arrow),
                    arrowprops=dict(arrowstyle="<->", color="gray"))
        ax.text((f1 + f2) / 2, y_arrow * 1.08,
                f"通频带 Δf ≈ {f2 - f1:.2f} kHz\n"
                f"(f1 ≈ {f1:.2f} kHz, f2 ≈ {f2:.2f} kHz)",
                ha="center", fontsize=10)

    ax.set_xlabel("f / kHz", fontsize=13)
    ax.set_ylabel("I / mA", fontsize=13)
    ax.set_title("RLC 串联电路幅频特性曲线（I~f）", fontsize=13)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.legend(fontsize=10, loc="upper right")

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def _plot_phase(f, phi, output_path: str):
    """绘制相频特性 φ~f 曲线。"""
    import numpy as np
    plt = _plot_setup()

    fig, ax = plt.subplots(figsize=(8, 5.5))

    x_s = np.linspace(f[0], f[-1], 500)
    ax.plot(x_s, _pchip_interp(f, phi, x_s), color="steelblue", linewidth=1.5)
    ax.scatter(f, phi, color="steelblue", s=60, zorder=5, label="实验数据")
    ax.axhline(0, color="gray", linewidth=0.8)

    ax.set_xlabel("f / kHz", fontsize=13)
    ax.set_ylabel("φ / rad", fontsize=13)
    ax.set_title("RLC 串联电路相频特性曲线（φ~f）", fontsize=13)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.legend(fontsize=10, loc="lower right")

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


# ============================================================
# 数据处理计算（结果字典供报告与变体 %%DATA 注入共用）
# ============================================================

def _compute(data: dict) -> dict:
    """读取校验 data.json 并完成全部数值计算，返回结果字典 r。

    校验失败返回 None。键与量纲：
    - f0 / f0p: kHz（理论 / 实测谐振频率）；eta: %（相对偏差，已乘 100）
    - t1_f: kHz；t1_i: mA（表1 频率与电流）
    - t2_f: kHz；t2_a / t2_b: V（含符号修正）；t2_phi: rad
    - i_max / thr: mA（峰值与半功率电流）
    - f1 / f2 / df: kHz（半功率截止频率与通频带，未覆盖时为 None）
    - q: 无量纲（实验品质因数 f0/Δf，无法确定时为 None）
    """
    payload = _read_and_validate(data)
    if payload is None:
        return None

    L_mh = payload["given"]["L"]
    C_uf = payload["given"]["C"]
    R_ohm = payload["given"]["R"]
    f0p = payload["given"]["f0p"]

    # 理论谐振频率 f0 = 1/(2π√(LC))，L: mH → H，C: μF → F，结果 Hz → kHz
    # η 用舍入后的显示值计算，保证文档内数值自洽（与范例做法一致）
    f0 = round(1.0 / (2.0 * math.pi * math.sqrt(L_mh * 1e-3 * C_uf * 1e-6)) / 1000.0, 3)
    eta = abs(f0 - f0p) / f0 * 100.0

    # 表1：I = V_R / R（V/Ω → A，×1000 → mA），按 f 升序排列
    t1 = sorted(payload["t1"], key=lambda p: p[1])
    t1_f = [p[1] for p in t1]
    t1_i = [p[3] / R_ohm * 1000.0 for p in t1]

    # 表2：φ = ±arcsin(B/A)，f < f0' 时电流超前、φ 取负；按 f 升序排列
    t2 = sorted(payload["t2"], key=lambda p: p[1])
    t2_f = [p[1] for p in t2]
    t2_a = [p[2] for p in t2]
    t2_b = []
    t2_phi = []
    for _row, f, a, b in t2:
        sign = -1.0 if f < f0p else 1.0
        b_signed = 0.0 if b == 0 else sign * b
        t2_b.append(b_signed)
        t2_phi.append(0.0 if b == 0 else sign * math.asin(b / a))

    # 通频带与派生特征量
    thr, f1, f2 = _find_bandwidth(t1_f, t1_i)
    i_max = max(t1_i)
    df = (f2 - f1) if (f1 is not None and f2 is not None) else None
    q = (f0 / df) if (df is not None and df > 0) else None

    return {
        "f0": f0, "f0p": f0p, "eta": eta,
        "t1_f": t1_f, "t1_i": t1_i,
        "t2_f": t2_f, "t2_a": t2_a, "t2_b": t2_b, "t2_phi": t2_phi,
        "i_max": i_max, "thr": thr, "f1": f1, "f2": f2, "df": df, "q": q,
    }


# ============================================================
# docx 报告生成
# ============================================================

def _write_phase_table(doc, f_vals, a_vals, b_signed, phi_vals):
    """输出负号修正后的相频数据表（照范例横排，拆成两半）。"""
    n = len(f_vals)
    h1 = math.ceil(n / 2)
    for lo, hi in ((0, h1), (h1, n)):
        if lo >= hi:
            continue
        cols = hi - lo
        doc.add_table(
            headers=["$f$ / kHz"] + [f"{v:.3f}" for v in f_vals[lo:hi]],
            rows=[
                ["A格 $U_i$ / V"] + [f"{v:g}" for v in a_vals[lo:hi]],
                ["B格 $U_r$ / V"] + [f"{v:g}" for v in b_signed[lo:hi]],
                ["$\\phi$ / rad"] + [f"{v:.4f}" for v in phi_vals[lo:hi]],
            ],
            col_widths=[2.2] + [1.6] * cols,
        )


def _generate_docx(data: dict, output_path: str) -> bool:
    """从 data.json 读取数据 → 校验 → 计算 → 绘图 → 输出 docx 报告。返回是否成功。"""
    # ---------- 1~2. 读取校验与计算（见 _compute）----------
    r = _compute(data)
    if r is None:
        return False

    f0 = r["f0"]
    f0p = r["f0p"]
    eta = r["eta"]
    t1_f = r["t1_f"]
    t1_i = r["t1_i"]
    t2_f = r["t2_f"]
    t2_a = r["t2_a"]
    t2_b = r["t2_b"]
    t2_phi = r["t2_phi"]
    thr = r["thr"]
    f1 = r["f1"]
    f2 = r["f2"]

    # ---------- 3. 控制台输出 ----------
    print(f"\n{'=' * 50}")
    print(f"理论谐振频率 f0  = {f0:.3f} kHz")
    print(f"实测谐振频率 f0' = {f0p:.3f} kHz")
    print(f"相对误差 eta = {eta:.2f} %")
    print(f"\n表1 电流值 I/mA: {[round(v, 3) for v in t1_i]}")
    print(f"表2 相位 phi/rad: {[round(v, 4) for v in t2_phi]}")
    print(f"\n半功率电流 I_max/sqrt(2) = {thr:.3f} mA")
    if f1 is not None and f2 is not None:
        print(f"通频带: f1 = {f1:.2f} kHz, f2 = {f2:.2f} kHz, Δf = {f2 - f1:.2f} kHz")
    else:
        print("[警告] 数据未完整覆盖半功率点，无法确定通频带边界（图中仅画阈值线）。")
    print(f"{'=' * 50}\n")

    # ---------- 4. 绘制图表 ----------
    amp_plot = os.path.join(SCRIPT_DIR, "幅频特性曲线.png")
    phase_plot = os.path.join(SCRIPT_DIR, "相频特性曲线.png")
    _plot_amplitude(t1_f, t1_i, thr, f1, f2, amp_plot)
    _plot_phase(t2_f, t2_phi, phase_plot)
    print(f"图已保存: {amp_plot}")
    print(f"图已保存: {phase_plot}")

    # ---------- 5. 生成 docx ----------
    doc = DocxReportWriter(output_path)

    # ---- 零、实验标题 ----
    doc.add_title("RLC 串联电路的稳态特性实验")
    doc.add_student_info()

    # ---- 变体组合：实验原理 / 实验方法（存在 variants.json 且应用传入选择时生效）----
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

    # 1. 计算谐振频率
    doc.add_heading("1. 计算谐振频率", level=2)
    doc.add_paragraph("由公式得理论谐振频率：")
    doc.add_math(r"f_{0} = \frac{1}{2\pi \sqrt{LC}} \approx "
                 + f"{f0:.3f}" + r"\ \mathrm{kHz}")
    doc.add_paragraph("")
    doc.add_run("实际谐振频率 ")
    doc.add_inline_math(r"f_{0}' = " + f"{f0p:.3f}" + r"\ \mathrm{kHz}")
    doc.add_run("，则误差：")
    doc.add_math(r"\eta = \frac{|f_{0} - f_{0}'|}{f_{0}} \approx "
                 + f"{eta:.2f}" + "%")

    # 2. 幅频特性的测量
    doc.add_heading("2. 幅频特性的测量", level=2)
    doc.add_paragraph("由数据得到 I～f 特性曲线及通频带如下：")
    doc.add_image(amp_plot, width_cm=14)

    # 3. 相频特性的测量
    doc.add_heading("3. 相频特性的测量", level=2)
    doc.add_paragraph("实际上，上文的数据在记录时未添加负号，下面是修正后的数据：")
    _write_phase_table(doc, t2_f, t2_a, t2_b, t2_phi)
    doc.add_paragraph("由数据得到 φ～f 特性曲线如下：")
    doc.add_image(phase_plot, width_cm=14)

    # ---- 三、实验结果分析 ----
    doc.add_heading("三、实验结果分析", level=1)
    doc.add_paragraph(
        "RLC 串联电路在谐振频率附近呈现明显的选频特性，电流达到最大，电压与电流同相。"
        "实验测得的谐振频率与理论值基本一致，误差在合理范围内。"
        "幅频曲线与相频曲线的变化趋势符合理论预期，验证了 RLC 串联电路的稳态特性。"
        "可能的误差来自于读数误差，即示波器格值读取时存在视觉偏差。"
        "以及内阻与分布参数，即信号源内阻、导线电阻、分布电容等未被完全计入，"
        "影响谐振点的准确测量。"
    )

    # ---- 变体组合：误差分析 / 结论（存在 variants.json 且应用传入选择时生效）----
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])
    if "结论" in variants:
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    # ---- 四、思考题 ----
    doc.add_heading("四、思考题", level=1)

    doc.add_paragraph("1. RLC 串联电路中谐振时的特点是什么？")
    doc.add_paragraph(
        "答：RLC 串联电路的谐振频率是指电路呈现纯电阻性、总阻抗最小、电流最大的频率点。"
        "此时电感与电容的阻抗相互抵消，电压与电流同相。"
    )

    doc.add_paragraph("")
    doc.add_run("2. RLC 串联电路实验中 U 和 ")
    doc.add_inline_math(r"U_{R}")
    doc.add_run("、")
    doc.add_inline_math(r"U_{C}")
    doc.add_run(" 以及 ")
    doc.add_inline_math(r"U_{L}")
    doc.add_run(" 不是代数和的关系，请问原因是什么？")

    doc.add_paragraph("")
    doc.add_run("答：因为这些电压之间存在相位差。在交流电路中，电压和电流均为正弦量，"
                "具有幅度和相位。由于电阻、电感和电容的特性不同：即电阻电压 ")
    doc.add_inline_math(r"U_{R}")
    doc.add_run(" 与电流同相位、电感电压 ")
    doc.add_inline_math(r"U_{L}")
    doc.add_run(" 超前电流 90°、电容电压 ")
    doc.add_inline_math(r"U_{C}")
    doc.add_run(" 滞后电流 90°。")

    doc.add_paragraph(
        "因此，三者瞬时值之和等于总电压瞬时值，但有效值之间不能直接相加。"
        "它们的合成需采用相量加法，即总电压有效值为："
    )
    doc.add_math(r"U = \sqrt{U_{R}^{2} + (U_{L} - U_{C})^{2}}")

    doc.save()
    doc.close()
    return True


# ============================================================
# 入口
# ============================================================

def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "RLC电路的稳态特性研究实验报告.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    if _generate_docx(data, DOCX_FILE):
        print(f"报告已生成: {DOCX_FILE}")


if __name__ == "__main__":
    main()
