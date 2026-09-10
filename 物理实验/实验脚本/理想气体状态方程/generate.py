"""理想气体状态方程实验 — 数据处理脚本。"""

import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import *
from common.docx_report import DocxReportWriter
from common.data_io import load_data

# ============================================================
# 实验参数
# ============================================================

R_THEORY = 8.31      # 普适气体常数 J/(mol·K)（照范例）
N_POINTS = 10        # 每张表的测量点数（照范例）

# 实验协议设定值（模板预填，用户可按实际修改）
PROTOCOL_V = [220, 215, 210, 205, 200, 195, 190, 185, 180, 175]   # 可视体积 V′/mL
PROTOCOL_T = [18.0, 21.0, 24.0, 27.0, 30.0, 33.0, 36.0, 39.0, 42.0, 45.0]  # 升温温度 t/℃
PROTOCOL_VP = 220    # 等容过程体积视值 V′/mL

# 模板单元格布局（仅 _create_template 使用；数据读取已迁移到 data.json）
ROW_P0, ROW_T_ISO, ROW_VP = 3, 4, 5          # 给定量 B 列
TA_TITLE, TA_HEAD = 7, 8                      # 表A 标题行 / 表头行
TA_V, TA_DP = 9, 10                           # 表A 可视体积 / 压强差（B~K 列）
TB_TITLE, TB_HEAD = 12, 13                    # 表B 标题行 / 表头行
TB_T_UP, TB_DP_UP = 14, 15                    # 表B 升温：温度 / 压强差
TB_T_DN, TB_DP_DN = 16, 17                    # 表B 降温：温度 / 压强差（选填）


# ============================================================
# Excel 模板生成（旧版模板代码，方式三迁移后保留不再调用）
# ============================================================

# （方式三：_create_template 已移除，数据真相为 data.json）


# ============================================================
# 数据校验（读取 data.json 提供的 data 字典）
# ============================================================

def _load_required_row(data: dict, key: str, name: str, missing: list):
    """读取一组 10 点必填数据（data[key]），空值记入 missing。"""
    raw = data.get(key) or []
    out = []
    for i in range(N_POINTS):
        v = raw[i] if i < len(raw) else None
        if v is None:
            missing.append(f"{key} 第 {i + 1} 点（{name}）")
        else:
            out.append(float(v))
    return out


def _load_cooling(data: dict, missing: list):
    """读取降温过程（选填）：整点留空跳过；只填一半记入 missing。"""
    t_raw = data.get("cool_t") or []
    dp_raw = data.get("cool_dp") or []
    pairs = []
    for i in range(max(len(t_raw), len(dp_raw))):
        t = t_raw[i] if i < len(t_raw) else None
        dp = dp_raw[i] if i < len(dp_raw) else None
        if t is None and dp is None:
            continue
        if t is None:
            missing.append(f"cool_t 第 {i + 1} 点（降温温度，需与压强差成对填写）")
        elif dp is None:
            missing.append(f"cool_dp 第 {i + 1} 点（降温压强差，需与温度成对填写）")
        else:
            pairs.append((float(t), float(dp)))
    return pairs


