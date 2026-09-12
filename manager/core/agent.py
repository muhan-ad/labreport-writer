"""工作流 agent：MinerU Markdown → 变体候选 JSON（OpenAI 兼容接口，默认 MiMo）。"""
import json
import re
from pathlib import Path

import requests

PROMPT_PATH = Path(__file__).resolve().parent.parent / 'prompts' / 'variant_system.md'
MAX_RETRY = 2


class VariantAgent:
    def __init__(self, cfg, dry=False):
        self.base = cfg['llm_base_url']
        self.key = cfg['llm_api_key']
        self.model = cfg['llm_model'] or 'mimo'
        self.dry = dry
        self.system = PROMPT_PATH.read_text(encoding='utf-8')

    def _chat(self, messages):
        resp = requests.post(
            f'{self.base}/chat/completions',
            headers={'Authorization': f'Bearer {self.key}', 'Content-Type': 'application/json'},
            json={'model': self.model, 'messages': messages, 'temperature': 0.4},
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content']

    @staticmethod
    def _parse_json(text):
        """剥掉可能的 ```json 围栏后解析。"""
        text = text.strip()
        m = re.match(r'^```(?:json)?\s*([\s\S]*?)\s*```$', text)
        if m:
            text = m.group(1)
        return json.loads(text)

    def markdown_to_variants(self, markdown, exp_id, allowed_keys, existing_variants):
        """返回 (候选 dict, 错误列表)。错误非空表示重试后仍未通过强校验。"""
        if self.dry or not self.key:
            keys = sorted(allowed_keys) or ['demo_mean', 'demo_err']
            k1 = keys[0]
            k2 = keys[1] if len(keys) > 1 else k1
            candidate = {
                '实验原理': [
                    f'（dry-run 样例）本实验依据理论公式推导测量目标量，核心关系如 $T = 2\\pi\\sqrt{{l/g}}$ 所示，'
                    f'通过对多组原始读数的处理可得最终结果 %%DATA:{k1}:%.4f%%。'
                    '实验中需严格控制近似条件，并采用多次测量取平均的方法减小偶然误差，保证结果的可靠性。'
                ],
                '误差分析': [
                    f'（dry-run 样例）主要误差来源包括仪器读数误差与计时启停反应误差，'
                    f'其中仪器允差贡献为 %%DATA:{k2}:%.2f%%，按误差传递公式合成后得到合成不确定度，'
                    '再与公认值比较给出相对误差并分析偏差来源。'
                ],
            }
            return candidate, []
        system = self.system.format(
            exp_id=exp_id,
            allowed_keys=json.dumps(sorted(allowed_keys), ensure_ascii=False),
            existing=json.dumps(existing_variants or {}, ensure_ascii=False)[:2000],
        )
        messages = [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': '待加工的解析 Markdown：\n\n' + markdown},
        ]
        errors = []
        for attempt in range(MAX_RETRY + 1):
            content = self._chat(messages)
            try:
                candidate = self._parse_json(content)
            except json.JSONDecodeError as e:
                errors = [f'输出不是合法 JSON：{e}']
            else:
                errors = self._validate(candidate, exp_id, allowed_keys, existing_variants)
                if not errors:
                    return candidate, []
            messages.append({'role': 'assistant', 'content': content})
            messages.append({'role': 'user', 'content': '你的输出未通过校验：\n- ' + '\n- '.join(errors)
                             + '\n请严格按系统规则重新输出完整 JSON。'})
        return candidate if 'candidate' in dir() else {}, errors

    def _validate(self, candidate, exp_id, allowed_keys, existing_variants):
        """调用 manager.core.validate（延迟导入避免循环依赖由 CLI 层组装）。"""
        from .validate import validate_variants
        return validate_variants(candidate, allowed_keys, existing_variants)
