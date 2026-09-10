"""用冲击法测量螺旋管磁场分布实验 — 数据处理脚本。

数据来自 data.json（结构由 schema.json 定义），运行生成 用冲击法测量螺旋管磁场分布实验.docx。
"""
import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import *
from common.docx_report import DocxReportWriter
from common.data_io import load_data

# ═══════════════════════════════════════════════════════════
# 物理常数
# ═══════════════════════════════════════════════════════════
MU0 = 4 * math.pi * 1e-7  # 真空磁导率 / (N/A²)

# ═══════════════════════════════════════════════════════════
# 仪器误差
# ═══════════════════════════════════════════════════════════
DELTA_AMMETER_A = 1.0e-3   # 直流电流表 Δ仪 / A (0.5级, 200mA量程 → 1.0mA)
DELTA_SCALE_MM = 0.5       # 标尺 Δ仪 / mm (最小分度1mm, 估读至0.5mm)

# ═══════════════════════════════════════════════════════════
# 16 个测点位置 (教材表3-20-2)
# ═══════════════════════════════════════════════════════════
X_POSITIONS_MM = [0, 20, 40, 60, 80, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200]

# ═══════════════════════════════════════════════════════════
# _create_template — 生成数据模板
# ═══════════════════════════════════════════════════════════
# （方式三：_create_template 已移除，数据真相为 data.json）


