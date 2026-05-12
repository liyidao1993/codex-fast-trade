import { FormEvent, useMemo, useState } from 'react';
import { FloatingOrderPayload, placeFloatingOrder } from '../api/client';

type Props = {
  symbol: string;
  onSymbolChange: (symbol: string) => void;
};

export function FloatingOrderPanel({ symbol, onSymbolChange }: Props) {
  const [side, setSide] = useState<'long' | 'short'>('long');
  const [action, setAction] = useState<'open' | 'close'>('open');
  const [qty, setQty] = useState('100');
  const [floatPct, setFloatPct] = useState('-0.1');
  const [tpPct, setTpPct] = useState('0.5');
  const [slPct, setSlPct] = useState('0.3');
  const [postOnly, setPostOnly] = useState(true);
  const [chase, setChase] = useState(true);
  const [ladderCount, setLadderCount] = useState(1);
  const [ladderSpacing, setLadderSpacing] = useState('0.05');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  const intentText = useMemo(() => `${side === 'long' ? '做多' : '做空'} / ${action === 'open' ? '开仓' : '平仓'}`, [side, action]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setStatus('');
    const payload: FloatingOrderPayload = {
      symbol,
      side,
      action,
      float_pct: floatPct,
      qty_mode: 'usdt',
      qty,
      post_only: postOnly,
      tp_pct: tpPct || undefined,
      sl_pct: slPct || undefined,
      chase: { enabled: chase, interval_sec: 5, max_attempts: 3, on_expire: 'cancel' },
      ladders: { count: ladderCount, spacing_pct: ladderSpacing, distribution: 'equal' }
    };
    try {
      const result = await placeFloatingOrder(payload);
      setStatus(`已提交 ${result.orders.length} 个订单`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : '提交失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel" onSubmit={submit}>
      <div className="panel-title">
        <span>浮动限价挂单</span>
        <strong>{intentText}</strong>
      </div>

      <label>
        <span>交易对</span>
        <input value={symbol} onChange={(event) => onSymbolChange(event.target.value.toUpperCase())} />
      </label>

      <div className="segmented">
        <button type="button" className={side === 'long' ? 'active green' : ''} onClick={() => setSide('long')}>做多</button>
        <button type="button" className={side === 'short' ? 'active red' : ''} onClick={() => setSide('short')}>做空</button>
      </div>

      <div className="segmented">
        <button type="button" className={action === 'open' ? 'active' : ''} onClick={() => setAction('open')}>开仓</button>
        <button type="button" className={action === 'close' ? 'active' : ''} onClick={() => setAction('close')}>平仓</button>
      </div>

      <div className="grid-2">
        <label>
          <span>金额 USDT</span>
          <input value={qty} onChange={(event) => setQty(event.target.value)} inputMode="decimal" />
        </label>
        <label>
          <span>浮动 %</span>
          <input value={floatPct} onChange={(event) => setFloatPct(event.target.value)} inputMode="decimal" />
        </label>
      </div>

      <div className="grid-2">
        <label>
          <span>止盈 %</span>
          <input value={tpPct} onChange={(event) => setTpPct(event.target.value)} inputMode="decimal" />
        </label>
        <label>
          <span>止损 %</span>
          <input value={slPct} onChange={(event) => setSlPct(event.target.value)} inputMode="decimal" />
        </label>
      </div>

      <div className="grid-2">
        <label>
          <span>分档</span>
          <input value={ladderCount} min={1} max={20} type="number" onChange={(event) => setLadderCount(Number(event.target.value))} />
        </label>
        <label>
          <span>档距 %</span>
          <input value={ladderSpacing} onChange={(event) => setLadderSpacing(event.target.value)} inputMode="decimal" />
        </label>
      </div>

      <div className="toggles">
        <label className="toggle"><input type="checkbox" checked={postOnly} onChange={(event) => setPostOnly(event.target.checked)} /> 只挂单</label>
        <label className="toggle"><input type="checkbox" checked={chase} onChange={(event) => setChase(event.target.checked)} /> 追价</label>
      </div>

      <button className="submit" disabled={busy} type="submit">{busy ? '提交中' : '提交挂单'}</button>
      {status && <div className="status-line">{status}</div>}
    </form>
  );
}
