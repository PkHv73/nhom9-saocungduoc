const http = require('http');
const https = require('https');
const path = require('path');

const JIRA_ENDPOINT = process.env.JIRA_ENDPOINT || 'https://endpoint-cca86e6d-4e6d-411d-8e2e-e6dc55b868a2.agentbase-runtime.aiplatform.vngcloud.vn';

// ── Excel export (exceljs — no Python needed) ──────────────────────────────
async function buildExcel(tickets) {
  const ExcelJS = require(path.join(__dirname, 'node_modules', 'exceljs'));
  const wb = new ExcelJS.Workbook();

  const HEADERS = ['Issue Key','Loại vấn đề','Root Cause','SLA Status','Ưu tiên','Escalate đến','Gợi ý xử lý CS'];
  const COL_W   = [16, 26, 28, 12, 10, 28, 65];

  const hdrFill  = { type:'pattern', pattern:'solid', fgColor:{argb:'FF1E3A5F'} };
  const hdrFont  = { name:'Arial', bold:true, color:{argb:'FFFFFFFF'}, size:10 };
  const thinBrd  = { style:'thin', color:{argb:'FFE2E8F0'} };
  const border   = { top:thinBrd, bottom:thinBrd, left:thinBrd, right:thinBrd };

  // ── Sheet 1: Chi tiết ────────────────────────────────────────────────────
  const ws = wb.addWorksheet('Chi tiết Tickets');
  ws.views = [{ state:'frozen', ySplit:1 }];

  ws.columns = HEADERS.map((h, i) => ({ header: h, width: COL_W[i] }));
  const hdrRow = ws.getRow(1);
  hdrRow.height = 30;
  HEADERS.forEach((_, ci) => {
    const c = hdrRow.getCell(ci + 1);
    c.font = hdrFont; c.fill = hdrFill; c.border = border;
    c.alignment = { horizontal:'center', vertical:'middle', wrapText:true };
  });

  tickets.forEach((t, idx) => {
    const isBreach = String(t.sla_status||'').toUpperCase() === 'BREACH';
    const isInfra  = String(t.root_cause||'').includes('Infrastructure');
    const isPrio   = !!t.priority_action;

    const fillColor = isBreach ? 'FFFFF0F0' : isInfra ? 'FFFFF8E7' : idx%2===0 ? 'FFF0F4FF' : 'FFFFFFFF';
    const rowFill = { type:'pattern', pattern:'solid', fgColor:{argb:fillColor} };

    const row = ws.addRow([
      t.key || '',
      t.type || '',
      t.root_cause || '',
      t.sla_status || 'OK',
      isPrio ? '🔥 Có' : 'Không',
      t.escalate_to || '',
      t.suggestion || t.error || '',
    ]);
    row.height = 45;

    row.eachCell((cell, ci) => {
      cell.fill = rowFill; cell.border = border;
      cell.alignment = { vertical:'top', wrapText:[2,3,6,7].includes(ci) };
      if (ci === 1) cell.font = { name:'Arial', size:9, bold:true, color:{argb:'FF1E3A5F'} };
      else if (ci === 4) cell.font = { name:'Arial', size:9, bold:true, color:{argb: isBreach?'FFDC2626':'FF166534'} };
      else if (ci === 5) cell.font = { name:'Arial', size:9, bold:isPrio, color:{argb: isPrio?'FFC05621':'FF374151'} };
      else cell.font = { name:'Arial', size:9 };
    });
  });

  // ── Sheet 2: Tổng kết ────────────────────────────────────────────────────
  const ws2 = wb.addWorksheet('Tổng kết');
  ws2.columns = [{ width:40 },{ width:18 }];

  const breach_n = tickets.filter(t => String(t.sla_status||'').toUpperCase()==='BREACH').length;
  const prio_n   = tickets.filter(t => t.priority_action).length;

  const rcCount  = {}, escCount = {};
  tickets.forEach(t => {
    const rc = t.root_cause || 'Unknown';
    rcCount[rc]  = (rcCount[rc]  || 0) + 1;
    if (t.escalate_to) escCount[t.escalate_to] = (escCount[t.escalate_to] || 0) + 1;
  });

  function addSectionHeader(ws, row, title) {
    ['A','B'].forEach(col => {
      const c = ws.getCell(`${col}${row}`);
      c.value = col==='A' ? title : '';
      c.fill = { type:'pattern', pattern:'solid', fgColor:{argb:'FF1E3A5F'} };
      c.font = { name:'Arial', bold:true, color:{argb:'FFFFFFFF'}, size:10 };
      c.alignment = { horizontal:'center', vertical:'middle' };
      c.border = border;
    });
    ws.getRow(row).height = 24;
  }

  function addKV(ws, row, k, v) {
    const ck = ws.getCell(`A${row}`);
    ck.value = k; ck.font = { name:'Arial', bold:true, size:10 };
    ck.fill = { type:'pattern', pattern:'solid', fgColor:{argb:'FFEFF6FF'} };
    ck.border = border; ck.alignment = { vertical:'middle' };
    const cv = ws.getCell(`B${row}`);
    cv.value = v; cv.font = { name:'Arial', bold:true, size:10 };
    cv.border = border; cv.alignment = { horizontal:'center', vertical:'middle' };
    ws.getRow(row).height = 20;
  }

  addSectionHeader(ws2, 1, 'Chỉ số'); ws2.getCell('B1').value = 'Giá trị';
  addKV(ws2, 2, 'Tổng số tickets', tickets.length);
  addKV(ws2, 3, 'SLA Breach', breach_n);
  addKV(ws2, 4, 'Cần ưu tiên xử lý', prio_n);
  addKV(ws2, 5, 'Tỷ lệ SLA Breach', tickets.length ? `${Math.round(breach_n/tickets.length*100)}%` : '0%');

  let r = 7;
  ws2.getCell(`A${r}`).value = 'Phân bố Root Cause';
  ws2.getCell(`A${r}`).font = { name:'Arial', bold:true, size:11, color:{argb:'FF1E3A5F'} };
  addSectionHeader(ws2, r+1, 'Root Cause'); ws2.getCell(`B${r+1}`).value = 'Số lượng';
  Object.entries(rcCount).sort((a,b)=>b[1]-a[1]).forEach(([k,v]) => { r++; addKV(ws2, r+1, k, v); });

  r += 3;
  ws2.getCell(`A${r}`).value = 'Phân bố Escalate';
  ws2.getCell(`A${r}`).font = { name:'Arial', bold:true, size:11, color:{argb:'FF1E3A5F'} };
  addSectionHeader(ws2, r+1, 'Team Escalate'); ws2.getCell(`B${r+1}`).value = 'Số tickets';
  Object.entries(escCount).sort((a,b)=>b[1]-a[1]).forEach(([k,v]) => { r++; addKV(ws2, r+1, k, v); });

  return wb.xlsx.writeBuffer();
}

