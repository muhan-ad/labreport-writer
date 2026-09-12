"""配置加载：.env → dict；dry 模式判定（缺密钥时自动降级为本地模拟）。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # manager/


def load_config() -> dict:
    """读取 manager/.env（存在时），返回配置字典。缺 COS 密钥时 dry=True（本地模拟外部服务）。"""
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / '.env')
    except ImportError:
        pass  # 未装 python-dotenv 时直接读环境变量

    cfg = {
        'cos_secret_id': os.getenv('COS_SECRET_ID', '').strip(),
        'cos_secret_key': os.getenv('COS_SECRET_KEY', '').strip(),
        'cos_bucket': os.getenv('COS_BUCKET', '').strip(),
        'cos_region': os.getenv('COS_REGION', 'ap-guangzhou').strip(),
        'mineru_token': os.getenv('MINERU_TOKEN', '').strip(),
        'llm_base_url': os.getenv('LLM_BASE_URL', 'https://api.xiaomimimo.com/v1').strip().rstrip('/'),
        'llm_api_key': os.getenv('LLM_API_KEY', '').strip(),
        'llm_model': os.getenv('LLM_MODEL', '').strip(),
        'reviewer': os.getenv('REVIEWER', os.getenv('USERNAME', 'unknown')).strip() or 'unknown',
        'main_repo': Path(os.getenv('MAIN_REPO_PATH', str(BASE_DIR.parent))).resolve(),
        'workspace': BASE_DIR / 'workspace',
    }
    cfg['dry'] = not (cfg['cos_secret_id'] and cfg['cos_secret_key'] and cfg['cos_bucket'])
    return cfg
