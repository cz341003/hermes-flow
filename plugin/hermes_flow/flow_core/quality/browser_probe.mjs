// HERMES Flow browser probe: zero-dependency Chrome DevTools Protocol.
// Usage: node browser_probe.mjs <baseUrl> <routesJson> <outDir> <chromePath> [timeoutMs]
const [, , baseUrl, routesJson, outDir, chromePath, timeoutArg] = process.argv;
const routes = JSON.parse(routesJson);
const timeoutMs = Number(timeoutArg || 120000);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const fs = await import('node:fs');
const path = await import('node:path');
const { spawn } = await import('node:child_process');

const PORT = 9333 + Math.floor(Math.random() * 500);
const profile = path.join(outDir, `.chrome-${Date.now()}`);
fs.mkdirSync(profile, { recursive: true });

const chrome = spawn(chromePath, [
  '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage',
  '--disable-crash-reporter', '--disable-breakpad', '--hide-scrollbars',
  '--no-first-run', '--no-default-browser-check', '--mute-audio',
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  '--window-size=1440,900', 'about:blank',
], { stdio: 'ignore', windowsHide: true });

let ws;
let msgId = 0;
const pending = new Map();
const listeners = new Map();
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++msgId;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
    setTimeout(() => { if (pending.has(id)) { pending.delete(id); reject(new Error(`CDP timeout ${method}`)); } }, 15000);
  });
}
function on(event, fn) {
  if (!listeners.has(event)) listeners.set(event, []);
  listeners.get(event).push(fn);
}
function emit(event, params) {
  for (const fn of listeners.get(event) || []) { try { fn(params); } catch {} }
}

let page;
for (let i = 0; i < 80; i++) {
  try {
    const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
    page = list.find((t) => t.type === 'page');
    if (page) break;
  } catch {}
  await sleep(250);
}
if (!page) { console.log(JSON.stringify({ ran: false, ok: false, error: 'chrome target unavailable' })); chrome.kill(); process.exit(2); }

ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
ws.onmessage = (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(msg.error.message)); else resolve(msg.result);
  } else if (msg.method) emit(msg.method, msg.params || {});
};

await send('Page.enable');
await send('Runtime.enable');
await send('Log.enable');
await send('Network.enable');

const results = [];
const deadline = Date.now() + timeoutMs;
try {
  for (const route of routes) {
    if (Date.now() > deadline) { results.push({ route, ok: false, error: 'probe deadline' }); continue; }
    const consoleErrors = [], pageErrors = [], networkErrors = [], warnings = [], http404 = [];
    const onConsole = (p) => {
      if (p.type === 'error') consoleErrors.push((p.args || []).map((a) => a.description || a.value || a.type).join(' ').slice(0, 500));
      else if (p.type === 'warning') warnings.push((p.args || []).map((a) => a.description || a.value || '').join(' ').slice(0, 300));
    };
    const onException = (p) => pageErrors.push((p.exceptionDetails?.exception?.description || p.exceptionDetails?.text || 'exception').slice(0, 800));
    const onLog = (p) => { if (p.entry?.level === 'error') consoleErrors.push(String(p.entry.text).slice(0, 500)); };
    const onNet = (p) => { if (p.errorText) networkErrors.push(`${p.errorText} ${p.type || ''}`.slice(0, 300)); };
    const onResponse = (p) => { if (p.response?.status === 404) http404.push(String(p.response.url || '')); };
    on('Runtime.consoleAPICalled', onConsole);
    on('Runtime.exceptionThrown', onException);
    on('Log.entryAdded', onLog);
    on('Network.loadingFailed', onNet);
    on('Network.responseReceived', onResponse);
    try {
      await send('Page.navigate', { url: baseUrl.replace(/\/$/, '') + route });
      await sleep(3500);
      const evalRes = await send('Runtime.evaluate', {
        expression: `(() => ({
          title: document.title || '',
          url: location.href,
          appText: (document.querySelector('#app')?.innerText || document.body?.innerText || '').trim().slice(0, 500),
          appNodes: document.querySelector('#app')?.querySelectorAll('*')?.length || 0,
          bodyLen: (document.body?.innerText || '').length
        }))()`,
        returnByValue: true,
      });
      const value = evalRes.result?.value || {};
      // 浏览器会无条件请求 /favicon.ico；没有 favicon 的 404 不是应用错误。
      const faviconOnly404 = http404.length > 0 && http404.every((u) => /favicon\.ico/i.test(u));
      const filteredConsoleErrors = faviconOnly404
        ? consoleErrors.filter((e) => !/Failed to load resource: the server responded with a status of 404/i.test(e))
        : consoleErrors;
      const filteredNetworkErrors = faviconOnly404
        ? networkErrors.filter((e) => !/favicon\.ico/i.test(e))
        : networkErrors;
      const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
      const safe = route.replace(/[^a-zA-Z0-9]+/g, '_') || 'root';
      const shotPath = path.join(outDir, `browser-${safe}.png`);
      fs.writeFileSync(shotPath, Buffer.from(shot.data, 'base64'));
      const ok = Boolean(value.appNodes > 0) && Boolean(value.appText) && pageErrors.length === 0 && filteredConsoleErrors.length === 0 && filteredNetworkErrors.length === 0;
      results.push({ route, ok, title: value.title, url: value.url, appNodes: value.appNodes,
        appText: value.appText, bodyLen: value.bodyLen, screenshot: shotPath,
        consoleErrors: filteredConsoleErrors, pageErrors, networkErrors: filteredNetworkErrors,
        http404, warnings: warnings.slice(0, 10) });
    } catch (e) {
      results.push({ route, ok: false, error: String(e).slice(0, 800) });
    } finally {
      for (const ev of ['Runtime.consoleAPICalled', 'Runtime.exceptionThrown', 'Log.entryAdded', 'Network.loadingFailed', 'Network.responseReceived']) {
        const arr = listeners.get(ev) || [];
        for (const fn of [onConsole, onException, onLog, onNet, onResponse]) {
          const i = arr.indexOf(fn); if (i >= 0) arr.splice(i, 1);
        }
      }
    }
  }
} finally {
  try { ws.close(); } catch {}
  try { chrome.kill(); } catch {}
  try { fs.rmSync(profile, { recursive: true, force: true }); } catch {}
}
const ok = results.length > 0 && results.every((r) => r.ok);
console.log(JSON.stringify({ ran: true, ok, routes: results, baseUrl }));
process.exit(ok ? 0 : 1);
