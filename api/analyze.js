const https = require('https');

const ENDPOINT = 'endpoint-cca86e6d-4e6d-411d-8e2e-e6dc55b868a2.agentbase-runtime.aiplatform.vngcloud.vn';

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') { res.status(204).end(); return; }
  if (req.method !== 'POST') { res.status(405).end(); return; }

  const body = JSON.stringify(req.body);

  await new Promise((resolve) => {
    const options = {
      hostname: ENDPOINT,
      path: '/invocations',
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
      timeout: 600000
    };
    const proxyReq = https.request(options, proxyRes => {
      let data = '';
      proxyRes.on('data', chunk => data += chunk);
      proxyRes.on('end', () => {
        try { res.status(proxyRes.statusCode).json(JSON.parse(data)); }
        catch(e) { res.status(500).json({ error: 'Invalid JSON from upstream' }); }
        resolve();
      });
    });
    proxyReq.on('error', err => { res.status(500).json({ error: err.message }); resolve(); });
    proxyReq.write(body);
    proxyReq.end();
  });
};
