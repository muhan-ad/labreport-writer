"""数值 → LaTeX 格式字符串。

不确定度表达遵循课程规范（教材 2-4 测量结果和不确定度的确定）：
- 不确定度 ΔY 只保留 1 位有效数字，尾数只进不舍；
- 测量值末位与 ΔY 对齐，尾数按"四舍六入五凑偶"修约；
- 相对不确定度以百分数表示，保留 1~2 位有效数字（首位非零数字
  ≥3 取 1 位，为 1 或 2 取 2 位），尾数只进不舍。
"""

import math
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_EVEN


def _first_sig_digit(x: float) -> int:
    """第一个非零数字所在的位（小数点后为正，前为负）。
    例: 0.034 → 3,  0.5 → 1,  120 → -2"""
    if x == 0:
        return 0
    return -int(math.floor(math.log10(abs(x))))


def _ceil_to_1sig(u: float) -> float:
    """不确定度取 1 位有效数字，尾数只进不舍（课程 2-4）。"""
    u = float(u)  # 兼容 numpy 浮点标量（其 repr 不是纯数字，Decimal 无法直接解析）
    if u <= 0:
        return 0.0
    exp = int(math.floor(math.log10(u)))
    d = Decimal(repr(u)).scaleb(-exp).quantize(Decimal(1), rounding=ROUND_CEILING)
    if d >= 10:
        d = Decimal(1)
        exp += 1
    return float(d.scaleb(exp))


def _round_half_even(x: float, decimals: int) -> float:
    """四舍六入五凑偶修约到指定小数位（decimals 可为负，表示修约到十/百位）。"""
    x = float(x)
    q = Decimal(1).scaleb(-decimals)
    return float(Decimal(repr(x)).quantize(q, rounding=ROUND_HALF_EVEN))


def format_percent(p: float) -> str:
    """相对不确定度百分数：首位非零数字 ≥3 保留 1 位、1/2 保留 2 位有效数字，
    尾数只进不舍（课程 2-4）。输入为百分数值，如 1.48 → '1.5'，4.12 → '5'。"""
    p = float(p)
    if p == 0:
        return "0"
    a = abs(p)
    exp = int(math.floor(math.log10(a)))
    first = min(9, int(a / 10 ** exp + 1e-9))
    keep = 2 if first in (1, 2) else 1
    decimals = max(0, keep - 1 - exp)
    d = Decimal(repr(a)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_CEILING)
    return f"{d:.{decimals}f}"


def format_number(value: float, uncertainty: float | None = None,
                   sig_figs: int | None = None) -> str:
    """数值转字符串，自动处理有效数字。

    - 有 uncertainty 时（课程 2-4 标准形式）：不确定度取 1 位有效数字（只进不舍），
      测量值末位与其对齐并按四舍六入五凑偶修约；
    - 无 uncertainty 时：保留 sig_figs 位有效数字（默认6位）。
    """
    if uncertainty is not None and uncertainty > 0:
        value = float(value)
        uncertainty = float(uncertainty)
        u_disp = _ceil_to_1sig(uncertainty)
        exp = int(math.floor(math.log10(u_disp)))
        decimals = -exp
        if value == uncertainty:
            # 惯用法 format_number(u, u)：显示不确定度本身 → 只进不舍
            v = u_disp
        else:
            v = _round_half_even(value, decimals)
        return f"{v:.{max(0, decimals)}f}"

    if sig_figs is not None:
        if value == 0:
            return "0"
        exponent = int(math.floor(math.log10(abs(value))))
        decimal_places = max(0, sig_figs - 1 - exponent)
        return f"{value:.{decimal_places}f}"

    # 默认：保留合理位数，去除多余的尾随零；
    # 超出 %.6g 显示范围会产生 e 计数法（如 1.7e-08），转为 LaTeX 科学计数法（×10ⁿ）
    s = f"{value:.6g}"
    if "e" in s or "E" in s:
        return format_scientific(value, 6)
    return s


def format_scientific(value: float, sig_figs: int = 4) -> str:
    """输出 LaTeX 科学计数法: 1.234 × 10^{-5}。"""
    if value == 0:
        return "0"
    exponent = int(math.floor(math.log10(abs(value))))
    mantissa = value / (10 ** exponent)
    s = f"{mantissa:.{sig_figs - 1}f}"
    return f"{s} \\times 10^{{{int(exponent)}}}"


def build_formula(template: str, **kwargs) -> str:
    """将值填入LaTeX模板。模板中用{name}占位。

    kwargs 的值如果是数字则自动浮点数格式化，否则直接str()插入。

    示例:
        build_formula(r"\frac{{{a}}}{{{b}}} = {c}", a=10, b=3, c=3.333)
    """
    result = template
    for key, val in kwargs.items():
        placeholder = "{" + key + "}"
        if isinstance(val, float):
            formatted = format_number(val)
        else:
            formatted = str(val)
        result = result.replace(placeholder, formatted)
    return result
