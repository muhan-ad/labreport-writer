"""新贡献感知与拉取：列出 contributions/ 下的贡献目录，未登记的下载到 inbox 并登记为 new。"""
from pathlib import Path

from .states import States

KINDS = ('variants', 'reports')


def discover(cos):
    """从桶上枚举全部贡献目录（contributions/<kind>/<实验>/<时间戳>），按路径升序。"""
    dirs = set()
    for key in cos.list_keys('contributions/'):
        parts = key.split('/')
        if len(parts) >= 4 and parts[1] in KINDS and parts[2] not in ('_meta', 'processed'):
            dirs.add('/'.join(parts[:4]))
    return sorted(dirs)


def parse_dir(dir_key):
    """'contributions/reports/<实验>/<时间戳>' → (kind, exp, ts)。"""
    parts = dir_key.split('/')
    return parts[1], parts[2], parts[3]


def sync(cos, cfg, states, reviewer, dry=False):
    """发现新贡献 → 下载到 workspace/inbox/<kind>/<实验>/<时间戳>/ → 登记 new。

    返回 (new_dirs, known_count)。dry 模式下 Cos 已是本地 mock，登记落在本地无副作用。
    """
    workspace = Path(cfg['workspace'])
    all_dirs = discover(cos)
    known = states.load()['items']
    new_dirs = [d for d in all_dirs if d not in known]
    downloaded = []
    for d in new_dirs:
        keys = cos.list_keys(d + '/')
        for key in keys:
            rel = key.split('/', 1)[1] if '/' in key else key   # 去掉 contributions/ 前缀
            cos.download(key, workspace / 'inbox' / rel)
        states.set(d, 'new', reviewer=reviewer, note='sync 自动登记')
        downloaded.append(d)
    return downloaded, len(all_dirs) - len(new_dirs)
