"""单缝衍射（衍射光强分布）实验 — 数据处理脚本。

用激光（λ=650nm）照射单缝，探测器在导轨上每 1mm 记录光强 I，
计算相对光强 I/I₀、确定暗纹位置、计算缝宽 a 并与给定值比较。
"""

import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import *
from common.docx_report import DocxReportWriter
from common.data_io import load_data

# ============================================================
# 物理常数 / 实验参数（按教材）
# ============================================================

LASER_WAVELENGTH_NM = 650          # 激光波长 λ = 650 nm
LASER_WAVELENGTH_MM = 6.5e-4       # mm 单位
GIVEN_SLIT_WIDTH_MM = 0.100        # 给定缝宽 0.100 mm

# 次极大理论相对光强（来自教材：u=±1.43π, ±2.46π, ±3.47π）
THEORY_SECONDARY_MAX = [0.047, 0.016, 0.008]

# 42 个 x 位置，分为 6 个块，每块对应 x 范围和 Excel 列数
BLOCKS = [
    (0, 8, 8),     # 0~7,   8 列
    (8, 16, 8),    # 8~15,  8 列
    (16, 24, 8),   # 16~23, 8 列
    (24, 32, 8),   # 24~31, 8 列
    (32, 40, 8),   # 32~39, 8 列
    (40, 42, 2),   # 40~41, 2 列
]


# ============================================================
# Excel 模板生成
# ============================================================

# （方式三：_create_template 已移除，数据真相为 data.json）


# ============================================================
# 数据读取
# ============================================================

def _read_data(data: dict):
    """从 data.json 数据组装 (x_list, I_list, L, lambda_nm, given_a)。

    原实现为 openpyxl 遍历 数据.xlsx 的 6 个横向数据块（x 行 / I 行）与
    底部参数区（L/mm、波长、缝宽），现改为直接读取 schema 定义的 key：
    x、I、L、lambda_nm、given_a。λ/a 缺省时回退教材给定量（与原逻辑一致）。
    """
    x_all = [float(v) for v in data["x"]]
    I_all = [float(v) for v in data["I"]]
    L_val = float(data["L"])
    lambda_val = data.get("lambda_nm")
    given_a_val = data.get("given_a")
    return (x_all, I_all, L_val,
            lambda_val or LASER_WAVELENGTH_NM,
            given_a_val or GIVEN_SLIT_WIDTH_MM)


# ============================================================
# 数据处理
# ============================================================

def _quadratic_min_x(x, I, i):
    """在局部极小值 i 处做二次插值，求精确极小值 x 位置。

    通过 (x[i-1], I[i-1]), (x[i], I[i]), (x[i+1], I[i+1]) 三点拟合抛物线，
    返回抛物线顶点对应的 x。
    """
    if i <= 0 or i >= len(x) - 1:
        return x[i]
    x0, x1, x2 = x[i-1], x[i], x[i+1]
    y0, y1, y2 = I[i-1], I[i], I[i+1]

    # 抛物线 y = ax² + bx + c，顶点在 x = -b/(2a)
    # 其中 a, b 由三点差分确定
    denom = 2 * (y0 - 2 * y1 + y2)
    if abs(denom) < 1e-12:
        return x1
    offset = (y2 - y0) / denom
    # offset 单位是 dx=1mm（因为 x 间距为 1mm）
    return x1 - offset