def _validate_data(data: dict):
    """校验给定量与两张数据表；失败打印原因并返回 None。"""
    missing = []
    given = {}
    for key, name in (("p0", "大气压"),
                      ("t_iso", "等温过程温度"),
                      ("vp", "体积视值")):
        v = data.get(key)
        if v is None:
            missing.append(f"{key}（给定量 {name}）")
        else:
            given[key] = float(v)

    ta_v = _load_required_row(data, "ta_v", "表A 可视体积", missing)
    ta_dp = _load_required_row(data, "ta_dp", "表A 压强差", missing)
    tb_t = _load_required_row(data, "tb_t", "表B 升温温度", missing)
    tb_dp = _load_required_row(data, "tb_dp", "表B 升温压强差", missing)
    cooling = _load_cooling(data, missing)

    if missing:
        print("[错误] 以下数据为空，请填写后重新运行：")
        for m in missing:
            print(f"  - {m}")
        return None

    ok = True
    for i, (v, dp) in enumerate(zip(ta_v, ta_dp)):
        if v <= 0:
            print(f"[错误] 表A 第 {i + 1} 列：可视体积 ({v}) 必须为正。")
            ok = False
        if given["p0"] + dp <= 0:
            print(f"[错误] 表A 第 {i + 1} 列：压强值 p0+Δp ({given['p0'] + dp}) 必须为正。")
            ok = False
    if not ok:
        return None

    for name, dps in (("表A", ta_dp), ("表B 升温", tb_dp)):
        for i, dp in enumerate(dps):
            if dp <= 0:
                print(f"[警告] {name} 第 {i + 1} 列：压强差 ({dp}) 非正，"
                      "本实验读数应为正值，请检查。")

    return {"given": given, "ta_v": ta_v, "ta_dp": ta_dp,
            "tb_t": tb_t, "tb_dp": tb_dp, "cooling": cooling}


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


def _plot_boyle(inv_p, v_vals, slope, intercept, output_path: str):
    """绘制 V′~1/p 图：数据点 + 最小二乘拟合直线。"""
    plt = _plot_setup()

    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.scatter(inv_p, v_vals, color="steelblue", s=60, zorder=5, label="实验数据")
    x0, x1 = min(inv_p), max(inv_p)
    ax.plot([x0, x1], [slope * x0 + intercept, slope * x1 + intercept],
            color="red", linewidth=1.5, label="线性拟合")

    ax.set_xlabel(r"$1/p$ / kPa$^{-1}$", fontsize=13)
    ax.set_ylabel(r"$V'$ / mL", fontsize=13)
    ax.set_title("同一温度下测量气体压强与体积的关系图", fontsize=13)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.legend(fontsize=10, loc="upper left")

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def _plot_charles(t_up, p_up, slope, intercept, cooling_tp, output_path: str):
    """绘制 p~T 图：升温数据点 + 拟合直线；有降温数据则叠加（不参与拟合）。"""
    plt = _plot_setup()

    fig, ax = plt.subplots(figsize=(8, 5.5))
    up_label = "升温过程" if cooling_tp else "实验数据"
    ax.scatter(t_up, p_up, color="steelblue", s=60, zorder=5, label=up_label)
    x0, x1 = min(t_up), max(t_up)
    ax.plot([x0, x1], [slope * x0 + intercept, slope * x1 + intercept],
            color="red", linewidth=1.5, label="线性拟合")

    if cooling_tp:
        t_dn, p_dn = zip(*cooling_tp)
        ax.plot(t_dn, p_dn, color="darkorange", linestyle="--", linewidth=1.2,
                marker="s", markersize=6, zorder=4, label="降温过程")

    ax.set_xlabel("T / K", fontsize=13)
    ax.set_ylabel("p / kPa", fontsize=13)
    ax.set_title("同一体积下测量气体压强与温度的关系图", fontsize=13)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.legend(fontsize=10, loc="upper left")

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


# ============================================================
# docx 报告生成
# ============================================================

