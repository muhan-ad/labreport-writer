"""COS 访问层：列举/下载/上传/移动/JSON 读写。

dry 模式（未配置密钥）时用本地目录 workspace/cloud_mock/ 模拟桶，
接口行为与真实 COS 一致，便于全流程演练。
"""
import json
import shutil
from pathlib import Path


class Cos:
    def __init__(self, cfg):
        self.dry = bool(cfg.get('dry'))
        self.bucket = cfg['cos_bucket']
        self.region = cfg['cos_region']
        self.mock_root = Path(cfg['workspace']) / 'cloud_mock'
        if self.dry:
            self.mock_root.mkdir(parents=True, exist_ok=True)
            self.client = None
        else:
            from qcloud_cos import CosConfig, CosS3Client
            self.client = CosS3Client(CosConfig(
                Region=cfg['cos_region'],
                SecretId=cfg['cos_secret_id'],
                SecretKey=cfg['cos_secret_key'],
            ))

    # ── 列举 ──
    def list_keys(self, prefix):
        """返回前缀下全部对象 key（分页聚合）。"""
        if self.dry:
            root = self.mock_root
            out = []
            for p in root.rglob('*'):
                if p.is_file():
                    rel = p.relative_to(root).as_posix()
                    if rel.startswith(prefix):
                        out.append(rel)
            return sorted(out)
        keys, marker = [], ''
        while True:
            resp = self.client.list_objects(Bucket=self.bucket, Prefix=prefix, Marker=marker, MaxKeys=1000)
            keys += [c['Key'] for c in resp.get('Contents', [])]
            if resp.get('IsTruncated') == 'true':
                marker = resp['NextMarker']
            else:
                return sorted(keys)

    # ── 下载 / 上传 ──
    def download(self, key, local_path):
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        if self.dry:
            src = self.mock_root / key
            if src.exists():
                shutil.copyfile(src, local_path)
            else:
                local_path.write_text('', encoding='utf-8')  # 模拟空对象
            return local_path
        self.client.download_file(Bucket=self.bucket, Key=key, DestFilePath=str(local_path))
        return local_path

    def upload(self, key, local_path):
        local_path = Path(local_path)
        if self.dry:
            dest = self.mock_root / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local_path, dest)
            return key
        self.client.upload_file(Bucket=self.bucket, Key=key, LocalFilePath=str(local_path))
        return key

    def upload_bytes(self, key, data: bytes):
        if self.dry:
            dest = self.mock_root / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return key
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return key

    # ── 移动（复制 + 删除，COS 无原子 rename）──
    def move(self, key, new_key):
        if self.dry:
            src = self.mock_root / key
            dest = self.mock_root / new_key
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                shutil.move(str(src), str(dest))
            return new_key
        self.client.copy_object(Bucket=self.bucket, Key=new_key,
                                CopySource={'Bucket': self.bucket, 'Key': key, 'Region': self.region})
        self.client.delete_object(Bucket=self.bucket, Key=key)
        return new_key

    def exists(self, key):
        if self.dry:
            return (self.mock_root / key).exists()
        return self.client.object_exists(Bucket=self.bucket, Key=key)

    # ── JSON 便捷读写 ──
    def get_json(self, key):
        if self.dry:
            f = self.mock_root / key
            if not f.exists():
                return None
            return json.loads(f.read_text(encoding='utf-8'))
        if not self.client.object_exists(Bucket=self.bucket, Key=key):
            return None
        resp = self.client.get_object(Bucket=self.bucket, Key=key)
        return json.loads(resp['Body'].read().decode('utf-8'))

    def put_json(self, key, obj):
        data = json.dumps(obj, ensure_ascii=False, indent=1).encode('utf-8')
        return self.upload_bytes(key, data)

    # ── 公网直链（供 latest/manifest 的 url 字段使用）──
    def public_url(self, key):
        return f'https://{self.bucket}.cos.{self.region}.myqcloud.com/{key}'
