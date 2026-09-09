# 实验报告自动编写（labreport-writer）

大学物理实验报告自动生成桌面应用。选择实验 → 在结构化表单里填测量数据 → 一键调用 Python 脚本、通过 Word COM 生成可提交的 `.docx` 实验报告（含公式、三线表、图表、不确定度计算），并支持 AI 润色（限定教材知识库）与措辞变体。

- 技术栈：Electron（主进程 Node + 渲染层原生 JS）+ Python 数据处理 + `win32com` 驱动 Word 生成 `.docx`。
- 数据模型（方式三）：每个实验以 `schema.json`（字段/类型/量纲/知识库标签）+ `data.json`（填写的数据真相）为核心，**不再用 Excel 坐标硬编码**；`generate.py` 读 `data["key"]`。
- 知识库：每个实验 `rag/原理.md` 存教材原理，供 AI 润色作为唯一依据约束。

## 一、普通用户：下载安装包用（推荐）

1. 打开 Releases：https://github.com/muhan-ad/labreport-writer/releases
2. 下载 `实验报告编写 Setup 1.0.0.exe`，双击安装（用户级，免管理员）。
3. 桌面/开始菜单打开「实验报告编写」，选实验 → 填数据 → 保存 → 生成报告。

安装包**已内置 Python 运行时与全部实验数据/脚本/知识库**，对方机器**无需安装 Python 或任何依赖**。

## 二、开发者：源码运行

环境要求：
- Node.js（建议 18+）
- 二选一：仓库根放置 `python-runtime/`（嵌入式 Python 3.14），或本机安装 **Python ≥ 3.10（建议 3.12+）** 及依赖。

```bash
npm install
# 若用本机 Python，先装依赖（自动探测/安装 Python + pip 依赖）：
#   Windows: 双击 物理实验/setup.bat
#   或:      pip install -r 物理实验/requirements.txt
npm start
```

`resolvePythonExe` 优先级：内置 `python-runtime` → 本机 Python（Store / 常见目录 / PATH）。

## 三、打包

```bash
npm run build:win
```
产出 `dist/实验报告编写 Setup x.x.x.exe`（NSIS 安装包）与 `dist/win-unpacked/`（绿色版）。
`物理实验`（脚本/数据/schema/知识库/变体）与 `python-runtime` 作为 extraResources 打进可写的安装目录，实现自包含。

## 四、质量校验（不启动 Word 的静态冒烟）

```bash
python smoke_test.py        # 26 实验：语法 / schema-data 校验 / 变体每节数与 $ 配对 / 占位符键存在 / rag 存在
python validate_schema.py   # 各实验 data.json 相对 schema 的 missing/invalid
```

## 五、项目结构

```
main.js / preload.js       Electron 主进程与预加载
src/                        渲染层（index.html / renderer.js / style.css）
物理实验/实验脚本/
  common/                   公共库（docx_report / uncertainty / regression / latex_formatter / plot_utils / variants / data_io）
  <实验名>/
    generate.py             该实验数据处理 + 报告生成（读 data.json）
    schema.json             数据模型定义（字段/类型/量纲/知识库标题）
    data.json               测量数据（真相）
    variants.json           报告措辞变体（可选）
    rag/原理.md             教材原理知识库（AI 润色依据）
```

## 六、注意事项

- **不要直接提交安装包里的示例数据**：仓库/安装包内的 `data.json` 为**测试示例数据**，仅供演示，请勿当真实测量结果提交。
- 学校要求提交 Word（`.docx`），纯中文；实验原理以教材为准。
- 仓库不纳入 `node_modules/`、`python-runtime/`、`dist/`、`backup/`、生成物（`__pycache__`、`*.pyc`、报告 `*.docx`、图表 `*.png`）。

## 许可

仅用于学习交流。实验数据与公式来自西安电子科技大学物理实验课程。
