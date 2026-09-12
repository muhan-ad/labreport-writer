# 发布更新流程（供开发者使用）

应用内置「检查更新」功能：读取一份**公网可访问的更新清单 `latest.json`**（版本号 + 安装包直链），
发现新版本后自动下载并打开安装程序。

更新清单与安装包建议放在**国内对象存储（腾讯云 COS / 阿里云 OSS）**：
国内 CDN 高速直连、默认域名免备案、无单文件大小限制（安装包 164MB、以后更大都不受影响）、
免费额度足够个人项目使用（超量后每月成本约几毛钱）。

## 发布步骤（每次发版）

1. **改版本号**：编辑 `package.json` 的 `version` 字段（如 `1.5.1`）；
2. **打包**：`npm run build:win`，产物为 `dist/实验报告编写 Setup <版本>.exe`，
   同时复制一份英文名 `dist/labreport-setup-<版本>.exe`（latest.json 指向英文名，避免 URL 编码问题）；
3. **上传 3 个文件**到 COS/OSS 桶（覆盖旧版本同名文件即可）：

   | 文件 | 说明 |
   |---|---|
   | `labreport-setup-<版本>.exe` | 安装包（应用整体更新） |
   | `latest.json` | 更新清单（指向安装包） |
   | `data-package-<数据版本>.zip` 与 `data-manifest.json` | 实验数据包 + 数据清单 |

   `latest.json` 示例：
   ```json
   {
     "version": "1.5.1",
     "notes": "本次更新内容：\n1. 修复……\n2. 新增……",
     "url": "https://labreport-1485394950.cos.ap-guangzhou.myqcloud.com/labreport-setup-1.5.1.exe",
     "fileName": "labreport-setup-1.5.1.exe"
   }
   ```
4. 完成。用户应用内「设置 → 检查更新」→ 自动发现新版本 → 自动下载 → 自动打开安装程序。

## 实验数据热更新（改变体/知识库/新增实验，无需重装）

实验数据（约 0.7MB 的 zip）与安装包（约 164MB）分开更新。
**数据版本独立于应用版本**：应用内置数据版本为 `1.0.0`，数据包每次发布时可在 `1.0.0` 基础上递增
（如 `1.0.1`、`1.1.0`），应用内「检查实验数据更新」按数据版本号比较。

1. **打包数据包**（在项目根目录执行；`DVER` 为本次数据版本号，如 `1.0.1`）：
   ```bash
   python -c "import os,sys,zipfile,json; ROOT=os.getcwd(); SRC=os.path.join(ROOT,'物理实验','实验脚本'); DIST=os.path.join(ROOT,'dist'); DVER='1.0.1'; zp=os.path.join(DIST,f'data-package-{DVER}.zip'); c=0
   import io
   zf=zipfile.ZipFile(zp,'w',zipfile.ZIP_DEFLATED)
   for dp,dn,fns in os.walk(os.path.realpath(SRC)):
       dn[:]=[d for d in dn if d!='__pycache__']
       for fn in fns:
           if fn.lower().endswith(('.docx','.png','.xlsx','.xls','.pdf')) or fn=='.lab_sections.json': continue
           full=os.path.realpath(os.path.join(dp,fn))
           if not full.startswith(os.path.realpath(SRC)+os.sep): raise SystemExit('越界')
           zf.writestr(os.path.join('实验脚本',os.path.relpath(full,os.path.realpath(SRC))),open(full,'rb').read()); c+=1
   zf.close(); print(zp, c)"
   ```
   （产物为 `dist/data-package-<数据版本>.zip`，约 0.7MB；内含每个实验的 `sample.json`——「填入默认数据」恢复的内置测试数据快照，随包同步更新）
2. **更新清单** `data-manifest.json`（同桶，覆盖上传）：
   ```json
   {
     "dataVersion": "1.0.1",
     "notes": "本次实验数据更新说明",
     "url": "https://labreport-1485394950.cos.ap-guangzhou.myqcloud.com/data-package-1.0.1.zip"
   }
   ```
3. 用户应用内「设置 → 检查更新 → 检查实验数据更新」→ 下载 → 应用，**无需重装应用**。

合并规则：用户的测量数据 `data.json` 永不覆盖；用户改过的 `variants.json` 保留本地版本；
`sample.json`（内置测试数据）、公共库、原理知识库、脚本直接更新。

## 首次配置（一次性）

应用「设置 → 检查更新」→ 填写 `latest.json` 的完整 URL（须为公网 http/https 地址，
本地/内网地址会被自动拒绝），保存后持久生效。

## 检查更新原理

- GET 清单 → 比对 `version` 与本地版本 → 有新版本即自动下载 `url`，进度实时显示；
- 下载完成后自动打开安装程序；可随时点「稍后再说」取消下载；
- 安全检查：更新/下载地址仅允许公网 http/https，自动拒绝 localhost、内网、私有与保留地址
  （域名解析后再次核验）。
