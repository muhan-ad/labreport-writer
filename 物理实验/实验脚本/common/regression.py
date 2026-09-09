"""最小二乘法线性回归 y = a + bx。"""

import math
from dataclasses import dataclass


@dataclass
class LinearRegressionResult:
    slope: float
    slope_uncertainty: float
    intercept: float
    intercept_uncertainty: float
    r_squared: float         # 相关系数平方 (R²)
    r: float                 # 相关系数


def linear_regression(x: list[float], y: list[float]) -> LinearRegressionResult:
    """最小二乘法拟合 y = a + bx。

    返回斜率b、截距a及其不确定度、相关系数。

    u_b = s_y * sqrt(1/S_xx)
    u_a = s_y * sqrt(1/n + x̄²/S_xx)
    s_y = sqrt( Σ(y_i - a - b*x_i)² / (n-2) )
    """
    n = len(x)
    if n != len(y):
        raise ValueError("x 和 y 长度必须相等")
    if n < 3:
        raise ValueError("至少需要3个数据点")

    x_mean = sum(x) / n
    y_mean = sum(y) / n

    S_xx = sum((xi - x_mean) ** 2 for xi in x)
    S_yy = sum((yi - y_mean) ** 2 for yi in y)
    S_xy = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))

    if S_xx == 0:
        raise ValueError("x 值全部相同，无法回归")

    b = S_xy / S_xx              # 斜率
    a = y_mean - b * x_mean      # 截距

    # 残差标准差
    residuals = [yi - a - b * xi for xi, yi in zip(x, y)]
    s_y = math.sqrt(sum(r ** 2 for r in residuals) / (n - 2))

    u_b = s_y / math.sqrt(S_xx)
    u_a = s_y * math.sqrt(1 / n + x_mean ** 2 / S_xx)

    # 相关系数
    denom = math.sqrt(S_xx * S_yy)
    r_val = S_xy / denom if denom != 0 else 0.0

    return LinearRegressionResult(
        slope=b,
        slope_uncertainty=u_b,
        intercept=a,
        intercept_uncertainty=u_a,
        r_squared=r_val ** 2,
        r=r_val,
    )