def _find_dark_fringes(x, I, i0_idx):
    """在 I 数组中寻找暗纹位置（k=±1, ±2, ±3）。

    从中央主极大向两侧扫描，找局部极小值（I 接近 0），
    用二次插值精确定位每个暗纹的 x 坐标。
    左右各取 3 个距离中心最近的，按级次配对。

    返回 {k: (x_left, x_right)} 字典。
    """
    i0_val = I[i0_idx]
    threshold = 0.03 * i0_val  # 暗纹区域：相对光强 < 3%

    # 找所有局部极小值（I 低于阈值）
    candidates = []
    for i in range(1, len(I) - 1):
        if I[i] is None or I[i-1] is None or I[i+1] is None:
            continue
        if I[i] <= I[i-1] and I[i] <= I[i+1] and I[i] < threshold:
            # 用二次插值求精确位置
            x_precise = _quadratic_min_x(x, I, i)
            candidates.append((x_precise, I[i], i))

    # 分为左右两组
    left = [c for c in candidates if c[0] < x[i0_idx]]
    right = [c for c in candidates if c[0] > x[i0_idx]]

    # 按距中心距离排序（最近优先）
    left.sort(key=lambda c: x[i0_idx] - c[0])
    right.sort(key=lambda c: c[0] - x[i0_idx])

    # 合并相邻的极小值点（同一暗纹可能被检测为两个相邻点）
    def _merge_nearby(points, max_gap=2.0):
        """合并间距小于 max_gap 的相邻极小值点，取 I 更小的那个。"""
        if len(points) <= 1:
            return points
        merged = []
        i = 0
        while i < len(points):
            best = points[i]
            j = i + 1
            while j < len(points) and abs(points[j][0] - best[0]) < max_gap:
                if points[j][1] < best[1]:
                    best = points[j]
                j += 1
            merged.append(best)
            i = j
        return merged

    left = _merge_nearby(left)
    right = _merge_nearby(right)

    result = {}
    max_k = min(3, len(left), len(right))
    for k in range(1, max_k + 1):
        result[k] = (left[k - 1][0], right[k - 1][0])

    return result


def _find_secondary_maxima(x, I, dark_fringes, i0_idx):
    """在暗纹之间找次极大。返回 [(k, x_pos, i_rel, theory), ...] 列表。"""
    # 收集所有暗纹位置（含中心对称的边界），排序
    dark_positions = [x[i0_idx]]  # 中央主极大
    for k in sorted(dark_fringes.keys()):
        xl, xr = dark_fringes[k]
        dark_positions.append(xl)
        dark_positions.append(xr)
    dark_positions.sort()

    # 为每个暗纹找在 x 数组中的最近索引
    dark_indices = []
    for dp in dark_positions:
        # 找 x 数组中最接近 dp 的索引
        best = min(range(len(x)), key=lambda i: abs(x[i] - dp))
        dark_indices.append(best)
    # 去重排序
    dark_indices = sorted(set(dark_indices))

    results = []
    # 在每对相邻暗纹之间找局部极大值
    for order in range(1, 4):  # k=1,2,3 次极大
        # 左侧次极大：在中央主极大左边的两个暗纹之间
        # 右侧次极大：在中央主极大右边的两个暗纹之间
        pass

    # 简化方法：扫描全部数据找局部极大值（排除中央主极大），
    # 然后按距离中心排序配对
    maxima = []
    for i in range(1, len(I) - 1):
        if I[i] is None or I[i-1] is None or I[i+1] is None:
            continue
        if I[i] >= I[i-1] and I[i] >= I[i+1] and i != i0_idx:
            maxima.append((i, x[i], I[i] / I[i0_idx]))

    # 按距中心距离排序，左右各取最近的 3 个
    left_max = [(i, xp, r) for i, xp, r in maxima if xp < x[i0_idx]]
    right_max = [(i, xp, r) for i, xp, r in maxima if xp > x[i0_idx]]
    left_max.sort(key=lambda t: x[i0_idx] - t[1])
    right_max.sort(key=lambda t: t[1] - x[i0_idx])

    result = []
    max_count = min(3, len(left_max), len(right_max))
    for k in range(max_count):
        _, xl, rl = left_max[k]
        _, xr, rr = right_max[k]
        avg_r = (rl + rr) / 2
        theory = THEORY_SECONDARY_MAX[k] if k < len(THEORY_SECONDARY_MAX) else 0
        rel_err = abs(avg_r - theory) / theory * 100 if theory > 0 else 0
        result.append({
            "k": k + 1,
            "left_x": xl,
            "left_r": rl,
            "right_x": xr,
            "right_r": rr,
            "avg_r": avg_r,
            "theory": theory,
            "rel_err": rel_err,
        })

    return result


