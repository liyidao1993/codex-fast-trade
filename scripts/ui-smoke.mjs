import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';

const EDGE_PATH =
  process.env.EDGE_PATH ||
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const APP_URL = process.env.APP_URL || 'http://127.0.0.1:18081/';
const PORT = Number(process.env.CDP_PORT || 9337);
const PROFILE_DIR = path.resolve('data', 'edge-smoke');

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
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await waitFor(cdp, 'Boolean(document.querySelector(".symbol-selector") && document.querySelector(".chart-shell"))');
    await waitFor(cdp, 'document.querySelector("iframe[title*=TradingView]")?.src.includes("BTCUSDT.P")');
    await evaluate(cdp, `
      (() => {
        localStorage.setItem("cft.favoriteSymbols", JSON.stringify(["BTCUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT"]));
        localStorage.setItem("cft.symbolHistory", JSON.stringify(["BTCUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT"]));
        location.reload();
      })()
    `);
    await waitFor(cdp, 'Boolean(document.querySelector(".symbol-current-trigger") && document.querySelector(".chart-shell"))');

    const closedLayout = await evaluate(cdp, `({
      selectorHeight: Math.round(document.querySelector(".symbol-selector").getBoundingClientRect().height),
      hasInlineInput: Boolean(document.querySelector(".symbol-selector > input")),
      hasStrip: Boolean(document.querySelector(".symbol-strip")),
      current: document.querySelector(".symbol-current-trigger strong")?.textContent,
      positionTop: Math.round(document.querySelector(".position-list")?.getBoundingClientRect().top || 0),
    })`);
    if (closedLayout.selectorHeight > 76 || closedLayout.hasInlineInput || closedLayout.hasStrip) {
      throw new Error(`Symbol selector is not compact when closed: ${JSON.stringify(closedLayout)}`);
    }

    await evaluate(cdp, 'document.querySelector(".symbol-current-trigger").click()');
    await waitFor(cdp, 'Boolean(document.querySelector(".symbol-popover input"))');
    const openLayout = await evaluate(cdp, `({
      selectorHeight: Math.round(document.querySelector(".symbol-selector").getBoundingClientRect().height),
      popoverPosition: getComputedStyle(document.querySelector(".symbol-popover")).position,
      sectionText: [...document.querySelectorAll(".symbol-popup-section > span")].map((item) => item.textContent),
      current: document.querySelector(".symbol-current-trigger strong")?.textContent,
    })`);
    if (openLayout.selectorHeight > 76 || openLayout.popoverPosition !== 'absolute' || !openLayout.sectionText.includes('最近搜索')) {
      throw new Error(`Symbol popover is not detached or search-as-history is missing: ${JSON.stringify(openLayout)}`);
    }

    await evaluate(cdp, `
      (() => {
        const input = document.querySelector(".symbol-popover input");
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
        setter.call(input, "ETH");
        input.dispatchEvent(new Event("input", { bubbles: true }));
      })()
    `);
    await waitFor(cdp, '[...document.querySelectorAll(".symbol-result button")].some((button) => button.textContent === "ETHUSDT")');
    await evaluate(cdp, '[...document.querySelectorAll(".symbol-result button")].find((button) => button.textContent === "ETHUSDT").click()');
    await waitFor(cdp, 'document.querySelector(".symbol-current-trigger strong")?.textContent === "ETHUSDT"');
    await waitFor(cdp, 'document.querySelector("iframe[title*=TradingView]")?.src.includes("ETHUSDT.P")');

    await evaluate(cdp, 'document.querySelector(".symbol-current-trigger").click()');
    await waitFor(cdp, 'Boolean(document.querySelector(".symbol-popover"))');
    await evaluate(cdp, 'document.querySelector(".symbol-popover-head button").click()');
    await waitFor(cdp, 'localStorage.getItem("cft.favoriteSymbols")?.includes("ETHUSDT")');

    await evaluate(cdp, `
      (() => {
        const input = document.querySelector(".symbol-popover input");
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
        setter.call(input, "SOL");
        input.dispatchEvent(new Event("input", { bubbles: true }));
      })()
    `);
    await waitFor(cdp, '[...document.querySelectorAll(".symbol-result button")].some((button) => button.textContent === "SOLUSDT")');
    await evaluate(cdp, '[...document.querySelectorAll(".symbol-result button")].find((button) => button.textContent === "SOLUSDT").click()');
    await waitFor(cdp, 'document.querySelector(".symbol-current-trigger strong")?.textContent === "SOLUSDT"');

    await evaluate(cdp, 'document.querySelector(".symbol-current-trigger").click()');
    await waitFor(cdp, '[...document.querySelectorAll(".symbol-result button")].some((button) => button.textContent === "ETHUSDT")');
    await evaluate(cdp, '[...document.querySelectorAll(".symbol-result button")].find((button) => button.textContent === "ETHUSDT").click()');
    await waitFor(cdp, 'document.querySelector(".symbol-current-trigger strong")?.textContent === "ETHUSDT"');

    const final = await evaluate(cdp, `({
      current: document.querySelector(".symbol-current-trigger strong")?.textContent,
      orderSymbol: document.querySelector("form.panel input")?.value,
      chart: document.querySelector("iframe[title*=TradingView]")?.src,
      favorites: JSON.parse(localStorage.getItem("cft.favoriteSymbols") || "[]"),
      history: JSON.parse(localStorage.getItem("cft.symbolHistory") || "[]"),
      closedLayout: ${JSON.stringify(closedLayout)},
      openLayout: ${JSON.stringify(openLayout)},
      hasHistoryStrip: Boolean(document.querySelector(".symbol-strip")),
      bodyHasEnglishAuth: document.body.innerText.includes("authentication required"),
    })`);

    console.log(JSON.stringify({ ok: true, final }, null, 2));
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