// ── HTTP Server ────────────────────────────────────────────────────────────
const server = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  let body = '';
  req.on('data', chunk => body += chunk);
  req.on('end', async () => {

    // /analyze — forward to AgentBase
    if (req.method === 'POST' && req.url === '/analyze') {
      const url = new URL(JIRA_ENDPOINT);
      const options = {
        hostname: url.hostname, path: '/invocations', method: 'POST',
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
      // Timeout 10 phút — AgentBase xử lý nhiều tickets mất thời gian
      proxyReq.setTimeout(600000, () => {
        proxyReq.destroy();
        res.writeHead(504);
        res.end(JSON.stringify({ success: false, error: 'AgentBase timeout sau 10 phút' }));
      });
      proxyReq.on('error', err => {
        if (!res.headersSent) {
          res.writeHead(500);
          res.end(JSON.stringify({ success: false, error: err.message }));
        }
      });
      proxyReq.write(body); proxyReq.end();

    // /export — generate formatted Excel (pure Node.js)
    } else if (req.method === 'POST' && req.url === '/export') {
      try {
        const { tickets } = JSON.parse(body);
        const buf = await buildExcel(tickets || []);
        const date = new Date().toISOString().slice(0,10);
        res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
        res.setHeader('Content-Disposition', `attachment; filename="jira_analysis_${date}.xlsx"`);
        res.writeHead(200);
        res.end(Buffer.from(buf));
      } catch(e) {
        res.writeHead(500);
        res.end(JSON.stringify({ success: false, error: e.message }));
      }

    } else {
      res.writeHead(404); res.end('Not found');
    }
  });
});

server.listen(3002, () => {
  console.log('Jira Proxy running at http://localhost:3002');
  console.log('Forwarding /analyze -> ' + JIRA_ENDPOINT);
  console.log('Export /export -> Node.js exceljs (no Python needed)');
});
