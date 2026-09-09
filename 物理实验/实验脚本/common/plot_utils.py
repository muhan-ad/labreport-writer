"""通用作图工具 — 基于 matplotlib 生成数据曲线图。

提供折线图、散点图、线性拟合图、柱状图等通用绘图函数，
生成的图片可通过 DocxReportWriter.add_image() 插入报告。

要求：matplotlib 已安装（pip install matplotlib）。
中文字体自动回退到 SimHei / Microsoft YaHei。
"""

import os
import matplotlib
matplotlib.use('Agg')  # 非交互式后端，无需 GUI
import matplotlib.pyplot as plt
import numpy as np


# ── 中文字体配置 ──
def _setup_chinese_font():
    """配置 matplotlib 中文字体，避免中文显示为方框。"""
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False  # 负号正常显示


_setup_chinese_font()


def plot_xy(x, y, xlabel='', ylabel='', title='', save_path='plot.png',
            kind='line', color='#1a5632', figsize=(6, 4), dpi=150,
            marker='o', markersize=4, linestyle='-', linewidth=1.2,
            grid=True, legend_label=None):
    """绘制折线图或散点图。

    Args:
        x: x 轴数据（列表或数组）
        y: y 轴数据（列表或数组）
        xlabel: x 轴标签
        ylabel: y 轴标签
        title: 图表标题
        save_path: 图片保存路径
        kind: 'line' 折线图 / 'scatter' 散点图
        color: 线条/点颜色
        figsize: 图片尺寸 (宽, 高) 英寸
        dpi: 分辨率
        marker: 数据点标记
        markersize: 标记大小
        linestyle: 线条样式
        linewidth: 线条宽度
        grid: 是否显示网格
        legend_label: 图例标签（None 则不显示图例）
    """
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    if kind == 'scatter':
        ax.scatter(x, y, c=color, s=markersize * 8, alpha=0.8, label=legend_label)
    else:
        ax.plot(x, y, color=color, marker=marker, markersize=markersize,
                linestyle=linestyle, linewidth=linewidth, label=legend_label)
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    if title:
        ax.set_title(title, fontsize=12, fontweight='bold')
    if grid:
        ax.grid(True, alpha=0.3, linestyle='--')
    if legend_label:
        ax.legend(fontsize=10)
    fig.tight_layout()
    fig.savefig(save_path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return save_path


def plot_fit(x, y, slope, intercept, xlabel='', ylabel='', title='',
             save_path='fit_plot.png', data_color='#1a5632',
             fit_color='#c0392b', figsize=(6, 4), dpi=150,
             data_label='实验数据', fit_label=None, r_squared=None):
    """绘制带线性拟合的散点图。

    Args:
        x: x 轴数据
        y: y 轴数据
        slope: 拟合斜率
        intercept: 拟合截距
        xlabel, ylabel, title: 标签和标题
        save_path: 保存路径
        data_color: 数据点颜色
        fit_color: 拟合线颜色
        figsize, dpi: 尺寸和分辨率
        data_label: 数据点图例
        fit_label: 拟合线图例（None 则自动生成）
        r_squared: 决定系数（显示在图中，None 则不显示）
    """
    if fit_label is None:
        fit_label = f'线性拟合: y = {slope:.4f}x + {intercept:.4f}'
        if r_squared is not None:
            fit_label += f', R^2 = {r_squared:.4f}'

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.scatter(x, y, c=data_color, s=40, alpha=0.8, label=data_label, zorder=3)

    # 绘制拟合线
    x_fit = np.linspace(min(x), max(x), 100)
    y_fit = slope * x_fit + intercept
    ax.plot(x_fit, y_fit, color=fit_color, linewidth=1.5, label=fit_label, zorder=2)

    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    if title:
        ax.set_title(title, fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.legend(fontsize=9, loc='best')
    fig.tight_layout()
    fig.savefig(save_path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return save_path


def plot_multi_series(x_list, y_list, labels=None, xlabel='', ylabel='',
                      title='', save_path='multi_plot.png',
                      colors=None, figsize=(6, 4), dpi=150,
                      markers=None, linestyles=None, grid=True):
    """绘制多组数据的折线图。

    Args:
        x_list: x 轴数据列表（每组一个数组）
        y_list: y 轴数据列表（每组一个数组）
        labels: 每组的图例标签列表
        xlabel, ylabel, title: 标签和标题
        save_path: 保存路径
        colors: 颜色列表（None 则自动分配）
        figsize, dpi: 尺寸和分辨率
        markers: 标记列表
        linestyles: 线条样式列表
        grid: 是否显示网格
    """
    if colors is None:
        colors = ['#1a5632', '#c0392b', '#2980b9', '#f39c12', '#8e44ad', '#16a085']
    if markers is None:
        markers = ['o', 's', '^', 'D', 'v', 'p']
    if linestyles is None:
        linestyles = ['-', '--', '-.', ':', '-', '--']

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    for i, (x, y) in enumerate(zip(x_list, y_list)):
        label = labels[i] if labels and i < len(labels) else f'系列 {i+1}'
        ax.plot(x, y, color=colors[i % len(colors)],
                marker=markers[i % len(markers)], markersize=4,
                linestyle=linestyles[i % len(linestyles)],
                linewidth=1.2, label=label)
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    if title:
        ax.set_title(title, fontsize=12, fontweight='bold')
    if grid:
        ax.grid(True, alpha=0.3, linestyle='--')
    if labels:
        ax.legend(fontsize=9, loc='best')
    fig.tight_layout()
    fig.savefig(save_path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return save_path


def plot_bar(categories, values, xlabel='', ylabel='', title='',
             save_path='bar_plot.png', color='#1a5632', figsize=(6, 4),
             dpi=150, grid=True, value_labels=True):
    """绘制柱状图。

    Args:
        categories: 类别标签列表
        values: 数值列表
        xlabel, ylabel, title: 标签和标题
        save_path: 保存路径
        color: 柱子颜色
        figsize, dpi: 尺寸和分辨率
        grid: 是否显示网格
        value_labels: 是否在柱子上方显示数值
    """
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    bars = ax.bar(categories, values, color=color, alpha=0.8, width=0.6)
    if value_labels:
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2., height,
                    f'{height:.3g}', ha='center', va='bottom', fontsize=9)
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    if title:
        ax.set_title(title, fontsize=12, fontweight='bold')
    if grid:
        ax.grid(True, axis='y', alpha=0.3, linestyle='--')
    fig.tight_layout()
    fig.savefig(save_path, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    return save_path
