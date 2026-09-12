# 贡献数据上传凭证云函数 — 部署指引

给「贡献数据」功能签发放上传凭证的腾讯云函数（SCF）。签名密钥只存在函数的环境变量里，
客户端应用只拿到 10 分钟有效的预签名 PUT 地址，拿不到任何密钥。

## 一、创建函数（约 5 分钟）

1. 打开腾讯云控制台 → 云函数 SCF → 新建函数；
2. 基本配置：
   - 创建方式：**从头开始**；
   - 函数类型：事件函数；
   - 运行环境：**Node.js 16 或 18**；
   - 函数名称：如 `contribute-credentials`；
3. 创建后进入「函数代码」页，把本目录的 `index.js` 内容粘贴替换；
4. 安装依赖（二选一）：
   - 方式 A（推荐，免 zip）：编辑器下方「在线安装依赖」输入 `cos-nodejs-sdk-v5` 并执行；
   - 方式 B：本地 `npm install cos-nodejs-sdk-v5`，把 `index.js + package.json + node_modules` 打包 zip 上传。

## 二、配置环境变量（函数配置 → 环境变量）

| 变量名 | 值 |
|---|---|
| `SECRET_ID` | 腾讯云 API 密钥 SecretId |
| `SECRET_KEY` | 腾讯云 API 密钥 SecretKey |
| `BUCKET` | COS 桶全名（如 `labreport-1485394950-1250000000`，带 APPID 后缀） |
| `REGION` | 桶所在园区（如 `ap-guangzhou`） |

> 建议：为这个函数单独建一个**子账号密钥**（CAM），只授予下表的最小写权限，避免使用主账号密钥。

## 三、开启访问入口（函数 URL，免 API 网关）

1. 函数配置 → 触发器 → 创建触发器 → 触发方式选「**函数 URL**」；
2. 鉴权类型：**免鉴权**（应用直接 POST 调用，函数自身只发预签名、无泄露风险）；
3. 创建后复制生成的访问地址，形如：
   `https://<env>.scf.<region>.tencentcs.com/release/contribute-credentials`

## 四、把地址填回应用

编辑应用源码 `main.js` 中的常量：

```js
const CONTRIBUTE_FN_URL = 'https://<env>.scf.<region>.tencentcs.com/release/contribute-credentials';
```

重新打包发布后，「贡献数据」上传即可用。

## 五、联调测试

```bash
curl -X POST "https://<env>.scf.<region>.tencentcs.com/release/contribute-credentials" \
  -H "Content-Type: application/json" \
  -d '{"keys":["contributions/reports/测试实验/20260101_000000/manifest.json"]}'
```

正常返回：

```json
{"ok":true,"items":[{"key":"contributions/reports/测试实验/20260101_000000/manifest.json","putUrl":"https://xxx.cos.ap-guangzhou.myqcloud.com/...?q-sign-algorithm=..."}],"expires":600}
```

拿到 `putUrl` 后可顺手验证直传：

```bash
curl -X PUT --upload-file manifest.json "<putUrl>"
```

## 六、安全边界（已内置）

- key 必须匹配 `contributions/(variants|reports)/<实验名>/<文件名>`，其它任何路径一律 400 拒绝；
- 单次请求最多 20 个 key；签名有效期 10 分钟；
- 上传走 COS 上行流量（免费）；此函数月调用几千次规模在免费额度内，费用为 0；
- 密钥永不进入应用安装包（客户端只接触预签名 URL）。

## 附：CAM 子账号最小权限示例

```json
{
  "version": "2.0",
  "statement": [
    {
      "effect": "allow",
      "action": ["cos:PutObject"],
      "resource": ["qcs::cos:ap-guangzhou:uid/1250000000:*/*/contributions/*"]
    }
  ]
}
```

（`uid/1250000000` 与桶全名按您的实际账号修改。）