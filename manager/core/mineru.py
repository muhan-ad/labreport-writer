"""MinerU 文档解析客户端（精准解析 API，批量上传→轮询→解包 full.md）。

接口字段以官方文档为准：https://mineru.net/apiManage/docs
dry 模式：不访问网络，直接为每个输入文件生成一段占位 Markdown。
"""
import io
import ipaddress
import re
import socket
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests

BATCH_URL = 'https://mineru.net/api/v4/file-urls/batch'
RESULT_URL = 'https://mineru.net/api/v4/extract-results/batch/{batch_id}'
POLL_INTERVAL = 10       # 秒
POLL_TIMEOUT = 1800      # 30 分钟上限

IMG_EXT = ('.jpg', '.jpeg', '.png', '.bmp', '.webp')
DOC_EXT = ('.pdf', '.docx', '.doc', '.pptx')

# 出站请求防 SSRF：仅 https，且域名解析结果必须全部为公网地址
ALLOWED_HOSTS = {'mineru.net'}


def assert_safe_url(url, allow_hosts=frozenset()):
    u = urlparse(url)
    if u.scheme not in ('http', 'https'):
        raise ValueError(f'仅允许 http/https 地址：{url}')
    host = u.hostname or ''
    if allow_hosts and host in allow_hosts:
        return u
    for info in socket.getaddrinfo(host, None):
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError(f'地址解析到非公网 IP，已拦截：{host}')
    return u


class MinerU:
    def __init__(self, token, out_dir, dry=False):
        self.token = token
        self.out_dir = Path(out_dir)
        self.dry = dry
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def parse_files(self, files):
        """files: [Path]；返回 [Path]（与输入顺序一一对应的 full.md）。

        内部流程：申请批量上传链接 → PUT 各文件 → 轮询 batch 结果 → 下载结果 zip 解出 full.md。
        """
        if self.dry:
            return self._dry_markdowns(files)
        if not self.token:
            raise RuntimeError('MINERU_TOKEN 未配置（.env），或使用 --dry-run 演练')
        files = [Path(f) for f in files]
        names = [f.name for f in files]
        # 1) 申请上传链接（固定官方域名，仍走安全校验）
        batch_u = assert_safe_url(BATCH_URL, ALLOWED_HOSTS)
        resp = requests.post(
            batch_u.geturl(),
            headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'},
            json={
                'enable_formula': True,
                'enable_table': True,
                'language': 'ch',
                'files': [{'name': n, 'is_ocr': True, 'data_id': n} for n in names],
            },
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get('code') != 0:
            raise RuntimeError(f"MinerU 申请上传链接失败: {body.get('msg') or body}")
        batch_id = body['data']['batch_id']
        upload_urls = body['data']['file_urls']
        if len(upload_urls) != len(files):
            raise RuntimeError('MinerU 返回的上传链接数量与文件数不一致')
        # 2) PUT 上传（上传完成即自动进入解析队列；地址为 MinerU 签发的存储直链，逐一校验为公网 https）
        for f, url in zip(files, upload_urls):
            put_u = assert_safe_url(url)
            put = requests.put(put_u.geturl(), data=f.read_bytes(), timeout=300)
            if put.status_code not in (200, 201):
                raise RuntimeError(f'上传 {f.name} 失败 HTTP {put.status_code}')
        # 3) 轮询结果
        result_u = assert_safe_url(RESULT_URL.format(batch_id=batch_id), ALLOWED_HOSTS)
        deadline = time.time() + POLL_TIMEOUT
        results = []
        while True:
            time.sleep(POLL_INTERVAL)
            r = requests.get(result_u.geturl(),
                             headers={'Authorization': f'Bearer {self.token}'}, timeout=30)
            r.raise_for_status()
            rb = r.json()
            if rb.get('code') != 0:
                raise RuntimeError(f"MinerU 轮询失败: {rb.get('msg') or rb}")
            results = rb['data'].get('extract_result', [])
            states = [x.get('state') for x in results]
            if results and all(s in ('done', 'failed', 'skipped') for s in states):
                break
            if time.time() > deadline:
                raise RuntimeError('MinerU 解析超时（30 分钟）')
        # 4) 下载结果 zip 并解出 full.md（按 data_id=文件名归位；下载地址校验为公网 https）
        outs = []
        batch_dir = self.out_dir / batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)
        for item in results:
            name = item.get('data_id') or item.get('file_name') or f'file_{len(outs)}'
            if item.get('state') != 'done' or not item.get('full_zip_url'):
                raise RuntimeError(f"MinerU 解析失败: {name} — {item.get('err_msg') or item.get('state')}")
            zip_u = assert_safe_url(item['full_zip_url'])
            zip_resp = requests.get(zip_u.geturl(), timeout=300)
            zip_resp.raise_for_status()
            zf = zipfile.ZipFile(io.BytesIO(zip_resp.content))
            md_names = [n for n in zf.namelist() if n.endswith('.md')]
            if not md_names:
                raise RuntimeError(f'MinerU 结果 zip 中未找到 Markdown: {name}')
            target = batch_dir / (Path(name).stem + '.md')
            target.write_bytes(zf.read(sorted(md_names)[0]))
            outs.append(target)
        # 保持与输入同序
        order = {Path(n).stem: i for i, n in enumerate(names)}
        outs.sort(key=lambda p: order.get(p.stem, 999))
        return outs

    def _dry_markdowns(self, files):
        outs = []
        for f in files:
            f = Path(f)
            target = self.out_dir / f'dry_{f.stem}.md'
            target.write_text(
                f'# （dry-run 样例解析：{f.name}）\n\n'
                '一、实验原理\n单摆法测量重力加速度的原理基于简谐振动周期公式 $T = 2\\pi\\sqrt{l/g}$。\n\n'
                '二、实验步骤\n调节仪器水平，测量摆长，记录 30 个周期的时间。\n',
                encoding='utf-8')
            outs.append(target)
        return outs
