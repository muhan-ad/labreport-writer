'use strict';

// ═══════════════════════════════════════════════
// 贡献数据上传凭证函数（COS 预签名 PUT）
// 密钥只存在于本函数的环境变量中，永不进入客户端应用
// ═══════════════════════════════════════════════

const COS = require('cos-nodejs-sdk-v5');

const BUCKET = process.env.BUCKET || '';          // 如 labreport-1485394950-1250000000
const REGION = process.env.REGION || 'ap-guangzhou';
const SECRET_ID = process.env.SECRET_ID || '';
const SECRET_KEY = process.env.SECRET_KEY || '';
const EXPIRES = 600;                              // 预签名有效期 10 分钟

// 只允许贡献区两层目录结构：contributions/<variants|reports>/<实验名>/<文件名>
const KEY_RE = /^contributions\/(variants|reports)\/[^/]+\/[^/]+$/;

function getPutUrl(key) {
  return new Promise((resolve, reject) => {
    const cos = new COS({ SecretId: SECRET_ID, SecretKey: SECRET_KEY });
    cos.getObjectUrl({
      Bucket: BUCKET,
      Region: REGION,
      Key: key,
      Method: 'PUT',
      Expires: EXPIRES,
      Sign: true,
    }, (err, data) => {
      if (err) return reject(err);
      resolve(data.Url);
    });
  });
}

exports.main_handler = async (event) => {
  const headers = {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };
  const reply = (statusCode, obj) => ({ statusCode, headers, body: JSON.stringify(obj) });
  try {
    if (event && event.httpMethod === 'OPTIONS') return reply(200, { ok: true });
    if (!BUCKET || !SECRET_ID || !SECRET_KEY) {
      return reply(500, { ok: false, error: '函数环境变量未配置' });
    }
    let keys = [];
    try {
      const body = JSON.parse((event && typeof event.body === 'string') ? event.body : '{}');
      keys = Array.isArray(body.keys) ? body.keys : [];
    } catch (e) {
      return reply(400, { ok: false, error: '请求体必须是 JSON' });
    }
    if (!keys.length || keys.length > 20) {
      return reply(400, { ok: false, error: 'keys 数量应为 1-20' });
    }
    const valid = [];
    for (const k of keys) {
      if (typeof k !== 'string' || !KEY_RE.test(k)) {
        return reply(400, { ok: false, error: '非法路径：' + String(k).slice(0, 120) });
      }
      valid.push(k);
    }
    const items = [];
    for (const k of valid) {
      items.push({ key: k, putUrl: await getPutUrl(k) });
    }
    return reply(200, { ok: true, items, expires: EXPIRES });
  } catch (err) {
    return reply(500, { ok: false, error: err.message });
  }
};