def _generate_docx(data: dict, output_path: str) -> bool:
    """校验数据 → 计算 → 绘图 → 输出 docx 报告。返回是否成功。"""
    # ---------- 1. 校验 data.json 数据 ----------
    prepared = _validate_data(data)
    if prepared is None:
        return False
    data = prepared

    p0 = data["given"]["p0"]        # 大气压 kPa
    t_iso = data["given"]["t_iso"]  # 等温过程温度 ℃
    vp = data["given"]["vp"]        # 体积视值 mL

    # ---------- 2. 计算 ----------
    # 下游计算均使用舍入后的显示值，保证文档内数值自洽（与范例做法一致）
    # 1) 波义耳—马略特定律：p(V′+V₀) = nRT = k → V′ = k·(1/p) − V₀
    #    以 1/p 为横轴、V′ 为纵轴拟合：斜率 = k，截距 = −V₀
    T_iso = round(t_iso + 273.15, 2)
    ta_p = [round(p0 + dp, 2) for dp in data["ta_dp"]]
    inv_p = [1.0 / p for p in ta_p]
    fit1 = linear_regression(inv_p, data["ta_v"])
    k1 = round(fit1.slope)             # kPa·mL（1 kPa·mL = 10⁻³ J）
    V0 = round(-fit1.intercept, 2)     # mL
    # n = k/(R·T)，k 换算 10⁻³ J 后结果即为 10⁻³ mol
    n_mmol = round(k1 / (R_THEORY * T_iso), 2)

    # 2) 查理定律：p = k₂·T，k₂ = nR/(V′+V₀) → R = k₂(V′+V₀)/n
    tb_p = [round(p0 + dp, 2) for dp in data["tb_dp"]]
    tb_T = [round(t + 273.15, 2) for t in data["tb_t"]]
    fit2 = linear_regression(tb_T, tb_p)
    k2 = round(fit2.slope, 2)          # kPa/K
    R_exp = round(k2 * (vp + V0) / n_mmol, 2)   # kPa·mL/K / 10⁻³ mol = J/(mol·K)
    E = round(abs(R_exp - R_THEORY) / R_THEORY * 100, 1)

    cooling_tp = [(round(t + 273.15, 2), round(p0 + dp, 2))
                  for t, dp in data["cooling"]]

    # ---------- 3. 控制台输出 ----------
    print(f"\n{'=' * 50}")
    print(f"表1 压强值 p/kPa: {ta_p}")
    print(f"波义耳拟合: k = {k1} kPa*mL, V0 = {V0} mL (r^2 = {fit1.r_squared:.4f})")
    print(f"n = {n_mmol} x 10^-3 mol")
    print(f"表2 压强值 p/kPa: {tb_p}")
    print(f"查理拟合: k = {k2} kPa/K (r^2 = {fit2.r_squared:.4f})")
    print(f"R = {R_exp} J/(mol*K), 相对误差 E = {E} %")
    if cooling_tp:
        print(f"降温过程数据点: {len(cooling_tp)} 个（叠加绘图，不参与拟合）")
    print(f"{'=' * 50}\n")

    # ---------- 4. 绘制图表 ----------
    boyle_plot = os.path.join(SCRIPT_DIR, "波义耳定律图.png")
    charles_plot = os.path.join(SCRIPT_DIR, "查理定律图.png")
    _plot_boyle(inv_p, data["ta_v"], fit1.slope, fit1.intercept, boyle_plot)
    _plot_charles(tb_T, tb_p, fit2.slope, fit2.intercept, cooling_tp, charles_plot)
    print(f"图已保存: {boyle_plot}")
    print(f"图已保存: {charles_plot}")

    # ---------- 5. 生成 docx ----------
    doc = DocxReportWriter(output_path)

    # ---- 零、实验标题 ----
    doc.add_title("理想气体状态方程")
    doc.add_student_info()

    # ---- 一、实验数据记录 ----
    doc.add_heading("一、实验数据记录", level=1)
    doc.add_paragraph("（请在此处粘贴原始数据记录照片。）")

    # ---- 二、数据处理 ----
    doc.add_heading("二、数据处理", level=1)

    # 1. 验证波义耳—马略特定律
    doc.add_heading("1. 验证波义耳—马略特定律", level=2)
    doc.add_paragraph("表1　同一温度下测量气体压强与体积的关系表")
    doc.add_paragraph(f"大气压：{p0:g} kPa　　温度：{t_iso:g} ℃")
    doc.add_table(
        headers=["测量次数"] + [str(i + 1) for i in range(N_POINTS)],
        rows=[
            ["可视体积 V′/mL"] + [f"{v:g}" for v in data["ta_v"]],
            ["压强差 Δp/kPa"] + [f"{v:.2f}" for v in data["ta_dp"]],
            ["压强值 p/kPa"] + [f"{v:.2f}" for v in ta_p],
        ],
        col_widths=[2.8] + [1.12] * N_POINTS,
    )
    doc.add_paragraph("以 1/p 为横轴、可视体积 V′ 为纵轴作图并作线性拟合，"
                      "得同一温度下测量气体压强与体积的关系图：")
    doc.add_image(boyle_plot, width_cm=14)
    doc.add_paragraph("由图可验证波义耳—马略特定律：")
    doc.add_math(r"k = nRT,\ T = " + f"{T_iso:.2f}"
                 + r"\ \mathrm{K},\ R = 8.31\ \mathrm{J/(mol·K)}")
    doc.add_paragraph("")
    doc.add_run("由拟合直线斜率可得 ")
    doc.add_inline_math(r"k = " + f"{k1}" + r"\ \mathrm{kPa·mL}")
    doc.add_run("，所以")
    doc.add_math(r"n = \frac{k}{RT} \approx " + f"{n_mmol:.2f}"
                 + r"\times 10^{-3}\ \mathrm{mol}")
    doc.add_paragraph("")
    doc.add_run("由拟合直线截距可得 ")
    doc.add_inline_math(r"V_{0} = " + f"{V0:.2f}" + r"\ \mathrm{mL}")
    doc.add_run("。")

    # 2. 验证查理定律
    doc.add_heading("2. 验证查理定律", level=2)
    doc.add_paragraph("表2　同一体积下测量气体压强与温度的关系表")
    doc.add_paragraph(f"大气压：{p0:g} kPa　　体积视值 V′：{vp:g} mL")
    doc.add_table(
        headers=["测量次数"] + [str(i + 1) for i in range(N_POINTS)],
        rows=[
            ["温度 t/℃"] + [f"{v:.1f}" for v in data["tb_t"]],
            ["压强差 Δp/kPa"] + [f"{v:.2f}" for v in data["tb_dp"]],
            ["压强值 p/kPa"] + [f"{v:.2f}" for v in tb_p],
            ["绝对温度 T/K"] + [f"{v:.2f}" for v in tb_T],
        ],
        col_widths=[2.8] + [1.12] * N_POINTS,
    )
    charles_intro = ("以绝对温度 T 为横轴、压强值 p 为纵轴作图并作线性拟合，"
                     "得同一体积下测量气体压强与温度的关系图：")
    if cooling_tp:
        charles_intro = (charles_intro[:-1]
                         + "，图中同时绘出降温过程的测量数据以作对比（不参与拟合）：")
    doc.add_paragraph(charles_intro)
    doc.add_image(charles_plot, width_cm=14)
    doc.add_paragraph("由查理定律，p–T 直线的斜率为：")
    doc.add_math(r"k = \frac{nR}{V' + V_{0}}")
    doc.add_paragraph("")
    doc.add_run("由拟合直线可得 ")
    doc.add_inline_math(r"k \approx " + f"{k2:.2f}" + r"\ \mathrm{kPa/K}")
    doc.add_run("，经计算得：")
    doc.add_math(r"R = \frac{k(V' + V_{0})}{n} \approx " + f"{R_exp:.2f}"
                 + r"\ \mathrm{J/(mol·K)}")
    doc.add_paragraph("所以相对误差：")
    doc.add_math(r"E = \left|\frac{R - R_{\text{理论}}}{R_{\text{理论}}}\right| \times 100% \approx "
                 + f"{E:.1f}" + "%")

    # ---- 三、思考题 ----
    doc.add_heading("三、思考题", level=1)

    doc.add_paragraph("1. 三大气体实验定律的内容是什么？这些定律的适用范围是什么？"
                      "如果某种气体的三个状态参量（p、V、T）都发生了变化，"
                      "它们之间又遵从什么规律？")
    doc.add_paragraph("答：波义耳—马略特定律：在恒定温度下，一定质量气体压强与体积成反比。"
                      "查理定律：在恒定容积下，一定质量气体温度与压强成正比。"
                      "盖·吕萨克定律：在恒定压强下，一定质量气体的体积与温度成正比。")
    doc.add_paragraph("适用范围：理想气体，即分子间无相互作用力，体积可以忽略不计的气体。")
    doc.add_paragraph("")
    doc.add_run("规律：")
    doc.add_inline_math(r"pV = nRT")
    doc.add_run("。")

    doc.add_paragraph("2. 推导理想气体的状态方程。")
    doc.add_paragraph("")
    doc.add_run("答：气体的体积随压强 p、温度 T 以及气体分子的数量 N 而变，"
                "写成函数形式是 ")
    doc.add_inline_math(r"V = f(p,T,N)")
    doc.add_run("，对其求全微分：")
    doc.add_math(r"dV = (\frac{∂V}{∂p})_{T,N} dp + (\frac{∂V}{∂T})_{p,N} dT"
                 r" + (\frac{∂V}{∂N})_{T,p} dN")
    doc.add_paragraph("对于一定量的气体，N 为常数，dN = 0，所以有")
    doc.add_math(r"dV = (\frac{∂V}{∂p})_{T,N} dp + (\frac{∂V}{∂T})_{p,N} dT")
    doc.add_paragraph("")
    doc.add_run("根据波义耳—马略特定律，")
    doc.add_inline_math(r"V = C/p")
    doc.add_run("（C 为常数），于是有")
    doc.add_math(r"(\frac{∂V}{∂p})_{T,N} = -\frac{C}{p^{2}} = -\frac{V}{p}")
    doc.add_paragraph("")
    doc.add_run("根据盖·吕萨克定律，")
    doc.add_inline_math(r"V = C'T")
    doc.add_run("（C′ 为常数），于是有")
    doc.add_math(r"(\frac{∂V}{∂T})_{p,N} = C' = \frac{V}{T}")
    doc.add_paragraph("将两偏导数代入上式可得")
    doc.add_math(r"dV = -\frac{V}{p} dp + \frac{V}{T} dT")
    doc.add_paragraph("即")
    doc.add_math(r"\frac{dV}{V} = -\frac{dp}{p} + \frac{dT}{T}")
    doc.add_paragraph("上式两边同时求积分可得")
    doc.add_math(r"\ln{V} + \ln{p} = \ln{T} + C_{1}")
    doc.add_paragraph("故有")
    doc.add_math(r"\frac{pV}{T} = \text{恒量}")
    doc.add_paragraph("（气体质量一定）")
    doc.add_paragraph("又由 R 的定义：")
    doc.add_math(r"R = \frac{p_{0}V_{m}}{T_{0}} = 8.31\ \mathrm{J/(mol·K)}")
    doc.add_paragraph("式中 R 称为普适气体常数。对于任一物质的量为 n mol 的理想气体，有")
    doc.add_math(r"\frac{pV}{T} = \frac{p_{0}nV_{m}}{T_{0}} = nR")
    doc.add_paragraph("即")
    doc.add_math(r"pV = nRT")

    doc.add_paragraph("3. 升温曲线与降温曲线不同，如何解释？实验时应如何避免？")
    doc.add_paragraph("答：升温曲线与降温曲线不同的现象称为滞后现象，气体具有热惯性，"
                      "在升温过程中，气体需要时间吸收热量并达到新的平衡温度。"
                      "在降温过程中，气体也需要时间来释放热量并达到新的平衡温度。"
                      "这种热惯性会导致升温和降温曲线出现差异。")
    doc.add_paragraph("避免方法：慢慢加热或冷却：不要一下子把温度变得太高或太低，"
                      "而是慢慢地改变温度，这样可以让气体有更多的时间来适应温度的变化，"
                      "减少热惯性的影响。使用更好的隔热材料：这样可以减少热量的损失，"
                      "让气体更容易保持稳定的温度。确保实验装置的均匀性：让气体在实验装置中"
                      "均匀地加热或冷却，这样可以减少局部的温度差异，减少热惯性的影响。")

    doc.save()
    doc.close()
    return True


# ============================================================
# 入口
# ============================================================

def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "理想气体状态方程实验报告.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    if _generate_docx(data, DOCX_FILE):
        print(f"报告已生成: {DOCX_FILE}")


if __name__ == "__main__":
    main()
