export type ApiEnvelope<T> = {
  code: number;
  data: T;
  msg: string;
};

const DEFAULT_TIMEOUT_MS = 15000;

function binanceErrorText(message: string) {
  const match = message.match(/^Binance\s+(\d+):\s*(.*)$/);
  if (!match) return `币安接口错误：${message}`;

  const [, httpStatus, rawPayload] = match;
  let code = '';
  let binanceMessage = rawPayload.trim();
  try {
    const parsed = JSON.parse(rawPayload) as { code?: number | string; msg?: string };
    code = parsed.code !== undefined ? String(parsed.code) : '';
    binanceMessage = parsed.msg || binanceMessage;
  } catch {
    // Binance sometimes returns plain text for gateway and region errors.
  }

  const hints: Record<string, string> = {
    '-2015': '请检查 API Key 是否属于当前选择的合约环境、是否开启合约权限、是否配置了 IP 白名单。',
    '-1021': '请检查本机时间同步，时间偏差会导致签名请求被拒绝。'
  };
  const statusHints: Record<string, string> = {
    '401': '签名接口认证失败。',
    '403': '节点、地区或 IP 可能被限制。',
    '451': '当前网络节点可能受地区限制。'
  };
  const hint = hints[code] || statusHints[httpStatus] || '';
  const parts = [`币安接口错误：HTTP ${httpStatus}`];
  if (code) parts.push(`code ${code}`);
  if (binanceMessage) parts.push(binanceMessage);
  if (hint) parts.push(hint);
  return parts.join('，');
}

function errorText(message: string, status?: number) {
  const normalized = message.trim();
  const mapped: Record<string, string> = {
    'API error': '接口错误',
    'authentication required': '请先登录',
    'Binance testnet key is not configured': '请先在设置中配置币安测试网 Key',
    'Binance mainnet key is not configured': '请先在设置中配置币安合约实盘 Key',
    'mainnet requires explicit confirmation': '合约实盘需要显式确认',
    'invalid PIN': 'PIN 不正确',
    'valid PIN is required for execution': '执行需要有效 PIN'
  };
  if (mapped[normalized]) return mapped[normalized];
  if (status === 401) return '请先登录';
  if (status === 403) return '没有权限执行该操作';
  if (status === 404) return '请求的资源不存在';
  if (status && status >= 500) {
    if (normalized.startsWith('Binance ')) return binanceErrorText(normalized);
    return normalized ? `服务端错误 ${status}：${normalized}` : `服务端错误 ${status}`;
  }
  if (normalized.startsWith('Binance ')) return binanceErrorText(normalized);
  return normalized || '请求失败';
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
  try {
    response = await fetch(path, {
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers ?? {})
      },
      ...init,
      signal: init?.signal ?? controller.signal
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('请求超时，请确认后端服务正常');
    }
    throw new Error('后端服务未连接，请确认 18080 后端已启动');
  } finally {
    window.clearTimeout(timeout);
  }

  const bodyText = await response.text();
  let body: ApiEnvelope<T> | { detail?: string } | null = null;
  if (bodyText.trim()) {
    try {
      body = JSON.parse(bodyText) as ApiEnvelope<T> | { detail?: string };
    } catch {
      throw new Error(response.ok ? '接口返回格式错误' : `后端返回非 JSON 错误 ${response.status}`);
    }
  }

  if (!response.ok) {
    throw new Error(errorText(body && 'detail' in body && body.detail ? body.detail : '', response.status));
  }
  if (!body) {
    throw new Error('后端返回空响应');
  }
  if ('code' in body && body.code !== 0) {
    throw new Error(errorText(body.msg || 'API error'));
  }
  return (body as ApiEnvelope<T>).data;
}

export type FloatingOrderPayload = {
  symbol: string;
  side: 'long' | 'short';
  action: 'open' | 'close';
  float_pct: string;
  qty_mode: 'usdt' | 'base';
  qty: string;
  post_only: boolean;
  tp_pct?: string;
  sl_pct?: string;
  chase: {
    enabled: boolean;
    interval_sec: number;
    max_attempts: number;
    on_expire: 'cancel' | 'market' | 'keep';
  };
  ladders: {
    count: number;
    spacing_pct: string;
    distribution: 'equal';
  };
};

export function login(pin: string) {
  return api<{ authenticated: boolean }>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ pin })
  });
}

export function fetchSession() {
  return api<{ authenticated: boolean }>('/api/v1/auth/session');
}

export function fetchTicker(symbol: string) {
  return api<{ bidPrice: string; askPrice: string; symbol: string }>(`/api/v1/market/ticker?symbol=${encodeURIComponent(symbol)}`);
}

export type SymbolView = {
  symbol: string;
  tick_size: string;
  step_size: string;
  min_notional: string;
};

export function fetchSymbols() {
  return api<SymbolView[]>('/api/v1/market/symbols');
}

