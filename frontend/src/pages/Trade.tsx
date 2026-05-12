import { useEffect, useState } from 'react';
import { closeAll, fetchBinanceKeyStatus, fetchSession, fetchTicker, login, reverse } from '../api/client';
import { ActivityPanel } from '../components/ActivityPanel';
import { ControlPanels } from '../components/ControlPanels';
import { FloatingOrderPanel } from '../components/FloatingOrderPanel';
import { PositionPanel } from '../components/PositionPanel';
import { SettingsPanel } from '../components/SettingsPanel';
import { SymbolSelector } from '../components/SymbolSelector';
import { TradingViewWidget } from '../components/TradingViewWidget';

type Ticker = {
  bidPrice: string;
  askPrice: string;
  symbol: string;
};

export function Trade() {
  const [symbol, setSymbol] = useState('BTCUSDT');
  const [pin, setPin] = useState('');
  const [ticker, setTicker] = useState<Ticker | null>(null);
  const [status, setStatus] = useState('未登录');
  const [env, setEnv] = useState<'testnet' | 'mainnet'>('testnet');

  useEffect(() => {
    let active = true;
    async function loadSession() {
      try {
        const session = await fetchSession();
        if (active) setStatus(session.authenticated ? '已登录' : '未登录');
        if (session.authenticated) {
          const keyStatus = await fetchBinanceKeyStatus();
          if (active) setEnv(keyStatus.env);
        }
      } catch {
        if (active) setStatus('未登录');
      }
    }
    loadSession();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const data = await fetchTicker(symbol);
        if (active) setTicker(data);
      } catch {
        if (active) setTicker(null);
      }
    }
    load();
    const timer = window.setInterval(load, 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [symbol]);

  async function doLogin() {
    try {
      await login(pin);
      setStatus('已登录');
    } catch (error) {
      setStatus(error instanceof Error ? error.message : '登录失败');
    }
  }

  async function runCloseAll() {
    const confirmPin = window.prompt('请输入本地 PIN');
    if (!confirmPin) return;
    try {
      const result = await closeAll(confirmPin);
      setStatus(`全平已提交：${result.orders.length} 个订单`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : '全平失败');
    }
  }

  async function runReverse() {
    const confirmPin = window.prompt('请输入本地 PIN');
    if (!confirmPin) return;
    try {
      await reverse(symbol, confirmPin);
      setStatus('反手已提交');
    } catch (error) {
      setStatus(error instanceof Error ? error.message : '反手失败');
    }
  }

  return (
    <main className="trade-page">
      <header className="topbar">
        <div>
          <h1>Codex Fast Trade</h1>
          <span className={env === 'mainnet' ? 'env-pill mainnet' : 'env-pill'}>{env === 'mainnet' ? '合约实盘' : '测试网'}</span>
        </div>
        <div className="login-strip">
          <SettingsPanel onStatusChange={(nextStatus) => setEnv(nextStatus.env)} />
          <input type="password" placeholder="本地 PIN" value={pin} onChange={(event) => setPin(event.target.value)} />
          <button type="button" onClick={doLogin}>登录</button>
          <span>{status}</span>
        </div>
      </header>

      <section className="ticker-band">
        <div>
          <span>买一</span>
          <strong>{ticker?.bidPrice ?? '-'}</strong>
        </div>
        <div>
          <span>卖一</span>
          <strong>{ticker?.askPrice ?? '-'}</strong>
        </div>
        <div className="quick-buttons">
          <button type="button" className="danger" onClick={runCloseAll}>全平</button>
          <button type="button" onClick={runReverse}>反手</button>
        </div>
      </section>

      <section className="workspace">
        <TradingViewWidget symbol={symbol} />
        <aside>
          <SymbolSelector symbol={symbol} onSymbolChange={setSymbol} />
          <PositionPanel />
          <FloatingOrderPanel symbol={symbol} onSymbolChange={setSymbol} />
          <ControlPanels symbol={symbol} />
          <ActivityPanel symbol={symbol} />
        </aside>
      </section>
    </main>
  );
}