# ═══════════════════════════════════════════════════════════
# _plot_dm_x — 绘制 dm-x 分布曲线
# ═══════════════════════════════════════════════════════════
def _plot_dm_x(x_mm: list, dm_cm: list, output_path: str):
    """用 matplotlib 绘制 dm-x 分布曲线。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=200)
    ax.plot(x_mm, dm_cm, "o-", color="#2c5f9e", markersize=6, linewidth=1.5,
            markerfacecolor="white", markeredgewidth=1.5)
    ax.set_xlabel("x / mm", fontsize=11)
    ax.set_ylabel("dm / cm", fontsize=11)
    ax.set_title("螺线管轴线上 dm-x 分布曲线", fontsize=12)
    ax.grid(True, linestyle="--", linewidth=0.5, color="#cccccc")
    ax.set_xlim(-5, 205)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200)
    plt.close(fig)


# ═══════════════════════════════════════════════════════════
# _generate_docx — 读取 → 计算 → 输出 docx
# ═══════════════════════════════════════════════════════════
def _generate_docx(data: dict, output_path: str):
    # ── 1. 读取数据（data.json）──
    # 校验必填数据（required 字段为 null 或 array 含 null → 缺失）
    missing = []
    for k in ("M_mH", "N", "l_m", "r0_m", "n_coil", "S_m2", "I_A", "R_ohm",
              "I0_ma", "dm1_cm", "dm2_cm", "x_mm", "d_left_cm", "d_right_cm"):
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

    # 已知参数
    M_mH = float(data["M_mH"])
    N = float(data["N"])
    l_m = float(data["l_m"])
    r0_m = float(data["r0_m"])
    n_coil = float(data["n_coil"])
    S_m2 = float(data["S_m2"])
    I_A = float(data["I_A"])
    R_ohm = float(data["R_ohm"])

    # 表1: RKb 标定数据（3 组）
    i0_ma_list = [float(v) for v in data["I0_ma"]]
    dm1_cm_list = [float(v) for v in data["dm1_cm"]]
    dm2_cm_list = [float(v) for v in data["dm2_cm"]]

    # 表2: B 测量数据（16 个点）
    x_mm = [float(v) for v in data["x_mm"]]
    dleft_cm = [float(v) for v in data["d_left_cm"]]
    dright_cm = [float(v) for v in data["d_right_cm"]]

    # ── 类型转换 ──
    M_H = M_mH / 1000.0                     # mH → H

    # ═══════════════════════════════════
    # 2. RKb 标定计算
    # ═══════════════════════════════════
    dm_bar_cm_list = []
    dm_bar_mm_list = []
    rkb_list = []

    for i in range(3):
        I0_A = i0_ma_list[i] / 1000.0
        dm_cm = (dm1_cm_list[i] + dm2_cm_list[i]) / 2.0
        dm_mm = dm_cm * 10.0  # cm → mm（关键转换）
        rkb = M_H * I0_A / dm_mm  # C·Ω/mm
        dm_bar_cm_list.append(dm_cm)
        dm_bar_mm_list.append(dm_mm)
        rkb_list.append(rkb)

    RKb_mean = mean(rkb_list)

    print(f"M = {M_mH} mH = {M_H:.3e} H")
    print(f"N = {N:.0f}, l = {l_m} m, r0 = {r0_m} m")
    print(f"n = {n_coil:.0f}, S = {S_m2:.2e} m^2, I = {I_A} A")
    print()
    for i in range(3):
        print(f"  Group {i+1}: I0={i0_ma_list[i]:.0f}mA, dm1={dm1_cm_list[i]:.2f}cm, "
              f"dm2={dm2_cm_list[i]:.2f}cm, dm_bar={dm_bar_cm_list[i]:.2f}cm, "
              f"RKb={rkb_list[i]:.4e}")
    print(f"  RKb mean = {RKb_mean:.4e}")

    # ═══════════════════════════════════
    # 3. dm 及 B 计算（16 个测点）
    # ═══════════════════════════════════
    dm_cm_all = []
    dm_mm_all = []
    B_exp_all = []

    for i in range(16):
        dm_cm = (dleft_cm[i] + dright_cm[i]) / 2.0
        dm_mm = dm_cm * 10.0
        B_exp = RKb_mean * dm_mm / (n_coil * S_m2)
        dm_cm_all.append(dm_cm)
        dm_mm_all.append(dm_mm)
        B_exp_all.append(B_exp)

    # 中心点 (x=0, i=0)
    dm_cm_center = dm_cm_all[0]
    dm_mm_center = dm_mm_all[0]
    B_exp_center = B_exp_all[0]

    # 理论值
    B0_theory = MU0 * N * I_A / math.sqrt(l_m**2 + 4 * r0_m**2)

    # 相对误差
    E_rel = abs(B0_theory - B_exp_center) / B0_theory * 100.0

    print(f"\n  中心点 (x=0): dm={dm_cm_center:.2f}cm, B_exp={B_exp_center:.4e} T")
    print(f"  B0 理论值 = {B0_theory:.4e} T")
    print(f"  相对误差 E = {E_rel:.2f}%")

    # ═══════════════════════════════════
    # 4. 不确定度评定
    # ═══════════════════════════════════
    # 4a. RKb A 类
    u_A_RKb = type_a(rkb_list)

    # 4b. RKb B 类 — 对每组用 propagate_numeric
    # dm 单次读数 B 类（标尺 Δ仪=0.5mm, 均匀分布）
    u_dm_single_mm = type_b(DELTA_SCALE_MM, "uniform")

    # I0 单次读数 B 类（电流表 Δ仪=1.0mA, 均匀分布）
    u_I0_single_A = type_b(DELTA_AMMETER_A, "uniform")

    def _calc_RKb_single(I0_A, dm1_cm, dm2_cm):
        dm_cm = (dm1_cm + dm2_cm) / 2.0
        dm_mm = dm_cm * 10.0
        return M_H * I0_A / dm_mm

    u_RKb_b_list = []
    for i in range(3):
        I0_A_i = i0_ma_list[i] / 1000.0
        # d̄m = (dm1+dm2)/2, 两次独立标尺读数
        # u(d̄m) = u_single / √2
        u_dm_bar_mm = u_dm_single_mm / math.sqrt(2.0)
        # 但 propagate_numeric 需要传入 dm1_cm, dm2_cm 分别的不确定度
        # 对于 d̄m(cm) = (dm1(cm) + dm2(cm)) / 2
        # u(dm_cm) = type_b(0.05cm) / √2  (0.05cm = 0.5mm)
        u_dm_cm = type_b(0.05, "uniform") / math.sqrt(2.0)

        _, u_i = propagate_numeric(_calc_RKb_single, {
            "I0_A": (I0_A_i, u_I0_single_A),
            "dm1_cm": (dm1_cm_list[i], u_dm_cm),
            "dm2_cm": (dm2_cm_list[i], u_dm_cm),
        })
        u_RKb_b_list.append(u_i)

    # B 类平均（3组 RMS ÷ √3）
    u_B_RKb = combine(*u_RKb_b_list) / math.sqrt(3.0)

    # 合成 RKb 不确定度
    u_RKb = combine(u_A_RKb, u_B_RKb)

    print(f"\n  RKb uncertainty: u_A={u_A_RKb:.3e}, u_B={u_B_RKb:.3e}, u={u_RKb:.3e}")

    # 4c. B(x=0) 不确定度
    u_dm_center_cm = u_dm_cm  # same as for RKb d̄m

    def _calc_B(RKb_val, dm_cm_val):
        return RKb_val * (dm_cm_val * 10.0) / (n_coil * S_m2)

    B_center, u_B_center = propagate_numeric(_calc_B, {
        "RKb_val": (RKb_mean, u_RKb),
        "dm_cm_val": (dm_cm_center, u_dm_center_cm),
    })

    print(f"  B(x=0) = ({format_number(B_center, u_B_center)}) T")

    # ═══════════════════════════════════
    # 5. 绘制 dm-x 曲线
    # ═══════════════════════════════════
    plot_path = os.path.join(SCRIPT_DIR, "dm-x分布曲线.png")
    _plot_dm_x(x_mm, dm_cm_all, plot_path)
    print(f"\n  dm-x 曲线已保存: {plot_path}")

    # ═══════════════════════════════════
    # 6. 生成 docx 报告
    # ═══════════════════════════════════
    doc = DocxReportWriter(output_path)

    # ── 零、标题 ──
    doc.add_title("直螺线管磁场分布的测量")
    doc.add_student_info()

    # ── 一、原始数据记录 ──
    doc.add_heading("一、原始数据记录", level=1)
    doc.add_paragraph("请在下方粘贴原始数据记录照片。")
    doc.add_paragraph("（包括：实验电路接线图、标尺读数记录等）")

    # ── 二、数据处理 ──
    doc.add_heading("二、数据处理", level=1)

    # 2.1 已知参数
    doc.add_heading("1. 已知参数", level=2)
    param_rows = [
        ["互感系数 M",            f"{M_mH} mH"],
        ["螺线管总匝数 N",        f"{N:.0f}"],
        ["螺线管长度 l",            f"{l_m} m"],
        ["螺线管半径 r₀",     f"{r0_m} m"],
        ["探测线圈匝数 n",        f"{n_coil:.0f}"],
        ["探测线圈截面积 S",      f"${format_scientific(S_m2, 3)}$ m²"],
        ["工作电流 I",             f"{I_A} A"],
        ["回路总电阻 R",           f"{R_ohm} Ω"],
    ]
    doc.add_table(["参数", "数值"], [[str(a), str(b)] for a, b in param_rows],
                  col_widths=[6.5, 5.5])

    # 2.2 RKb 标定
    doc.add_heading("2. RKb 标定（冲击常数测量）", level=2)

    doc.add_paragraph("用互感器校正冲击电流计。互感器初级电流 I₀ 突变 ΔI₀ 时，"
                       "次级感应电量 Q = MI₀，光标偏转 dm，则：")

    doc.add_math(r"RK_b = \frac{M I_0}{\bar{d}_m}")
    doc.add_paragraph_rich(r"式中 M 为互感系数，I₀ 为初级电流，$\bar{d}_m$ = (dm₁ + dm₂) / 2 为两次偏转平均值。")

    # RKb 数据表
    rkb_headers = ["序号", "$I_0$ / mA", "$d_{m1}$ / cm", "$d_{m2}$ / cm", "$\\bar{d}_m$ / cm", "$RKb$ / (C·Ω/mm)"]
    rkb_rows = []
    for i in range(3):
        rkb_rows.append([
            str(i + 1),
            f"{i0_ma_list[i]:.0f}",
            f"{dm1_cm_list[i]:.2f}",
            f"{dm2_cm_list[i]:.2f}",
            f"{dm_bar_cm_list[i]:.2f}",
            f"${format_scientific(rkb_list[i], 3)}$",
        ])
    rkb_rows.append(["均值", "", "", "", "", f"${format_scientific(RKb_mean, 3)}$"])
    doc.add_table(rkb_headers, rkb_rows, col_widths=[1.2, 2.0, 2.2, 2.2, 2.2, 4.0])

    # 示例计算（第1组）
    doc.add_paragraph("以第 1 组数据为例：")
    doc.add_math(
        rf"\bar{{d}}_m = \frac{{{dm1_cm_list[0]:.2f} + {dm2_cm_list[0]:.2f}}}{{2}}"
        rf" = {dm_bar_cm_list[0]:.2f} \,\mathrm{{cm}}"
    )
    doc.add_math(
        rf"RK_b = \frac{{{format_scientific(M_H, 3)} \times {i0_ma_list[0]/1000:.3f}}}"
        rf"{{{dm_bar_mm_list[0]:.1f}}}"
        rf" = {format_scientific(rkb_list[0], 3)} \,\mathrm{{C\cdot\Omega/mm}}"
    )

    doc.add_paragraph("三组 RKb 的平均值：")
    doc.add_math(
        rf"\overline{{RK_b}} = {format_scientific(RKb_mean, 3)} \,\mathrm{{C\cdot\Omega/mm}}"
    )

    # RKb 不确定度
    doc.add_paragraph("RKb 的不确定度评定：")
    doc.add_paragraph("A 类不确定度（3 次测量）：")
    doc.add_math(rf"u_{{\mathrm{{A}}}}(RK_b) = {format_scientific(u_A_RKb, 3)} \,\mathrm{{C\cdot\Omega/mm}}")
    doc.add_paragraph("B 类不确定度（标尺 Δ仪 = 0.5 mm + 电流表 Δ仪 = 1.0 mA）：")
    doc.add_math(rf"u_{{\mathrm{{B}}}}(RK_b) = {format_scientific(u_B_RKb, 3)} \,\mathrm{{C\cdot\Omega/mm}}")
    doc.add_paragraph("合成不确定度：")
    doc.add_math(rf"u(RK_b) = \sqrt{{u_{{\mathrm{{A}}}}^2 + u_{{\mathrm{{B}}}}^2}} = {format_scientific(u_RKb, 3)} \,\mathrm{{C\cdot\Omega/mm}}")

    # 2.3 磁场分布测量
    doc.add_heading("3. 磁场分布测量", level=2)

    doc.add_paragraph("保持工作电流 I 不变，探测线圈沿螺线管轴线从中心 (x=0) "
                       "向一端移动，每 10~20 mm 测一个点，共 16 个位置。"
                       "每个位置记录 S₁ 闭合和断开时的光标偏转 dm₁ 和 dm₂。")
    doc.add_paragraph("dₘ = (d左 + d右) / 2，结果如下：")

    # dm 数据表 — 拆分为两个子表（各 8 列，适应 A4 宽度）
    half = 8
    for sub_idx, (start, end) in enumerate([(0, half), (half, 16)]):
        sub_x = x_mm[start:end]
        sub_dm = dm_cm_all[start:end]
        label = "（前半段）" if sub_idx == 0 else "（后半段）"
        headers = ["$x$ / mm"] + [f"{v:.0f}" for v in sub_x]
        rows = [
            ["dₘ/cm"] + [f"{v:.2f}" for v in sub_dm],
        ]
        doc.add_table(headers, rows, col_widths=[2.5] + [1.5] * half)

    # B 数据表 — 同样拆分为两个
    doc.add_paragraph("由 dm 计算各点磁感应强度 B = RKb·dm / (nS)：")
    for sub_idx, (start, end) in enumerate([(0, half), (half, 16)]):
        sub_x = x_mm[start:end]
        sub_B = B_exp_all[start:end]
        headers = ["$x$ / mm"] + [f"{v:.0f}" for v in sub_x]
        rows = [
            ["B / (10⁻³ T)"] + [f"{v*1e3:.4f}" for v in sub_B],
        ]
        doc.add_table(headers, rows, col_widths=[2.5] + [1.5] * half)

    # 2.4 dm-x 分布曲线
    doc.add_heading("4. dₘ-x 分布曲线", level=2)
    doc.add_paragraph("螺线管轴线上 dₘ 随位置 x 的变化曲线如下。曲线呈中间平坦、"
                       "两端下降的特征，与长直螺线管内部磁场均匀、端口磁场减半的理论一致。")
    doc.add_image(plot_path, width_cm=14)
    doc.add_paragraph("图1 螺线管轴线上 dₘ-x 分布曲线")

    # 2.5 中心点磁感应强度
    doc.add_heading("5. 中心点磁感应强度", level=2)

    doc.add_paragraph("螺线管中心点 (x=0) 的理论磁感应强度：")
    doc.add_math(
        rf"B_0 = \frac{{\mu_0 N I}}{{\sqrt{{l^2 + 4r_0^2}}}}"
        rf" = \frac{{4\pi \times 10^{{-7}} \times {N:.0f} \times {I_A:.2f}}}"
        rf"{{\sqrt{{{l_m}^2 + 4 \times {r0_m}^2}}}}"
        rf" = {format_scientific(B0_theory, 3)} \,\mathrm{{T}}"
    )

    doc.add_paragraph("中心点实验值：")
    doc.add_math(
        rf"B = \frac{{\overline{{RK_b}}}}{{nS}} d_m"
        rf" = \frac{{{format_scientific(RKb_mean, 3)}}}{{{n_coil:.0f} \times {format_scientific(S_m2, 3)}}}"
        rf" \times {dm_mm_center:.1f}"
        rf" = {format_scientific(B_exp_center, 3)} \,\mathrm{{T}}"
    )

    doc.add_paragraph("相对误差：")
    doc.add_math(
        rf"E = \left|\frac{{B_0 - B}}{{B_0}}\right| \times 100\%"
        rf" = \left|\frac{{{format_scientific(B0_theory, 3)} - {format_scientific(B_exp_center, 3)}}}"
        rf"{{{format_scientific(B0_theory, 3)}}}\right| \times 100\%"
        rf" = {format_percent(E_rel)}\%"
    )

    # 2.6 不确定度分析
    doc.add_heading("6. 不确定度分析", level=2)

    doc.add_paragraph("中心点磁感应强度 B 的不确定度由 RKb 的不确定度和 dm 的不确定度传递：")
    doc.add_paragraph("B 类不确定度来源 — 标尺：Δ仪 = 0.5 mm（均匀分布），"
                       "电流表：Δ仪 = 1.0 mA（均匀分布）。")
    doc.add_paragraph("经传递计算，中心点 B 的合成不确定度为：")

    doc.add_math(
        rf"u(B) = {format_scientific(u_B_center, 3)} \,\mathrm{{T}}"
    )

    # 最终结果
    doc.add_paragraph("中心点磁感应强度的最终测量结果：")
    B_fmt = format_number(B_center, u_B_center)
    doc.add_math(rf"B = ({B_fmt}) \,\mathrm{{T}}")

    # 结果对比表
    doc.add_paragraph("")
    cmp_headers = ["", "理论值 / T", "实验值 / T", "相对误差"]
    cmp_rows = [
        ["B (x=0)", f"${format_scientific(B0_theory, 3)}$", f"${format_scientific(B_exp_center, 3)}$", f"{E_rel:.1f}%"],
    ]
    doc.add_table(cmp_headers, cmp_rows, col_widths=[3.5, 3.5, 3.5, 3.5])

    # ── 三、课后思考题 ──
    doc.add_heading("三、课后思考题", level=1)

    doc.add_heading("1. 实验中，对探测线圈有何要求？依据是什么？", level=2)
    doc.add_paragraph("要求：① 线圈的匝数要适当，匝数过少则感应信号太弱，"
                       "匝数过多则线圈尺寸增大，影响空间分辨率；"
                       "② 线圈的尺寸要足够小，以准确探测局部的磁感应强度；"
                       "③ 线圈的位置和方向要精确，确保线圈轴线与螺线管轴线重合。")
    doc.add_paragraph("依据：法拉第电磁感应定律，探测线圈中的感应电动势与穿过线圈的"
                       "磁通量变化率成正比。线圈的几何形状和匝数决定了其能感应到的磁场变化量，"
                       "因此需要根据实验需求选择适当的线圈参数。")

    doc.add_heading("2. 为什么测量磁场的磁感应强度时，互感器的次级线圈仍要接入测量回路？", level=2)
    doc.add_paragraph("互感器次级线圈仍接入测量回路，是为了保持冲击电流计回路的总电阻不变。"
                       "标定 RKb 时，互感器次级已接入回路；若测量 B 时将其断开，回路总电阻改变，"
                       "冲击常数 Kb 也随之改变（Kb 与回路总电阻有关），导致标定结果失效。"
                       "保持次级线圈接入确保了标定和测量在相同回路条件下进行。")

    doc.add_heading("3. 冲击电流计与灵敏电流计的主要区别是什么？", level=2)
    doc.add_paragraph_rich("① 测量对象不同：冲击电流计测量短时间内脉冲电流所迁移的电量 Q（"
                       "读取第一次最大偏转距离 dm）；灵敏电流计测量稳定电流的大小（读取稳定偏转距离 d）。"
                       "② 结构不同：冲击电流计的线圈扁而宽，或配有惯性圆盘，转动惯量 J 大，"
                       "自由振动周期 T₀ 达十几秒以上；灵敏电流计 T₀ 通常仅 1~2 秒。"
                       r"③ 使用条件不同：冲击电流计要求电流脉冲持续时间 $\tau \ll T_0$，"
                       "以保证电量全部通过后线圈才开始偏转。")

    doc.save()
    doc.close()
    print(f"报告已生成: {output_path}")


# ═══════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════
def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "直螺线管磁场分布的测量实验.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    _generate_docx(data, DOCX_FILE)


if __name__ == "__main__":
    main()
