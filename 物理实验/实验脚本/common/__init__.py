"""Physical-Experience 公共工具库。

每个实验的 generate.py 只需要:
    from common import *
即可使用所有工具函数。

方式三：数据真相为 data.json，不再需要 Excel 读取 / Excel 富文本 / 公式文本输出工具。
"""

from .uncertainty import mean, std_dev, type_a, type_b, combine, propagate_numeric
from .regression import linear_regression, LinearRegressionResult
from .latex_formatter import format_number, format_scientific, build_formula
from .data_io import load_data
