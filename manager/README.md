# 贡献数据管理内核（manager）

面向开发团队的贡献数据审核 / 加工 / 推送流水线。纯内核（CLI），后续 GUI 封装直接调用同一层。

```
流水线：sync（感知新贡献）→ review（人工审核）→ export（导出原文，可选）
      → process（MinerU 解析 + agent 转候选变体）→ merge（合入官方变体库）
      → package（打数据包 + 版本自增 + 推送）→ archive（归档贡献）
```

## 一、环境配置（每位管理员）

1. **Python 3.10+**，在 `manager/` 目录内创建虚拟环境并安装依赖：
   ```bash
   python -m venv .venv
   .venv/Scripts/activate        # Windows；Linux/macOS: source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **配置**：复制 `.env.example` 为 `.env`，填入：
   - `COS_SECRET_ID / COS_SECRET_KEY / COS_BUCKET / COS_REGION`：腾讯云 COS 密钥（建议子账号 + 只授该桶权限）；
   - `MINERU_TOKEN`：在 [mineru.net](https://mineru.net) 注册后在「API Token」页申请；
   - `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL`：工作流 agent 使用的模型（默认小米 MiMo，可换 DeepSeek 等任意 OpenAI 兼容接口）；
   - `MAIN_REPO_PATH`：labreport-writer 主仓库本地克隆路径（默认 `..`），用于校验 `%%DATA` 合法键、合入 variants.json、打数据包；
   - `REVIEWER`：您的署名（多人区分）。
3. **没配密钥也能跑**：缺 COS 密钥时自动进入 dry 模式（本地 `workspace/cloud_mock/` 模拟桶、MinerU/agent 输出样例），适合先熟悉流程。

## 二、命令速查

| 命令 | 作用 |
|---|---|
| `python manager.py sync` | 列出云端全部贡献目录，**未登记的自动下载到 inbox 并标记 new**（上传频率无所谓，打开即知新数据） |
| `python manager.py review list [--status new]` | 查看各贡献的审核/处理状态 |
| `python manager.py review approve <目录>` / `review reject <目录> --note "原因"` | 人工审核第一关：通过后才能处理 |
| `python manager.py export <目录> [--to 路径]` | 把该贡献的照片/Word 原样导出本地 |
| `python manager.py process <目录>` | MinerU 解析 + agent 转候选变体（自动强校验，不过则带错误重试 ≤2 次） |
| `python manager.py merge <目录>` | 人工确认候选后合入主仓库 variants.json（去重） |
| `python manager.py validate <json> --exp <实验名>` | 独立校验一个变体 JSON |
| `python manager.py package --note "说明"` | 打数据包 → **dataVersion 自动 +1** → 上传 COS（用户端自动感知） |
| `python manager.py archive <目录>` | 已处理的贡献移入 contributions/processed/ |

全局参数：`--dry-run`（演练，不写云端）、`--reviewer 名字`。

目录参数形如 `contributions/reports/<实验名>/<时间戳>`（sync 输出里直接复制）。

## 三、状态与多人协作

- 状态统一存云端 `contributions/_meta/states.json`：`new → approved/rejected → processing → merged → done`；
- 乐观锁：他人先更新时您会收到「状态已被他人更新，请重新 sync 后重试」，重跑即可；
- 归档语义：`archive` 把贡献对象移动到 `contributions/processed/<kind>/<实验>/<时间戳>/`，states 保留 done 记录；
- 每位管理员用独立 `.env`（密钥不共用、REVIEWER 各填各的）。

## 四、典型一轮

```bash
python manager.py sync
python manager.py review list
python manager.py review approve contributions/reports/单摆法测重力加速度/20260912_143001 --note "照片清晰"
python manager.py process contributions/reports/单摆法测重力加速度/20260912_143001
#  ↑ 产出 workspace/drafts/reports/单摆法测重力加速度/20260912_143001/variants_candidate.json
#    人工打开检查（重点：公式、%%DATA 键、无个人信息）
python manager.py merge contributions/reports/单摆法测重力加速度/20260912_143001
git -C .. add 物理实验 && git -C .. commit -m "variants: 合入贡献变体"
python manager.py package --note "合入优秀报告变体"
python manager.py archive contributions/reports/单摆法测重力加速度/20260912_143001
```

## 五、强校验规则（validate / agent 输出必过）

- 章节键白名单：实验原理 / 实验方法 / 误差分析 / 结论（或 实验结论），每章 1～3 条，单条 40～1000 字；
- `$` 必须成对、禁止 `$$` 与 `\( \)`；
- `%%DATA:<键>:<格式>%%` 的键必须存在于该实验 `generate.py` 的 `_compute` 返回字典（自动 ast 提取）；
- 禁止姓名/学号/班级等个人信息；与官方现有变体相似度 ≥0.90 拒绝。

## 六、MinerU 接口说明

客户端封装于 `core/mineru.py`（申请批量上传链接 → PUT 文件 → 轮询 → 解包 full.md）。
请求/响应字段以官方文档为准：<https://mineru.net/apiManage/docs>；如官方调整，改 `core/mineru.py` 顶部常量即可。
