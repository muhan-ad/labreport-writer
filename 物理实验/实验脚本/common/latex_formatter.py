"""数值 → LaTeX 格式字符串。"""

import math


def _first_sig_digit(x: float) -> int:
    """第一个非零数字所在的位（小数点后为正，前为负）。
    例: 0.034 → 3,  0.5 → 1,  120 → -2"""
    if x == 0:
        return 0
    return -int(math.floor(math.log10(abs(x))))


def format_number(value: float, uncertainty: float | None = None,
                   sig_figs: int | None = None) -> str:
    """数值转字符串，自动处理有效数字。

    - 有 uncertainty 时：不确定度保留1~2位有效数字，值与不确定度末位对齐
    - 无 uncertainty 时：保留 sig_figs 位有效数字（默认6位）
    """
    if uncertainty is not None and uncertainty > 0:
        # 小不确定度用2位有效数字，大不确定度用1位
        first = _first_sig_digit(uncertainty)
        # 第一个有效数字是1或2时保留2位，否则保留1位
        abs_first = abs(int(uncertainty / 10 ** (-first)))
        keep = 2 if abs_first in (1, 2) else 1
        decimal_places = max(0, first + keep - 1)
        return f"{value:.{decimal_places}f}"

    if sig_figs is not None:
        if value == 0:
            return "0"
        exponent = int(math.floor(math.log10(abs(value))))
        decimal_places = max(0, sig_figs - 1 - exponent)
        return f"{value:.{decimal_places}f}"

    # 默认：保留合理位数，去除多余的尾随零
    s = f"{value:.6g}"
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