def _compute(x, I, L_mm, lambda_nm, given_a_mm):
    """完整计算链。"""
    lambda_mm = lambda_nm * 1e-6  # nm → mm

    # ---- 1. 归一化 ----
    i0_val = max(I)
    i0_idx = I.index(i0_val)
    x0 = x[i0_idx]
    I_rel = [v / i0_val for v in I]

    # ---- 2. 暗纹位置 ----
    dark_fringes = _find_dark_fringes(x, I, i0_idx)

    # ---- 3. 缝宽计算 ----
    a_results = []
    for k in sorted(dark_fringes.keys()):
        xl, xr = dark_fringes[k]
        xk = (abs(xl - x0) + abs(xr - x0)) / 2
        a_k = L_mm * k * lambda_mm / xk
        a_results.append({
            "k": k,
            "xl": xl,
            "xr": xr,
            "xk": xk,
            "a_k": a_k,
        })

    a_values = [r["a_k"] for r in a_results]
    a_mean_val = mean(a_values) if len(a_values) >= 3 else sum(a_values) / len(a_values)
    rel_err_a = abs(a_mean_val - given_a_mm) / given_a_mm * 100

    # ---- 4. 次极大分析 ----
    sec_max = _find_secondary_maxima(x, I_rel, dark_fringes, i0_idx)

    return {
        "x": x, "I": I, "I_rel": I_rel,
        "i0_val": i0_val, "i0_idx": i0_idx, "x0": x0,
        "dark_fringes": dark_fringes,
        "a_results": a_results, "a_mean": a_mean_val,
        "rel_err_a": rel_err_a, "given_a_mm": given_a_mm,
        "L_mm": L_mm, "lambda_nm": lambda_nm, "lambda_mm": lambda_mm,
        "sec_max": sec_max,
    }


# ============================================================
# docx 报告生成
# ============================================================

