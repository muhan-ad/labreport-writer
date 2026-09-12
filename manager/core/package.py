"""打包推送：主仓库实验脚本 → data-package zip → dataVersion 自动 +1 → 上传 COS → 归档。

排除规则与主应用现有数据包一致（__pycache__ / docx / png / xlsx / .lab_sections.json / .mimosa）。
上传顺序：先 zip 后 manifest（manifest 是用户端"检查实验数据更新"的生效开关）。
"""
import json
import os
import zipfile
from pathlib import Path

MANIFEST_KEY = 'data-manifest.json'
ARCHIVE_PREFIX = 'app-data/archives'
EXCLUDE_SUFFIX = ('.docx', '.png', '.xlsx', '.xls')
EXCLUDE_NAMES = ('.lab_sections.json',)


def bump_version(ver):
    """'1.0.0' → '1.0.1'（patch 位 +1）。"""
    parts = str(ver).lstrip('v').split('.')
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f'无法解析数据版本号：{ver}')
    parts[2] = str(int(parts[2]) + 1)
    return '.'.join(parts)


def build_zip(main_repo, out_zip):
    """以主仓库 物理实验/实验脚本 为源打数据包，返回打包文件数。"""
    src_root = (Path(main_repo) / '物理实验' / '实验脚本').resolve()
    if not src_root.is_dir():
        raise FileNotFoundError(f'主仓库实验脚本目录不存在：{src_root}')
    count = 0
    with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for dp, dns, fns in os.walk(src_root):
            dns[:] = [d for d in dns if d != '__pycache__']
            for fn in fns:
                if fn.lower().endswith(EXCLUDE_SUFFIX) or fn in EXCLUDE_NAMES:
                    continue
                full = Path(dp) / fn
                if '__pycache__' in full.parts or '.mimosa' in full.parts:
                    continue
                rel = Path('实验脚本') / full.relative_to(src_root)
                zf.writestr(rel.as_posix(), full.read_bytes())
                count += 1
    return count


def merge_candidate(main_repo, exp_id, candidate):
    """把审核通过的候选变体合入主仓库该实验 variants.json（按章节追加、文本去重）。

    返回 {章节: 新增条数}。
    """
    from .validate import SECTION_WHITELIST
    variants_path = Path(main_repo) / '物理实验' / '实验脚本' / exp_id / 'variants.json'
    if not variants_path.is_file():
        raise FileNotFoundError(f'该实验 variants.json 不存在：{variants_path}')
    data = json.loads(variants_path.read_text(encoding='utf-8'))
    added = {}
    for section, texts in candidate.items():
        if section not in SECTION_WHITELIST or not isinstance(texts, list):
            continue
        arr = data.setdefault(section, [])
        n = 0
        for t in texts:
            if isinstance(t, str) and t.strip() and t not in arr:
                arr.append(t)
                n += 1
        if n:
            added[section] = n
    variants_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    return added


def package(cos, cfg, notes='', dry=False):
    """完整推送流程。返回 (新版本, zip 本地路径, 文件数)。dry 时不访问网络、不上传。"""
    main_repo = Path(cfg['main_repo'])
    workspace = Path(cfg['workspace'])
    workspace.mkdir(parents=True, exist_ok=True)

    if dry:
        current = '1.0.0'
    else:
        manifest = cos.get_json(MANIFEST_KEY)
        if not manifest or not manifest.get('dataVersion'):
            raise RuntimeError('线上 data-manifest.json 缺失或无 dataVersion，请先确认已发布过数据包')
        current = str(manifest['dataVersion']).lstrip('v')
    new_ver = bump_version(current)

    zip_path = workspace / f'data-package-{new_ver}.zip'
    count = build_zip(main_repo, zip_path)

    if not dry:
        # 旧 zip 归档（存在才归档）
        old_key = f'data-package-{current}.zip'
        archive_key = f'{ARCHIVE_PREFIX}/data-package-{current}.zip'
        if cos.exists(old_key):
            cos.move(old_key, archive_key)
        # 先 zip 后 manifest（manifest 最后覆盖 = 生效开关）
        cos.upload(f'data-package-{new_ver}.zip', zip_path)
        cos.put_json(MANIFEST_KEY, {
            'dataVersion': new_ver,
            'notes': notes or '贡献数据审核合入',
            'url': cos.public_url(f'data-package-{new_ver}.zip'),
        })
    return new_ver, zip_path, count
