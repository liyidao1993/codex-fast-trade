import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';

const EDGE_PATH =
  process.env.EDGE_PATH ||
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const APP_URL = process.env.APP_URL || 'http://127.0.0.1:18081/';
const PORT = Number(process.env.CDP_PORT || 9338);
const PROFILE_DIR = path.resolve('data', 'edge-settings-smoke');
const PIN = process.env.APP_PIN || '123456';
const SERVER_ERROR_TEXT = '\u670d\u52a1\u7aef\u9519\u8bef';

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
    socket.addEventListener('message', (event) => {
      const message = JSON.parse(event.data);
      if (!message.id) return;
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      if (message.error) {
        pending.reject(new Error(message.error.message));
      } else {
        pending.resolve(message.result);
      }
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    this.socket.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
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
    await waitFor(cdp, 'Boolean(document.querySelector(".login-strip") && document.querySelector(".settings-shell"))');

    await evaluate(cdp, `
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
    const message = await waitFor(cdp, 'document.querySelector(".settings-panel .status-line")?.textContent || ""', 20000);

    if (message.includes(SERVER_ERROR_TEXT)) {
      throw new Error(`Settings connection still shows generic server error: ${message}`);
    }
    const success = message.includes('连接成功');
    const binanceDetail = message.includes('币安接口错误') && message.includes('HTTP');
    if (!success && !binanceDetail) {
      throw new Error(`Settings connection did not expose success or Binance detail: ${message}`);
    }

    console.log(JSON.stringify({ ok: true, message }, null, 2));
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
