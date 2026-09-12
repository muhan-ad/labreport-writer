"""云端共享审核状态：contributions/_meta/states.json（多人读-比-写，简单版本号乐观锁）。

states.json 结构：
{
  "rev": 7,                                   ← 每次写入 +1（乐观锁依据）
  "items": {
    "contributions/reports/<实验>/<时间戳>": {
       "status": "new|approved|rejected|processing|merged|done",
       "reviewer": "...", "note": "...", "updated_at": "ISO 时间"
    }, ...
  }
}
"""
import json
from datetime import datetime, timezone

STATES_KEY = 'contributions/_meta/states.json'
VALID_STATUS = ('new', 'approved', 'rejected', 'processing', 'merged', 'done')


class ConflictError(RuntimeError):
    """他人先写了状态：请重新 sync 后再操作。"""


class States:
    def __init__(self, cos):
        self.cos = cos

    def load(self):
        raw = self.cos.get_json(STATES_KEY)
        if not raw or not isinstance(raw, dict):
            return {'rev': 0, 'items': {}}
        raw.setdefault('rev', 0)
        raw.setdefault('items', {})
        return raw

    def get(self, key, default_status='new'):
        st = self.load()
        return st['items'].get(key, {'status': default_status, 'reviewer': '', 'note': '', 'updated_at': ''})

    def set(self, key, status, reviewer, note=None, expect_rev=None):
        """更新一条状态。expect_rev 不符（他人先写）时抛 ConflictError。"""
        if status not in VALID_STATUS:
            raise ValueError(f'非法状态：{status}')
        cur = self.load()
        if expect_rev is not None and cur['rev'] != expect_rev:
            raise ConflictError('状态已被他人更新，请重新 sync 后重试')
        cur['rev'] = int(cur.get('rev', 0)) + 1
        item = cur['items'].get(key, {})
        item.update({
            'status': status,
            'reviewer': reviewer,
            'note': note if note is not None else item.get('note', ''),
            'updated_at': datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'),
        })
        cur['items'][key] = item
        self.cos.put_json(STATES_KEY, cur)
        return cur

    def pending(self, statuses=('new',)):
        """返回处于指定状态的贡献目录列表（升序）。"""
        st = self.load()
        return sorted(k for k, v in st['items'].items() if v.get('status') in statuses)

    def summary(self):
        st = self.load()
        lines = []
        for key in sorted(st['items']):
            v = st['items'][key]
            lines.append(f"{v.get('status', '?'):10s} {v.get('reviewer', '-') or '-':12s} {key}"
                         + (f"  # {v.get('note')}" if v.get('note') else ''))
        return lines
