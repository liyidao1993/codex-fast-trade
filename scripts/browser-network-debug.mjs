import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';

const EDGE_PATH =
  process.env.EDGE_PATH ||
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const APP_URL = process.env.APP_URL || 'http://127.0.0.1:18081/';
const PORT = Number(process.env.CDP_PORT || 9340);
const PROFILE_DIR = path.resolve('data', 'edge-network-debug');
const PIN = process.env.APP_PIN || '123456';
const OUTPUT = path.resolve('docs', 'browser-network-debug.json');

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForJson(url, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return await response.json();
    } catch (error) {
      lastError = error;
    }
    await sleep(250);
  }
  throw lastError || new Error(`Timed out waiting for ${url}`);
}

async function waitForPageTarget(timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const targets = await waitForJson(`http://127.0.0.1:${PORT}/json/list`, 2000);
    const target = targets.find((item) => item.type === 'page' && item.webSocketDebuggerUrl);
    if (target) return target;
    await sleep(250);
  }
  throw new Error('Timed out waiting for a debuggable page target');
}

class CdpClient {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
    socket.addEventListener('message', (event) => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(message.error.message));
        else pending.resolve(message.result);
        return;
      }
      const listeners = this.listeners.get(message.method) || [];
      for (const listener of listeners) listener(message.params || {});
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    this.socket.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) || [];
    listeners.push(listener);
    this.listeners.set(method, listeners);
  }

  close() {
    this.socket.close();
  }
}

async function evaluate(cdp, expression) {
  const result = await cdp.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.text || 'Runtime evaluation failed');
  }
  return result.result.value;
}

async function waitFor(cdp, expression, timeoutMs = 12000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await evaluate(cdp, expression);
    if (value) return value;
    await sleep(300);
  }
  throw new Error(`Timed out waiting for expression: ${expression}`);
}

async function main() {
  await fs.rm(PROFILE_DIR, { recursive: true, force: true });
  await fs.mkdir(PROFILE_DIR, { recursive: true });
  const network = [];
  const consoleLogs = [];
  const tracked = new Map();
  const edge = spawn(EDGE_PATH, [
    '--headless=new',
    '--disable-gpu',
    '--no-first-run',
    `--user-data-dir=${PROFILE_DIR}`,
    `--remote-debugging-port=${PORT}`,
    APP_URL,
  ], { stdio: ['ignore', 'ignore', 'ignore'] });

  try {
    await waitForJson(`http://127.0.0.1:${PORT}/json/version`);
    const target = await waitForPageTarget();
    const socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      socket.addEventListener('open', resolve, { once: true });
      socket.addEventListener('error', reject, { once: true });
    });
    const cdp = new CdpClient(socket);
    await cdp.send('Runtime.enable');
    await cdp.send('Network.enable');
    cdp.on('Runtime.consoleAPICalled', (params) => {
      consoleLogs.push({
        type: params.type,
        args: (params.args || []).map((arg) => arg.value ?? arg.description ?? '').join(' '),
      });
    });
    cdp.on('Network.requestWillBeSent', (params) => {
      if (!params.request?.url?.includes('/api/v1/')) return;
      tracked.set(params.requestId, {
        requestId: params.requestId,
        method: params.request.method,
        url: params.request.url,
      });
    });
    cdp.on('Network.responseReceived', (params) => {
      const item = tracked.get(params.requestId);
      if (!item) return;
      item.status = params.response.status;
      item.statusText = params.response.statusText;
      item.mimeType = params.response.mimeType;
      item.fromDiskCache = params.response.fromDiskCache;
    });
    cdp.on('Network.loadingFinished', async (params) => {
      const item = tracked.get(params.requestId);
      if (!item) return;
      try {
        const body = await cdp.send('Network.getResponseBody', { requestId: params.requestId });
        item.body = body.base64Encoded ? '<base64>' : body.body;
      } catch (error) {
        item.bodyError = String(error.message || error);
      }
      network.push(item);
    });

    await waitFor(cdp, 'Boolean(document.querySelector(".login-strip") && document.querySelector(".settings-shell"))');
    const loginStatus = await evaluate(cdp, `
      fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ pin: ${JSON.stringify(PIN)} })
      }).then((response) => response.status)
    `);
    await evaluate(cdp, 'document.querySelector(".settings-shell > button").click()');
    await waitFor(cdp, 'Boolean(document.querySelector(".settings-panel"))');
    await waitFor(cdp, '!document.querySelector(".settings-actions button:nth-child(2)")?.disabled');
    await evaluate(cdp, 'document.querySelector(".settings-actions button:nth-child(2)").click()');
    const uiMessage = await waitFor(cdp, 'document.querySelector(".settings-panel .status-line")?.textContent || ""', 20000);
    await sleep(1000);

    const report = {
      ok: true,
      loginStatus,
      uiMessage,
      network: network.filter((item) => item.url.includes('/api/v1/settings/binance-key')),
      consoleLogs,
    };
    await fs.mkdir(path.dirname(OUTPUT), { recursive: true });
    await fs.writeFile(OUTPUT, JSON.stringify(report, null, 2), 'utf8');
    console.log(JSON.stringify(report, null, 2));
    cdp.close();
  } finally {
    edge.kill();
    await sleep(500);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
