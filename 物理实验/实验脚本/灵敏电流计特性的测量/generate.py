"""灵敏电流计特性测量实验 — 数据处理脚本。"""

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
# 物理常数（AC15/4 型直流复射式检流计）
# ============================================================
RS = 0.100        # 标准电阻 / Ω


# ============================================================
# Excel 模板
# ============================================================

# （方式三：_create_template 已移除，数据真相为 data.json）


# ============================================================
# 计算
# ============================================================

def _compute(data: dict) -> dict:
    """从 data.json 数据计算全部结果（R-U 回归 → Rg、Ki 与临界阻尼对比）。"""
    Rs = float(data["rs"])
    Rg_th = float(data["rg_th"])
    Ki_th = float(data["ki_th"])
    Rc_th = float(data["rc_th"])
    rc_exp_val = data.get("rc_exp")   # 选填
    Rc_exp = float(rc_exp_val) if rc_exp_val is not None else None
    R1 = float(data["r1"])
    d_mm = float(data["d"])
    U = [float(v) for v in data["U"]]
    R = [float(v) for v in data["R"]]

    # 线性回归
    # 教材 (3-17-10): R = (Rs/(Ki·R1·d))·U - Rg  →  R = k·U + b
    # 以 U 为自变量 X，R 为因变量 Y
    reg = linear_regression(U, R)
    k = reg.slope           # Ω/V  (ΔR/ΔU)
    b = reg.intercept       # Ω
    Rg_meas = -b            # Ω  (b = -Rg)
    Ki_meas = Rs / (k * R1 * d_mm)   # A/mm

    # 不确定度
    u_k = reg.slope_uncertainty
    u_b = reg.intercept_uncertainty
    u_Rg = u_b
    u_Ki = Ki_meas * u_k / abs(k)

    # 相对误差
    delta_Ki = abs(Ki_meas / Ki_th - 1.0) * 100.0
    delta_Rg = abs(Rg_meas / Rg_th - 1.0) * 100.0
    delta_Rc = abs(Rc_exp / Rc_th - 1.0) * 100.0 if Rc_exp is not None else None

    return {
        "Rs": Rs, "R1": R1, "d": d_mm, "n": len(U),
        "U": U, "R": R,
        "k": k, "b": b, "r_squared": reg.r_squared,
        "u_k": u_k, "u_b": u_b,
        "Rg": Rg_meas, "u_Rg": u_Rg, "Rg_th": Rg_th, "delta_Rg": delta_Rg,
        "Ki": Ki_meas, "u_Ki": u_Ki, "Ki_th": Ki_th, "delta_Ki": delta_Ki,
        # Ki 尾数键：数值以 10⁻⁹ A/mm 为单位，供变体文本配 \times 10^{-9} 使用
        "Ki_ns": Ki_meas * 1e9, "u_Ki_ns": u_Ki * 1e9, "Ki_th_ns": Ki_th * 1e9,
        "Rc_th": Rc_th, "Rc_exp": Rc_exp, "delta_Rc": delta_Rc,
    }


# ============================================================
# docx 报告生成
# ============================================================

