# -*- coding: utf-8 -*-
"""manager 规则回归测试：python tests/test_rules.py（需主仓库在上级目录）。"""
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from core.validate import validate_variants, compute_return_keys  # noqa: E402
from core.package import merge_candidate, bump_version            # noqa: E402

MAIN = BASE.parent
EXP = '重力加速度的测量'
GEN = MAIN / '物理实验' / '实验脚本' / EXP / 'generate.py'
allowed = compute_return_keys(GEN)
assert allowed, '未能提取 _compute 键'
print('allowed keys:', sorted(allowed))

# ── 坏样例：应逐项捕获 ──
existing = {'实验原理': [
    '单摆法测量重力加速度的实验原理基于小角度简谐振动，周期公式给出重力加速度的计算途径，'
    '实验通过测量摆长与周期计算重力加速度的数值，并做系统误差修正。'
]}
bad = {
    '实验原理': [
        # $ 奇数 + $$ + \( \) + 杜撰键 + 个人信息 + 长度合规
        '这条存在未成对公式 $T = 2\\pi l 以及双定符 $$ 的用法，含杜撰键 %%DATA:fake_key:%.2f%%，'
        '还泄露了 学号：20231001 等个人信息，并使用 \\(行内\\) 定界符，属多重违规样例文本。'
    ],
    '幻觉章节': ['这一章根本不存在于白名单中，用来验证章节键校验是否生效，长度补充到四十个字以上以便观察输出。'],
    '结论': [
        # 与 existing 高度相似
        '单摆法测量重力加速度的实验原理基于小角度简谐振动，周期公式给出重力加速度的计算途径，'
        '实验通过测量摆长与周期计算重力加速度的数值，并做系统误差修正补充内容。'
    ],
}
errs = validate_variants(bad, allowed, existing)
print('BAD errors:')
for e in errs:
    print('  -', e)
joined = '\n'.join(errs)
for token in ('奇数', '$$', '\\(', 'fake_key', '个人信息', '白名单', '高度相似'):
    assert token in joined, f'规则未生效：{token}'
print('[OK] 全部坏样例规则命中')

# ── 好样例：应通过 ──
good = {
    '实验原理': [
        '本实验采用复摆法测定当地重力加速度。刚体绕固定轴做小角度摆动时，其周期与回转半径、'
        '质心到转轴的距离满足可倒摆关系式 $T = 2\\pi\\sqrt{\\dfrac{h_1 + h_2}{g}}$，'
        '通过改变支点位置测得多组周期即可解出 $g$，从而避免直接测量摆长的系统误差。'
        '数据处理采用 %%DATA:g_calc:%.4f%% 作为最终计算结果。'
    ],
}
errs = validate_variants(good, allowed, existing)
assert not errs, f'好样例不应报错：{errs}'
print('[OK] 好样例通过')

# ── merge_candidate 真实写 + 还原（文本带时间戳，重复运行幂等）──
import time
tag = str(int(time.time()))
cand = {'实验原理': [f'管理内核合并测试条目 {tag}——验证写入后立即还原，不会保留在仓库中。']}
before = json.loads((GEN.parent / 'variants.json').read_text(encoding='utf-8'))
try:
    added = merge_candidate(MAIN, EXP, cand)
    after = json.loads((GEN.parent / 'variants.json').read_text(encoding='utf-8'))
    assert added.get('实验原理') == 1, f'added 异常：{added}'
    assert len(after['实验原理']) == len(before['实验原理']) + 1
    print('[OK] merge 写入生效：', added)
finally:
    subprocess.run(['git', 'checkout', '--', str(GEN.parent / 'variants.json')], cwd=MAIN, check=True)
    restored = json.loads((GEN.parent / 'variants.json').read_text(encoding='utf-8'))
    assert len(restored['实验原理']) == len(before['实验原理'])
    print('[OK] 仓库已还原')

# ── bump ──
assert bump_version('1.0.0') == '1.0.1' and bump_version('1.2.9') == '1.2.10'
print('[OK] bump_version')

print('ALL TESTS PASSED')
