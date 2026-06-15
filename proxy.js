const http = require('http');
const https = require('https');

const AGENT_ENDPOINT = 'https://endpoint-b89daaf7-6f9c-43fb-9775-cf7a61aaa915.agentbase-runtime.aiplatform.vngcloud.vn';

const server = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  if (req.method === 'POST' && req.url === '/invocations') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      const options = {
        hostname: 'endpoint-b89daaf7-6f9c-43fb-9775-cf7a61aaa915.agentbase-runtime.aiplatform.vngcloud.vn',
        path: '/invocations',
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) }
      };

      const proxyReq = https.request(options, proxyRes => {
        let data = '';
        proxyRes.on('data', chunk => data += chunk);
        proxyRes.on('end', () => {
          res.setHeader('Content-Type', 'application/json');
          res.writeHead(proxyRes.statusCode);
          res.end(data);
        });
      });

      proxyReq.on('error', err => {
        res.writeHead(500);
        res.end(JSON.stringify({ error: err.message }));
      });

      proxyReq.write(body);
      proxyReq.end();
    });
  } else {
    res.writeHead(404);
    res.end('Not found');
  }
});

server.listen(3001, () => {
  console.log('Proxy running at http://localhost:3001');
  console.log('Forwarding /invocations -> ' + AGENT_ENDPOINT);
});
