"""不确定度计算：A类、B类、合成、传递。"""

import math


def mean(data: list[float]) -> float:
    """算术平均值。"""
    if not data:
        raise ValueError("data 不能为空")
    return sum(data) / len(data)


def std_dev(data: list[float], ddof: int = 1) -> float:
    """样本标准差 (ddof=1) 或总体标准差 (ddof=0)。"""
    n = len(data)
    if n < 2:
        return 0.0
    avg = mean(data)
    return math.sqrt(sum((x - avg) ** 2 for x in data) / (n - ddof))


def type_a(data: list[float]) -> float:
    """A类不确定度：标准差的均值标准误 s / sqrt(n)。"""
    n = len(data)
    if n < 2:
        return 0.0
    return std_dev(data) / math.sqrt(n)


def type_b(instrument_error: float, distribution: str = "uniform") -> float:
    """B类不确定度。

    distribution:
        'uniform' → C = sqrt(3)  (默认，均匀分布)
        'normal'  → C = 3        (正态分布，置信概率99.73%)
        'triangular' → C = sqrt(6)
    """
    c_map = {"uniform": math.sqrt(3), "normal": 3.0, "triangular": math.sqrt(6)}
    c = c_map.get(distribution)
    if c is None:
        raise ValueError(f"未知分布类型: {distribution}")
    return instrument_error / c


def combine(*uncertainties: float) -> float:
    """合成不确定度：sqrt(sum(u_i^2))。"""
    return math.sqrt(sum(u * u for u in uncertainties))


def propagate_numeric(func, params: dict) -> tuple[float, float]:
    """数值法不确定度传递。

    对 func(**params) 在每个参数上做有限差分求偏导，
    返回 (函数值, 合成不确定度)。

    params 格式: {'x': (value, uncertainty), 'y': (value, uncertainty), ...}

    示例:
        def f(x, y): return x * y
        val, u = propagate_numeric(f, {'x': (3.0, 0.1), 'y': (4.0, 0.2)})
    """
    param_names = list(params.keys())
    values = {k: v[0] for k, v in params.items()}
    uncertainties = {k: v[1] for k, v in params.items()}

    f0 = func(**values)

    variance = 0.0
    h = 1e-8  # 有限差分步长
    for name in param_names:
        v = values[name]
        h_actual = max(abs(v) * h, h)
        perturbed = dict(values)
        perturbed[name] = v + h_actual
        f_plus = func(**perturbed)
        perturbed[name] = v - h_actual
        f_minus = func(**perturbed)
        partial = (f_plus - f_minus) / (2 * h_actual)
        variance += (partial * uncertainties[name]) ** 2

    return f0, math.sqrt(variance)