def _generate_docx(data: dict, output_path: str):
    """校验 → 读取 data.json 数据 → 计算 → 输出 docx 报告。"""
    # 校验必填数据（required 字段为 null 或 array 含 null → 缺失）
    missing = []
    for k in ("L", "x", "I"):
        v = data.get(k)
        if v is None:
            missing.append(k)
        elif isinstance(v, list) and any(t is None for t in v):
            missing.append(k)
    if missing:
        print("以下必填数据未填写，请补齐后重新运行：")
        for m in missing:
            print(f"  - {m}")
        return False

    parsed = _read_data(data)
    if parsed is None:
        return False
    x, I, L_mm, lambda_nm, given_a_mm = parsed
    r = _compute(x, I, L_mm, lambda_nm, given_a_mm)

    # ---------- 控制台摘要 ----------
    print(f"\n{'=' * 56}")
    print(f"  I0 = {r['i0_val']:.1f}  (at x = {r['x0']:.3f} mm)")
    print(f"  L = {L_mm:.1f} mm,  lambda = {lambda_nm} nm")
    for d in r["a_results"]:
        print(f"  k={d['k']}: x_left={d['xl']:.3f}, x_right={d['xr']:.3f}, "
              f"xk_avg={d['xk']:.3f} mm, a_{d['k']}={d['a_k']:.4f} mm")
    print(f"  a_avg = {r['a_mean']:.4f} mm,  given = {given_a_mm:.3f} mm, "
          f"rel_err = {r['rel_err_a']:.2f}%")
    print(f"  Secondary maxima:")
    for s in r["sec_max"]:
        print(f"    k={s['k']}: I/I0={s['avg_r']:.3f} (theory {s['theory']:.3f}), "
              f"rel_err={s['rel_err']:.1f}%")
    print(f"{'=' * 56}\n")

    # ---------- docx ----------
    doc = DocxReportWriter(output_path)

    # ---- 零、实验标题 ----
    doc.add_title("衍射光强分布的测量")
    doc.add_student_info()

    # ---- 一、原始数据记录 ----
    doc.add_heading("一、原始数据记录", level=1)
    doc.add_paragraph("（请在此处粘贴原始数据记录照片。）")

    # ---- 二、数据处理 ----
    doc.add_heading("二、数据处理", level=1)

    # -- 2.1 相对光强计算 --
    doc.add_heading("1. 相对光强计算", level=2)
    doc.add_paragraph("")
    doc.add_run("实验测得 42 个位置的光强数据。中央主极大光强为")
    doc.add_inline_math(f"I_{0} = {r['i0_val']:.1f}")
    doc.add_run("，位于 ")
    doc.add_inline_math(f"x = {r['x0']:.3f}\\ \\mathrm{{mm}}")
    doc.add_run(" 处。将各点光强与 I₀ 做比值，得到归一化相对光强 I/I₀。")

    # -- 2.2 光强分布曲线 --
    doc.add_heading("2. I/I₀-x 光强分布曲线", level=2)
    doc.add_paragraph(
        "根据计算结果，在坐标纸上以 x 为横轴、I/I₀ 为纵轴描点，"
        "并用平滑曲线连接，得到单缝衍射光强分布曲线。"
        "曲线关于中央主极大近似对称分布，中央主极大处光强最大，"
        "向两侧逐渐衰减，各级次极大光强依次递减。")

    # -- 2.3 次极大分析 --
    doc.add_heading("3. 次极大位置与理论比较", level=2)
    doc.add_paragraph(
        "由光强分布曲线找出各级次极大的位置和相对光强，"
        "左右两侧对称级次取平均值，与理论值进行比较。")
    doc.add_paragraph("")

    if r["sec_max"]:
        table_rows = []
        for s in r["sec_max"]:
            table_rows.append([
                f"k={s['k']}",
                f"{s['left_x']:.1f} / {s['right_x']:.1f}",
                f"{s['left_r']:.4f} / {s['right_r']:.4f}",
                f"{s['avg_r']:.4f}",
                f"{s['theory']:.3f}",
                f"{format_percent(s['rel_err'])}%",
            ])
        doc.add_table(
            headers=["级次", "$x$ / mm (左/右)", "$I/I_0$ (左/右)",
                     "平均 $I/I_0$", "理论值", "相对误差"],
            rows=table_rows,
            col_widths=[1.2, 2.5, 2.8, 2.0, 1.5, 1.5],
        )

    doc.add_paragraph(
        "由表中可见，由于实验测量精度和背景光等因素影响，"
        "次极大的实测值可能与理论值存在一定偏差。")

    # -- 2.4 单缝宽度计算 --
    doc.add_heading("4. 单缝宽度计算", level=2)
    doc.add_paragraph(
        "在夫琅禾费衍射条件下，各级暗纹满足")
    doc.add_math(r"a\sin\theta = k\lambda\quad(k=\pm1,\pm2,\pm3,\cdots)")
    doc.add_paragraph("")
    doc.add_run("由于衍射角 θ 很小，")
    doc.add_inline_math(r"\sin\theta \approx \tan\theta = \frac{x_{k}}{L}")
    doc.add_run("，因此单缝宽度为")
    doc.add_math(r"a = \frac{Lk\lambda}{x_{k}}")

    doc.add_paragraph("")
    doc.add_run("实验测得 ")
    doc.add_inline_math(f"L = {L_mm:.1f}\\ \\mathrm{{mm}}")
    doc.add_run("，")
    doc.add_inline_math(f"\\lambda = {lambda_nm}\\ \\mathrm{{nm}}")
    doc.add_run("。中央主极大位于 ")
    doc.add_inline_math(f"x_{0} = {r['x0']:.3f}\\ \\mathrm{{mm}}")
    doc.add_run("。")

    doc.add_paragraph("从光强分布曲线上确定各级暗纹位置，代入上述公式：")

    for d in r["a_results"]:
        doc.add_paragraph("")
        doc.add_run(f"对于 k = ±{d['k']} 级暗纹，")
        doc.add_inline_math(
            f"x_{{-{d['k']}}} \\approx {d['xl']:.3f}\\ \\mathrm{{mm}},"
            f"\\quad x_{{+{d['k']}}} \\approx {d['xr']:.3f}\\ \\mathrm{{mm}}")
        doc.add_run("，平均间距")
        doc.add_math(
            f"\\overline{{x}}_{{{d['k']}}} = "
            f"\\frac{{|{d['xl']:.3f} - {r['x0']:.3f}|"
            f" + |{d['xr']:.3f} - {r['x0']:.3f}|}}{{2}}"
            f" \\approx {d['xk']:.3f}\\ \\mathrm{{mm}}")
        doc.add_paragraph("")
        doc.add_run("则")
        doc.add_math(
            f"a_{{{d['k']}}} = \\frac{{{L_mm:.1f} \\times {d['k']}"
            f" \\times {lambda_nm} \\times 10^{{-6}}}}{{{d['xk']:.3f}}}"
            f" \\approx {d['a_k']:.4f}\\ \\mathrm{{mm}}")

    doc.add_paragraph("")
    doc.add_run("单缝宽度的算术平均值为")
    a_terms = " + ".join([f"a_{{{d['k']}}}" for d in r["a_results"]])
    a_n = len(r["a_results"])
    doc.add_math(
        f"\\overline{{a}} = \\frac{{{a_terms}}}{{{a_n}}}"
        f" \\approx {r['a_mean']:.4f}\\ \\mathrm{{mm}}")

    doc.add_paragraph("")
    doc.add_run("与给定值 ")
    doc.add_inline_math(f"a_{{\\mathrm{{given}}}} = {given_a_mm:.3f}\\ \\mathrm{{mm}}")
    doc.add_run(" 比较，相对误差为")
    doc.add_math(
        f"\\Delta = \\frac{{|{r['a_mean']:.4f} - {given_a_mm:.3f}|}}"
        f"{{{given_a_mm:.3f}}} \\times 100\\%"
        f" \\approx {format_percent(r['rel_err_a'])}\\%")

    doc.add_paragraph(
        "结果在合理误差范围内，实验测量较为准确。"
        "误差主要来源于：探测器定位精度、背景光影响、"
        "单缝与探测器间距 L 的测量误差、激光光斑的非理想均匀性等。")

    # ---- 三、课后思考题 ----
    doc.add_heading("三、课后思考题", level=1)

    doc.add_heading("1. 夫琅禾费衍射的条件是什么？实验中是如何满足的？", level=2)
    doc.add_paragraph("")
    doc.add_run("答：夫琅禾费衍射的条件是光源和观察屏与衍射屏的距离均为无限远，"
                "即照射到衍射屏上的入射光和离开衍射屏的衍射光都是平行光。"
                "实验中，使用半导体激光器作为光源，"
                "激光器发出的光束发散角很小，可近似为平行光直接照射在单缝上，"
                "省去了准直透镜 L₁；"
                "同时，单缝宽度 a 远小于单缝到探测器之间的距离 L（L > 80 cm），"
                "衍射光传播到探测器时可视为平行光，"
                "省去了会聚透镜 L₂。这样简化的实验装置即可满足夫琅禾费衍射条件。")

    doc.add_heading(
        "2. 如果激光器输出的单色光照射在一根头发丝上，将会产生怎样的衍射图样？",
        level=2)
    doc.add_paragraph("")
    doc.add_run("答：当激光照射在头发丝上时，会产生与单缝衍射相似的衍射图样——"
                "一组明暗相间的平行条纹。根据巴比涅原理，"
                "互补屏（单缝与相同宽度的细丝）的衍射图样相同，"
                "因此头发丝的衍射图样与相同宽度的单缝衍射图样一致："
                "中央为最亮的明条纹（主极大），"
                "两侧对称分布亮度依次递减的明暗相间条纹。"
                "通过测量暗纹间距，同样可利用公式 ")
    doc.add_inline_math(r"a = \frac{Lk\lambda}{x_{k}}")
    doc.add_run(" 计算头发丝的直径。")

    doc.save()
    doc.close()
    return True


# ============================================================
# 入口
# ============================================================

def main():
    DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
    DOCX_FILE = os.path.join(SCRIPT_DIR, "实验报告.docx")

    data = load_data(DATA_FILE)
    if not data:
        print("未找到 data.json 或数据为空，请先在应用中填写数据。")
        return

    if _generate_docx(data, DOCX_FILE):
        print(f"报告已生成: {DOCX_FILE}")


if __name__ == "__main__":
    main()