def _generate_docx(data: dict, output_path: str):
    """读取 data.json 数据 → 计算 → 输出 docx 报告。"""

    # ---------- 1. 空值校验（必填项为 null → 缺失；rc_exp 选填不校验） ----------
    missing = []
    for k in ("rs", "rg_th", "ki_th", "rc_th", "r1", "d"):
        if data.get(k) is None:
            missing.append(k)
    for k in ("R", "U"):
        v = data.get(k)
        if v is None or any(x is None for x in v):
            missing.append(k)
    if missing:
        print("以下必填数据未填写，请补齐后重新运行：")
        for m in missing:
            print(f"  - {m}")
        return

    # ---------- 2. 合理性校验 ----------
    if float(data["d"]) <= 0:
        print(f"[ERROR] d = {data['d']} mm <= 0，请检查后重新运行。")
        return
    if float(data["r1"]) <= 0:
        print(f"[WARNING] R1 = {data['r1']} Ω <= 0，请检查。")

    # ---------- 3. 计算 ----------
    r = _compute(data)
    variants = compose(SCRIPT_DIR, r)

    Rs = r["Rs"]
    R1 = r["R1"]
    d_mm = r["d"]
    U = r["U"]
    R = r["R"]
    k = r["k"]
    b = r["b"]
    r_squared = r["r_squared"]
    u_k = r["u_k"]
    u_b = r["u_b"]
    Rg_meas = r["Rg"]
    u_Rg = r["u_Rg"]
    Ki_meas = r["Ki"]
    u_Ki = r["u_Ki"]
    Rg_th = r["Rg_th"]
    Ki_th = r["Ki_th"]
    Rc_th = r["Rc_th"]
    Rc_exp = r["Rc_exp"]
    delta_Ki = r["delta_Ki"]
    delta_Rg = r["delta_Rg"]
    delta_Rc = r["delta_Rc"]

    # ---------- 5. 格式化 ----------
    k_disp = f"{k:.1f}"
    b_disp = f"{b:.1f}"
    u_k_disp = f"{u_k:.1f}"
    u_b_disp = f"{u_b:.1f}"
    Rg_disp = f"{Rg_meas:.1f}"
    u_Rg_disp = f"{u_Rg:.1f}"
    Ki_disp = format_scientific(Ki_meas, sig_figs=3)
    u_Ki_disp = format_scientific(u_Ki, sig_figs=1)
    Ki_th_disp = format_scientific(Ki_th, sig_figs=2)
    delta_Ki_disp = format_percent(delta_Ki)
    delta_Rg_disp = format_percent(delta_Rg)

    # 控制台输出
    print(f"\n{'=' * 55}")
    print("灵敏电流计特性测量 — 计算结果")
    print(f"{'=' * 55}")
    print(f"斜率       k  = {k_disp} ± {u_k_disp} Ω/V")
    print(f"截距       b  = {b_disp} ± {u_b_disp} Ω")
    print(f"相关系数   R^2 = {r_squared:.4f}")
    print(f"内阻       Rg = {Rg_disp} ± {u_Rg_disp} Ω")
    print(f"            (理论值 {Rg_th:.0f} Ω, Δ = {delta_Rg_disp}%)")
    print(f"电流常数   Ki = {Ki_disp} ± {u_Ki_disp} A/mm")
    print(f"            (理论值 {Ki_th_disp} A/mm, Δ = {delta_Ki_disp}%)")
    if Rc_exp is not None:
        delta_Rc_disp = format_percent(delta_Rc)
        print(f"外临界电阻 Rc = {Rc_exp:.1f} Ω (理论值 {Rc_th:.0f} Ω, Δ = {delta_Rc_disp}%)")
    print(f"{'=' * 55}\n")

    # ---------- 6. 生成 docx ----------
    doc = DocxReportWriter(output_path)

    # ---- 零、实验标题 ----
    doc.add_title("灵敏电流计特性的测量")
    doc.add_student_info()

    # ---- 变体章节：实验原理 / 实验方法（置于原始数据之前） ----
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

    # 参数汇总
    params_rows = [
        ["标准电阻 Rs", f"{Rs:.3f} Ω"],
        ["R₁", f"{R1:.0f} Ω"],
        ["偏转距离 d", f"{d_mm:.1f} mm"],
    ]
    if Rc_exp is not None:
        params_rows.append(["外临界电阻 Rc（实验值）", f"{Rc_exp:.1f} Ω"])
    doc.add_table(
        headers=["参数", "实验设定值"],
        rows=params_rows,
        col_widths=[6.5, 5.5],
    )

    # R-U 数据表
    doc.add_paragraph("")
    doc.add_run("等偏转法测得的 R-U 数据如下（偏转距离 d 保持 ")
    doc.add_inline_math(rf"{d_mm:.1f}\ \mathrm{{mm}}")
    doc.add_run(" 不变）：")
    doc.add_table(
        headers=["序号"] + [str(i) for i in range(1, 11)],
        rows=[
            ["R / Ω"] + [f"{v:.1f}" for v in R],
            ["U / V"] + [f"{v:.3f}" for v in U],
        ],
        col_widths=[2.0] + [1.2] * 10,
    )

    # 公式与回归
    doc.add_paragraph("由教材公式（3-17-10）：")
    doc.add_math(r"R = \frac{R_s}{K_i R_1 d} U - R_g")
    doc.add_paragraph("")
    doc.add_run("令 ")
    doc.add_inline_math(r"k = \frac{R_s}{K_i R_1 d}")
    doc.add_run("，")
    doc.add_inline_math(r"b = -R_g")
    doc.add_run("，则 ")
    doc.add_inline_math(r"R = kU + b")
    doc.add_run("。对表中数据作最小二乘法线性回归：")

    # R-U 曲线占位
    doc.add_paragraph("R-U 曲线图如下所示：")
    doc.add_paragraph("（请在此处粘贴 R-U 曲线图照片。）")

    # 回归结果
    doc.add_paragraph("回归结果：")
    doc.add_math(
        rf"k = {k_disp}\ \mathrm{{\Omega/V}},\quad "
        rf"u(k) = {u_k_disp}\ \mathrm{{\Omega/V}}"
    )
    doc.add_math(
        rf"b = {b_disp}\ \mathrm{{\Omega}},\quad "
        rf"u(b) = {u_b_disp}\ \mathrm{{\Omega}}"
    )
    doc.add_paragraph("")
    doc.add_run("相关系数 ")
    doc.add_inline_math(f"r^{{2}} = {r_squared:.4f}")
    doc.add_run("，线性关系良好。")

    # 求 Ki
    doc.add_paragraph("由斜率求电流常数：")
    doc.add_math(
        rf"K_i = \frac{{R_s}}{{k R_1 d}} = "
        rf"\frac{{{Rs:.3f}}}{{{k_disp} \times {R1:.0f} \times {d_mm:.1f}}}"
        rf" \approx {Ki_disp}\ \mathrm{{A/mm}}"
    )
    doc.add_paragraph("")
    doc.add_run("不确定度：")
    doc.add_inline_math(rf"u(K_i) = {u_Ki_disp}\ \mathrm{{A/mm}}")

    # 求 Rg
    doc.add_paragraph("由截距求内阻：")
    doc.add_math(
        rf"R_g = -b = -({b_disp}) = {Rg_disp}\ \mathrm{{\Omega}}"
    )
    doc.add_paragraph("")
    doc.add_run("不确定度：")
    doc.add_inline_math(rf"u(R_g) = {u_Rg_disp}\ \mathrm{{\Omega}}")

    # 相对误差公式
    doc.add_paragraph("相对误差（分母为正值，绝对值仅作用于分子，避免公式渲染异常）：")
    doc.add_paragraph("")
    doc.add_run("电流常数：")
    doc.add_inline_math(
        rf"E_{{K_i}} = \frac{{|K_i - K_{{i,\text{{理论}}}}|}}"
        rf"{{K_{{i,\text{{理论}}}}}} \times 100\% \approx {delta_Ki_disp}\%"
    )
    doc.add_paragraph("")
    doc.add_run("内阻：")
    doc.add_inline_math(
        rf"E_{{R_g}} = \frac{{|R_g - R_{{g,\text{{理论}}}}|}}"
        rf"{{R_{{g,\text{{理论}}}}}} \times 100\% \approx {delta_Rg_disp}\%"
    )
    if Rc_exp is not None:
        delta_Rc_disp_f = f"{delta_Rc:.1f}"
        doc.add_paragraph("")
        doc.add_run("外临界电阻：")
        doc.add_inline_math(
            rf"E_{{R_c}} = \frac{{|R_c - R_{{c,\text{{理论}}}}|}}"
            rf"{{R_{{c,\text{{理论}}}}}} \times 100\% \approx {delta_Rc_disp_f}\%"
        )

    # 对比表
    doc.add_paragraph("实验值与铭牌理论值对比如下：")
    comp_rows = [
        ["电流常数 Ki", f"${Ki_th_disp}$ A/mm", f"${Ki_disp}$ A/mm", f"{delta_Ki_disp}%"],
        ["内阻 Rg", f"{Rg_th:.0f} Ω", f"{Rg_disp} Ω", f"{delta_Rg_disp}%"],
    ]
    if Rc_exp is not None:
        delta_Rc_disp = format_percent(delta_Rc)
        comp_rows.append([
            "外临界电阻 Rc",
            f"{Rc_th:.0f} Ω",
            f"{Rc_exp:.1f} Ω",
            f"{delta_Rc_disp}%",
        ])
    doc.add_table(
        headers=["参数", "理论值", "实验值", "相对误差"],
        rows=comp_rows,
        col_widths=[3.5, 3.5, 3.5, 2.5],
    )

    # ---- 三、实验结果分析 ----
    doc.add_heading("三、实验结果分析", level=1)

    doc.add_heading("（一）实验误差来源", level=2)

    doc.add_heading("1. 仪器固有误差", level=2)
    doc.add_paragraph("悬丝与磁场不均匀性：悬丝的弹性系数并非完全均匀，或永磁体磁隙中的磁场并非理想均匀辐射状分布，导致偏转角度与电流之间存在微弱的非线性关系，影响定偏法测量的精度。")
    doc.add_paragraph("标尺刻度精度：灵敏电流计标尺的最小分度值较大（通常为 1 mm），在微小偏转或光标晃动时难以精确读数，引入估读误差。")

    doc.add_heading("2. 人为操作误差", level=2)
    doc.add_paragraph("读数视差：观察标尺上光标位置时，视线若未与标尺平面保持垂直，会因视角倾斜导致读数偏差。此外，反射镜与标尺若未严格平行，也会引入系统误差。")

    doc.add_heading("3. 环境干扰", level=2)
    doc.add_paragraph("振动干扰：实验台面的微小振动会通过悬丝传递至线圈，导致光标在平衡位置附近持续晃动，影响偏转距离 d 的稳定读取。")
    doc.add_paragraph("温度变化：悬丝（磷青铜）的弹性模量随温度变化，温度波动会影响电流计的灵敏度；同时线圈的铜电阻也随温度变化，影响回路阻尼特性的稳定性。")

    doc.add_heading("4. 电路与电源误差", level=2)
    doc.add_paragraph("")
    doc.add_run("接触电阻：导线与接线柱之间的接触电阻（通常 ")
    doc.add_inline_math(r"0.1 \sim 0.5\ \mathrm{\Omega}")
    doc.add_run("）与电路中的标准电阻 Rs（0.100 Ω）量级接近，不可忽略，会直接影响分压比和最终的 Ki、Rg 计算结果。")
    doc.add_paragraph("电阻箱精度：电阻箱 R 和 R₁ 各档位的实际阻值与标称值存在偏差，尤其在小阻值档位（×1、×0.1），相对误差较大，影响回路总电阻的准确度。")

    doc.add_heading("（二）改进措施", level=2)

    doc.add_heading("1. 优化仪器与读数方法", level=2)
    doc.add_paragraph("定期校准仪器：用标准微电流源校准灵敏电流计的电流常数，建立偏转-电流标定曲线，修正悬丝非线性误差。")
    doc.add_paragraph("")
    doc.add_run("高精度电阻箱：选用步进值")
    doc.add_inline_math(r"\leq 0.1\ \mathrm{\Omega}")
    doc.add_run("的电阻箱，精确调节临界阻尼外阻，减小电阻箱的系统误差贡献。")

    doc.add_heading("2. 控制实验环境", level=2)
    doc.add_paragraph("防震与恒温：在防震实验台上进行测量，实验室温度控制在 ±1 ℃ 以内，减小环境因素对悬丝弹性和线圈电阻的影响。")
    doc.add_paragraph("多次测量取平均：对临界阻尼电阻、灵敏度等关键参数进行 5~10 次重复测量，计算标准差以降低随机误差，提高测量结果的可靠性。")
    doc.add_paragraph("数据拟合修正：通过最小二乘法拟合 R-U 关系曲线，利用全部 10 组数据的统计信息，降低单点测量误差对最终结果的影响。")

    # ---- 变体章节：误差分析 / 结论（置于结果分析之后、思考题之前） ----
    if "误差分析" in variants:
        doc.add_heading("误差分析", level=1)
        doc.add_paragraph_rich(variants["误差分析"])
    if "结论" in variants:
        doc.add_heading("结论", level=1)
        doc.add_paragraph_rich(variants["结论"])

    # ---- 四、课后思考题 ----
    doc.add_heading("四、课后思考题", level=1)

    # 题 1
    doc.add_heading("1. 内阻测量结果误差比较大，甚至个别学生测量得到的是负电阻，是何原因？", level=2)

    doc.add_paragraph("灵敏电流计内阻测量误差主要来源于温差电动势引起的零点漂移：")
    doc.add_paragraph("灵敏电流计的悬丝和接线端多使用不同金属材料（如磷青铜悬丝、黄铜接线柱），在室温变化时不同金属接点处产生温差电动势（塞贝克效应），形成微小的温差电流 ΔI。经过零点校准后，环境温度的缓慢变化会使光标再次偏离零点。当定偏法测量中 R 取值较小时，通过电流计的测量电流 I 本身也很小（约 10⁻⁹ A 量级），温差电流 ΔI 与 I 大小可比拟，叠加后严重干扰测量结果。")
    doc.add_paragraph("")
    doc.add_run("ΔI 与 I 的方向可相同或相反：当 ΔI 与 I 同向时，等效电流偏大，需在更大电压下才能达到相同偏转，导致 R-U 图的截距 b 偏负（即 |b| 偏大），Rg = −b 偏大；当 ΔI 与 I 反向且 |ΔI| 较大时，等效电流偏小甚至反向，截距 b 偏正，严重时 Rg = −b 表现为负值。")
    doc.add_paragraph("此外，定偏法要求每次调节 U 使偏转距离 d 精确保持恒定，实际操作中难以完全做到，微小的偏转变化也会引入测量误差，进一步影响回归截距的准确性。")

    # 题 2
    doc.add_heading("2. 标准电阻作为二级分压是如何保护电流计的？", level=2)

    doc.add_paragraph("")
    doc.add_run("标准电阻 Rs（0.100 Ω）在电路中起二级分压限流保护作用。第一级分压：Rs 与 R₁（约 3000 Ω）串联，根据分压公式 ")
    doc.add_inline_math(r"U_s \approx U \cdot \frac{R_s}{R_1} \approx U \times 3.3 \times 10^{-5}")
    doc.add_run("，Rs 两端获得约 10⁻⁵ 量级的微小电压（当 U = 3 V 时 Us ≈ 0.1 mV）。第二级分流：该微小电压施加在 R + Rg 回路两端，通过电流计的电流 ")
    doc.add_inline_math(r"I_g = \frac{U_s}{R + R_g}")
    doc.add_run("，再经并联分流后实际流过电流计线圈的电流降至 10⁻⁹ A 量级，恰好在 AC15/4 型灵敏电流计的额定测量范围（电流常数 ~10⁻⁹ A/mm）内，从而确保了电流计的安全运行。")
    doc.add_paragraph("此外，当电流计外部电路处于短路状态时（如 R = 0），线圈在磁场中摆动切割磁感线产生感应电流，短路形成的低阻闭合回路中感应电流产生电磁阻尼力矩，使线圈迅速停止摆动，起到对悬丝的机械保护作用。")

    # 题 3
    doc.add_heading('3. 为什么电流计在不用时，分流器必须要“短路”？', level=2)

    doc.add_paragraph("灵敏电流计的线圈由弹性极弱的磷青铜悬丝悬挂在永磁体磁隙中，悬丝兼具导电和提供恢复力矩的功能，其扭力系数极小（约 10⁻⁸ N·m/rad 量级）。当电流计不使用时，若分流器处于开路状态（即外电路断开），线圈两端无低阻闭合回路，此时：")
    doc.add_paragraph("任何外部振动、实验台轻微移动或偶然触碰都会引起线圈在磁场中摆动。线圈切割磁感线产生感应电动势，但由于外电路断开，感应电流无法流通，无法形成电磁阻尼力矩。线圈会因惯性长时间持续振荡（类似欠阻尼状态），悬丝因反复扭转产生疲劳，弹性系数逐渐改变，致使测量精度下降，严重时悬丝断裂导致仪器报废。同时，线圈长时间大幅度摆动可能撞击磁极或极靴，损坏线圈骨架和反射镜光学系统。")
    doc.add_paragraph("")
    doc.add_run('将分流器置于“短路”挡（电阻调至零）后，线圈两端通过低阻导线短接，形成闭合回路。根据楞次定律，线圈摆动时在回路中产生的感应电流，其受到的安培力方向始终与线圈运动方向相反，形成与运动速度成正比的电磁阻尼力矩。该阻尼力矩使线圈迅速停止摆动，回到平衡位置，从而有效保护悬丝和线圈免受机械损伤。因此，灵敏电流计在日常存放和搬运过程中，必须将分流器置于“短路”挡，这是保护仪器的基本操作规程。')

    # ----
    doc.save()
    doc.close()


# ============================================================
# 入口
# ============================================================

def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "灵敏电流计特性的测量实验报告.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    _generate_docx(data, DOCX_FILE)
    print(f"报告已生成: {DOCX_FILE}")


if __name__ == "__main__":
    main()
