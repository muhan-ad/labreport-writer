#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""管理应用内核 CLI——贡献数据审核 / 加工 / 推送流水线。

典型流水线：
  python manager.py sync
  python manager.py review list
  python manager.py review approve contributions/reports/<实验>/<时间戳>
  python manager.py process contributions/reports/<实验>/<时间戳>
  python manager.py merge  contributions/reports/<实验>/<时间戳>
  python manager.py package --note "合入 3 位学生的优秀报告"
  python manager.py archive contributions/reports/<实验>/<时间戳>
"""
import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from core.config import load_config                      # noqa: E402
from core.cos_client import Cos                          # noqa: E402
from core.states import States, ConflictError            # noqa: E402
from core import sync as sync_mod                        # noqa: E402
from core import mineru as mineru_mod                    # noqa: E402
from core import validate as validate_mod                # noqa: E402
from core.agent import VariantAgent                      # noqa: E402
from core import package as pkg_mod                      # noqa: E402


def _ctx(args):
    cfg = load_config()
    cos = Cos(cfg)
    return cfg, cos, States(cos)


def _reviewer(args, cfg):
    return getattr(args, 'reviewer', None) or cfg['reviewer']


def _inbox_dir(cfg, key):
    rel = key.split('/', 1)[1] if '/' in key else key
    return Path(cfg['workspace']) / 'inbox' / rel


def _draft_dir(cfg, key):
    rel = key.split('/', 1)[1] if '/' in key else key
    return Path(cfg['workspace']) / 'drafts' / rel


# ── sync ──
def cmd_sync(args):
    cfg, cos, states = _ctx(args)
    new, known = sync_mod.sync(cos, cfg, states, _reviewer(args, cfg), dry=args.dry_run or cfg['dry'])
    print(f'贡献目录共 {new.__class__ and (len(new) + known)} 个，其中新贡献 {len(new)} 个：')
    for d in new:
        print('  +', d)
    if not new:
        print('  （无新贡献）')


# ── review ──
def cmd_review(args):
    cfg, cos, states = _ctx(args)
    reviewer = _reviewer(args, cfg)
    if args.action == 'list':
        st = states.load()
        rows = [(k, v) for k, v in sorted(st['items'].items())
                if not args.status or v.get('status') == args.status]
        if not rows:
            print('（无记录，先执行 sync）')
            return
        for k, v in rows:
            print(f"{v.get('status', '?'):10s} {v.get('reviewer', '-') or '-':12s} {k}"
                  + (f"  # {v.get('note')}" if v.get('note') else ''))
        return
    key = args.dir
    status = 'approved' if args.action == 'approve' else 'rejected'
    try:
        states.set(key, status, reviewer=reviewer, note=args.note)
        print(f'{key} → {status}')
    except ConflictError as e:
        print(f'冲突：{e}')


# ── export ──
def cmd_export(args):
    cfg, cos, states = _ctx(args)
    inbox = _inbox_dir(cfg, args.dir)
    if not inbox.is_dir():
        print('本地 inbox 中没有该贡献，请先执行 sync')
        return
    dest = Path(args.to) if args.to else (Path(cfg['workspace']) / 'export' / (
        args.dir.split('/', 1)[1].replace('/', '_') + '_' + datetime.now().strftime('%Y%m%d_%H%M%S')))
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(inbox, dest, dirs_exist_ok=True)
    print(f'已导出 → {dest.resolve()}')


# ── process ──
def cmd_process(args):
    cfg, cos, states = _ctx(args)
    key = args.dir
    info = states.get(key)
    if info['status'] != 'approved' and not args.force:
        print(f"拒绝处理：当前状态为 {info['status']}，需先 review approve（或加 --force）")
        return
    kind, exp_id, ts = sync_mod.parse_dir(key)
    inbox = _inbox_dir(cfg, key)
    files = [p for p in sorted(inbox.rglob('*'))
             if p.is_file() and p.suffix.lower() in (mineru_mod.IMG_EXT + mineru_mod.DOC_EXT)]
    if not files:
        print('inbox 中没有可解析的图片/文档文件')
        return
    dry = args.dry_run or cfg['dry'] or not cfg['mineru_token']
    mineru = mineru_mod.MinerU(cfg['mineru_token'], Path(cfg['workspace']) / 'mineru_out', dry=dry)
    print(f'MinerU 解析 {len(files)} 个文件（dry={dry}）…')
    mds = mineru.parse_files(files)
    markdown = '\n\n'.join(f'## 来源：{p.name}\n\n{p.read_text(encoding="utf-8")}' for p in mds)

    gen_py = Path(cfg['main_repo']) / '物理实验' / '实验脚本' / exp_id / 'generate.py'
    allowed = validate_mod.compute_return_keys(gen_py)
    if not allowed:
        print(f'警告：未能从 generate.py 提取 _compute 键（{gen_py}），%%DATA 校验将退化为仅格式检查')
    existing_path = gen_py.parent / 'variants.json'
    existing = json.loads(existing_path.read_text(encoding='utf-8')) if existing_path.is_file() else {}

    agent = VariantAgent(cfg, dry=args.dry_run or cfg['dry'] or not cfg['llm_api_key'])
    print('工作流 agent 转化中…')
    candidate, errors = agent.markdown_to_variants(markdown, exp_id, allowed, existing)

    draft = _draft_dir(cfg, key)
    draft.mkdir(parents=True, exist_ok=True)
    (draft / 'variants_candidate.json').write_text(
        json.dumps(candidate, ensure_ascii=False, indent=1), encoding='utf-8')
    (draft / 'validation.txt').write_text('\n'.join(errors) if errors else 'PASS', encoding='utf-8')

    if not dry:
        states.set(key, 'processing', reviewer=_reviewer(args, cfg), note=f'候选 {len(candidate)} 章')
    print(f'候选已写入 {draft}')
    if errors:
        print('⚠ 校验未通过（已保存候选，需人工修改后 merge）：')
        for e in errors:
            print('  -', e)
    else:
        print('✓ 校验通过，可执行 merge 合入官方变体库')


# ── merge ──
def cmd_merge(args):
    cfg, cos, states = _ctx(args)
    key = args.dir
    draft = _draft_dir(cfg, key) / 'variants_candidate.json'
    if not draft.is_file():
        print('未找到候选文件，请先 process')
        return
    candidate = json.loads(draft.read_text(encoding='utf-8'))
    kind, exp_id, ts = sync_mod.parse_dir(key)
    if args.dry_run or cfg['dry']:
        preview = {s: len(t) for s, t in candidate.items()}
        print(f'（dry 模式：不写主仓库。将合入 {exp_id}：{json.dumps(preview, ensure_ascii=False)}）')
        return
    added = pkg_mod.merge_candidate(Path(cfg['main_repo']), exp_id, candidate)
    states.set(key, 'merged', reviewer=_reviewer(args, cfg))
    total = sum(added.values())
    print(f'已合入 {exp_id}/variants.json：' + (json.dumps(added, ensure_ascii=False) if added else '无新增（全部重复）'))
    if total:
        print('⚠ 请检查并 git 提交主仓库变更（合并的 variants.json），之后执行 package 推送')


# ── validate ──
def cmd_validate(args):
    cfg, cos, states = _ctx(args)
    obj = json.loads(Path(args.file).read_text(encoding='utf-8'))
    gen_py = Path(cfg['main_repo']) / '物理实验' / '实验脚本' / args.exp / 'generate.py'
    allowed = validate_mod.compute_return_keys(gen_py)
    existing_path = gen_py.parent / 'variants.json'
    existing = json.loads(existing_path.read_text(encoding='utf-8')) if existing_path.is_file() else {}
    errors = validate_mod.validate_variants(obj, allowed, existing)
    if errors:
        print('未通过：')
        for e in errors:
            print('  -', e)
        sys.exit(1)
    print('PASS')


# ── package ──
def cmd_package(args):
    cfg, cos, states = _ctx(args)
    dry = args.dry_run or cfg['dry']
    ver, zip_path, count = pkg_mod.package(cos, cfg, notes=args.note, dry=dry)
    print(f'数据包 {ver} 已生成：{zip_path}（{count} 个文件）')
    if dry:
        print('（dry 模式：未上传；配置 COS 密钥后重试即可推送）')
    else:
        print('已上传：zip 与 data-manifest.json 均已更新，用户端「检查实验数据更新」即可感知')


# ── archive ──
def cmd_archive(args):
    cfg, cos, states = _ctx(args)
    key = args.dir
    keys = cos.list_keys(key + '/')
    moved = 0
    for k in keys:
        rest = k.split('/', 1)[1] if '/' in k else k          # <kind>/<实验>/<ts>/<文件>
        cos.move(k, f'contributions/processed/{rest}')
        moved += 1
    if not args.dry_run:
        states.set(key, 'done', reviewer=_reviewer(args, cfg), note=args.note)
    inbox = _inbox_dir(cfg, key)
    if inbox.is_dir():
        shutil.rmtree(inbox, ignore_errors=True)
    print(f'已归档 {moved} 个对象到 contributions/processed/')


def main():
    ap = argparse.ArgumentParser(description='贡献数据审核/加工/推送流水线内核')
    ap.add_argument('--dry-run', action='store_true', help='演练模式：不访问外部服务、不写云端状态')
    ap.add_argument('--reviewer', help='审核人署名（默认取 .env REVIEWER 或系统用户名）')
    sub = ap.add_subparsers(dest='cmd', required=True)

    sub.add_parser('sync', help='感知新贡献并拉取到 inbox').set_defaults(func=cmd_sync)

    rev = sub.add_parser('review', help='人工审核（第一关）')
    rev.add_argument('action', choices=['list', 'approve', 'reject'])
    rev.add_argument('dir', nargs='?', help='贡献目录，如 contributions/reports/<实验>/<时间戳>')
    rev.add_argument('--status', help='list 过滤状态')
    rev.add_argument('--note', default=None, help='备注')
    rev.set_defaults(func=cmd_review)

    exp = sub.add_parser('export', help='导出贡献原始文件到本地')
    exp.add_argument('dir')
    exp.add_argument('--to', default=None)
    exp.set_defaults(func=cmd_export)

    pro = sub.add_parser('process', help='MinerU 解析 + agent 转化为候选变体')
    pro.add_argument('dir')
    pro.add_argument('--force', action='store_true', help='跳过 approved 状态检查')
    pro.set_defaults(func=cmd_process)

    mg = sub.add_parser('merge', help='把候选变体合入主仓库 variants.json')
    mg.add_argument('dir')
    mg.set_defaults(func=cmd_merge)

    val = sub.add_parser('validate', help='独立校验变体 JSON')
    val.add_argument('file')
    val.add_argument('--exp', required=True, help='实验目录名（用于提取允许键）')
    val.set_defaults(func=cmd_validate)

    pk = sub.add_parser('package', help='打数据包并推送（dataVersion 自动 +1）')
    pk.add_argument('--note', default='', help='数据更新说明')
    pk.set_defaults(func=cmd_package)

    ar = sub.add_parser('archive', help='归档已处理的贡献目录')
    ar.add_argument('dir')
    ar.add_argument('--note', default=None)
    ar.set_defaults(func=cmd_archive)

    args = ap.parse_args()
    try:
        args.func(args)
    except ConflictError as e:
        print(f'冲突：{e}')
        sys.exit(2)


if __name__ == '__main__':
    main()