export function placeFloatingOrder(payload: FloatingOrderPayload) {
  return api<{ orders: Array<{ client_order_id: string; exchange: unknown }> }>('/api/v1/orders/floating', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function closeAll(pin: string) {
  return api<{ orders: unknown[] }>('/api/v1/orders/close-all', {
    method: 'POST',
    body: JSON.stringify({ pin })
  });
}

export function reverse(symbol: string, pin: string) {
  return api<unknown>('/api/v1/orders/reverse', {
    method: 'POST',
    body: JSON.stringify({ symbol, pin })
  });
}

export function cancelOrder(clientOrderId: string, pin: string) {
  return api<unknown>(`/api/v1/orders/${encodeURIComponent(clientOrderId)}`, {
    method: 'DELETE',
    body: JSON.stringify({ pin })
  });
}

export type PositionView = {
  symbol: string;
  positionAmt: string;
  entryPrice: string;
  markPrice?: string;
  unRealizedProfit?: string;
  leverage?: string;
  marginType?: string;
  liquidationPrice?: string;
};

export function fetchPositions() {
  return api<PositionView[]>('/api/v1/positions');
}

export function createMonitorRule(payload: {
  name: string;
  symbol: string;
  metric: 'quote_volume' | 'price_change_pct' | 'last_price';
  operator: '>' | '>=' | '<' | '<=';
  threshold: string;
  window: string;
  enabled: boolean;
}) {
  return api<{ id: number }>('/api/v1/monitors', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function evaluateMonitorLive(id: number) {
  return api<{ event_id: number; triggered: boolean; value: string }>(`/api/v1/monitors/${id}/evaluate-live`, {
    method: 'POST'
  });
}

export function createStrategy(payload: {
  name: string;
  type: 'grid' | 'ma_cross' | 'ai_signal';
  symbol: string;
  params: Record<string, unknown>;
  stoploss_config: Record<string, unknown>;
}) {
  return api<{ id: number }>('/api/v1/strategies', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function runStrategyOnce(id: number, payload: { execute: boolean; pin?: string }) {
  return api<Record<string, unknown>>(`/api/v1/strategies/${id}/run-once`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function createAiDraft(payload: {
  symbol: string;
  action: 'long_open' | 'short_open' | 'close' | 'hold';
  confidence: string;
  rationale: string;
  suggested_order: Record<string, unknown>;
}) {
  return api<{ id: number; status: string }>('/api/v1/ai/trade-drafts', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export function analyzeAi(symbol: string) {
  return api<{ id: number; status: string; action: string; confidence: string }>('/api/v1/ai/analyze', {
    method: 'POST',
    body: JSON.stringify({ symbol, context: {} })
  });
}

export function validateAiDraft(id: number) {
  return api<{ id: number; status: string; order: Record<string, unknown> }>(`/api/v1/ai/drafts/${id}/validate`, {
    method: 'POST'
  });
}

export function approveAiDraft(id: number, payload: { pin: string; execute: boolean }) {
  return api<Record<string, unknown>>(`/api/v1/ai/drafts/${id}/approve`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export type WorkerSnapshot = Record<
  'monitor' | 'strategy' | 'user_stream',
  {
    name: string;
    enabled: boolean;
    running: boolean;
    iterations: number;
    last_ok: string;
    last_error: string;
    last_event: string;
    listen_key?: boolean;
    events_handled?: number;
    keepalives?: number;
  }
>;

export function fetchWorkerStatus() {
  return api<WorkerSnapshot>('/api/v1/workers/status');
}

export type BinanceKeyStatus = {
  configured: boolean;
  id?: number;
  exchange: string;
  env: 'testnet' | 'mainnet';
  env_label?: string;
  base_url?: string;
  mainnet_confirmed?: boolean;
  label?: string;
  key_masked?: string;
  created_at?: string;
};

export function fetchBinanceKeyStatus() {
  return api<BinanceKeyStatus>('/api/v1/settings/binance-key');
}

export function saveBinanceKey(payload: {
  api_key: string;
  api_secret: string;
  label: string;
  env: 'testnet' | 'mainnet';
  confirm_mainnet: boolean;
}) {
  return api<BinanceKeyStatus>('/api/v1/settings/binance-key', {
    method: 'PUT',
    body: JSON.stringify(payload)
  });
}

export function testBinanceKey() {
  return api<{ connected: boolean; can_trade: boolean; fee_tier: unknown; assets: number; positions: number; env: string; base_url: string }>('/api/v1/settings/binance-key/test', {
    method: 'POST'
  });
}

export function deleteBinanceKey() {
  return api<BinanceKeyStatus>('/api/v1/settings/binance-key', {
    method: 'DELETE'
  });
}

export type OrderView = {
  id: number;
  client_order_id: string;
  symbol: string;
  side: string;
  action: string;
  order_type: string;
  price: string;
  qty: string;
  executed_qty: string;
  avg_price: string;
  status: string;
  origin: string;
  created_at: string;
  updated_at: string;
};

export type OrderEventView = {
  id: number;
  client_order_id: string;
  event_type: string;
  created_at: string;
};

export type MonitorEventView = {
  id: number;
  rule_id: number;
  symbol: string;
  metric: string;
  value: string;
  threshold: string;
  triggered: boolean;
  created_at: string;
};

export type StrategyRunView = {
  id: number;
  strategy_id: number;
  status: string;
  last_heartbeat: string;
  error: string;
  created_at: string;
  updated_at: string;
};

export type ActivityItemView = {
  id: string;
  source: string;
  time: string;
  title: string;
  detail: string;
  tone: '' | 'green' | 'red';
  cancel_client_order_id?: string;
};

export function fetchOrders(symbol: string) {
  return api<OrderView[]>(`/api/v1/orders?symbol=${encodeURIComponent(symbol)}&limit=20`);
}

export function fetchOrderEvents() {
  return api<OrderEventView[]>('/api/v1/orders/events?limit=20');
}

export function fetchMonitorEvents(symbol: string) {
  return api<MonitorEventView[]>(`/api/v1/monitors/events?symbol=${encodeURIComponent(symbol)}&limit=20`);
}

export function fetchStrategyRuns() {
  return api<StrategyRunView[]>('/api/v1/strategies/runs?limit=20');
}

export function fetchRecentActivity(symbol: string) {
  return api<ActivityItemView[]>(`/api/v1/activity/recent?symbol=${encodeURIComponent(symbol)}&limit=40`);
}
