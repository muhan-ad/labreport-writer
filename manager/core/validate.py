"""强校验：agent 产出的变体 JSON 必须全部通过才能进入合入流程。

校验维度：JSON 结构 / 章节白名单 / 条数与字数 / $ 公式成对 / %%DATA 键 ⊆ 该实验 _compute 键 /
个人信息泄露启发式 / 与官方现有变体相似度。
"""
import ast
import difflib
import re
from pathlib import Path

SECTION_WHITELIST = ('实验原理', '实验方法', '误差分析', '结论', '实验结论')
DATA_RE = re.compile(r'%%DATA:([^:]+):')
PII_RE = re.compile(r'(姓名|学号|班级|学院)\s*[:：]\s*\S+')
MIN_ENTRY, MAX_ENTRY = 40, 1000        # 单条字数硬限
MIN_PER_SECTION, MAX_PER_SECTION = 1, 3
SIM_THRESHOLD = 0.90                   # 与官方现有变体的相似度上限


def compute_return_keys(generate_py_path):
    """ast 解析 generate.py 的 _compute 返回字典键（%%DATA 合法键清单）。

    逻辑与主仓库 smoke_test.py 保持一致。
    """
    src = Path(generate_py_path).read_text(encoding='utf-8')
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_compute'), None)
    if fn is None:
        return set()
    keys = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict):
            for k in n.value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
    return keys


def _check_entry(text, allowed_keys, existing_texts, errors, where):
    if not isinstance(text, str) or not text.strip():
        errors.append(f'{where}: 条目为空')
        return
    if len(text) < MIN_ENTRY or len(text) > MAX_ENTRY:
        errors.append(f'{where}: 条目长度 {len(text)} 超出 [{MIN_ENTRY},{MAX_ENTRY}]')
    if text.count('$') % 2 != 0:
        errors.append(f'{where}: "$" 数量为奇数（公式未成对）')
    if '$$' in text:
        errors.append(f'{where}: 不允许 $$（请使用行内 $...$）')
    if re.search(r'\\\(|\\\)', text):
        errors.append(f'{where}: 不允许 \\( \\) 定界符')
    used = set(DATA_RE.findall(text))
    unknown = used - allowed_keys
    if unknown:
        errors.append(f'{where}: %%DATA 键不在该实验 _compute 清单中: {sorted(unknown)}')
    if PII_RE.search(text):
        errors.append(f'{where}: 疑似包含个人信息（姓名/学号/班级等），必须删除')
    if existing_texts:
        for ref in existing_texts:
            ratio = difflib.SequenceMatcher(None, text, ref).ratio()
            if ratio >= SIM_THRESHOLD:
                errors.append(f'{where}: 与官方现有变体高度相似（{ratio:.2f}），请换措辞')
                break


def validate_variants(obj, allowed_keys, existing_variants=None):
    """校验变体候选 dict，返回错误列表（空列表 = 通过）。"""
    errors = []
    if not isinstance(obj, dict) or not obj:
        return ['输出必须是「章节 → 文本数组」的非空 JSON 对象']
    existing_texts = []
    if isinstance(existing_variants, dict):
        for arr in existing_variants.values():
            if isinstance(arr, list):
                existing_texts += [t for t in arr if isinstance(t, str)]
    for section, entries in obj.items():
        if section not in SECTION_WHITELIST:
            errors.append(f'章节键 "{section}" 不在白名单 {SECTION_WHITELIST}')
            continue
        if not isinstance(entries, list) or not entries:
            errors.append(f'"{section}" 应为非空文本数组')
            continue
        if not (MIN_PER_SECTION <= len(entries) <= MAX_PER_SECTION):
            errors.append(f'"{section}" 条数 {len(entries)} 超出 [{MIN_PER_SECTION},{MAX_PER_SECTION}]')
        for i, text in enumerate(entries, 1):
            _check_entry(text, allowed_keys, existing_texts, errors, f'{section}#{i}')
    return errors
