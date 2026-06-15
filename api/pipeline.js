const https = require('https');

const ENDPOINT = 'endpoint-b89daaf7-6f9c-43fb-9775-cf7a61aaa915.agentbase-runtime.aiplatform.vngcloud.vn';

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') { res.status(204).end(); return; }
  if (req.method !== 'POST') { res.status(405).end(); return; }

  const body = JSON.stringify(req.body);

  await new Promise((resolve, reject) => {
    const options = {
      hostname: ENDPOINT,
      path: '/invocations',
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) }
    };
    const proxyReq = https.request(options, proxyRes => {
      let data = '';
      proxyRes.on('data', chunk => data += chunk);
      proxyRes.on('end', () => {
        res.status(proxyRes.statusCode).json(JSON.parse(data));
        resolve();
      });
    });
    proxyReq.on('error', err => { res.status(500).json({ error: err.message }); resolve(); });
    proxyReq.write(body);
    proxyReq.end();
  });
};
