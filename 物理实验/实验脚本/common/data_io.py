# -*- coding: utf-8 -*-
"""数据模型 IO —— 方式三：data.json 是数据真相。

generate.py 通过 load_data 读取实验数据（dict），不再读 xlsx 坐标。
"""
import json
import os


def load_data(path):
    """读取 data.json，返回 dict。文件不存在返回空 dict。"""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)