import { useEffect, useState } from 'react';
import { PositionView, fetchPositions } from '../api/client';

function compact(value?: string) {
  if (!value) return '-';
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return value;
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

export function PositionPanel() {
  const [positions, setPositions] = useState<PositionView[]>([]);
  const [status, setStatus] = useState('登录并配置币安 Key 后加载持仓');

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const result = await fetchPositions();
        if (active) {
          setPositions(result);
          setStatus('');
        }
      } catch (error) {
        if (active) setStatus(error instanceof Error ? error.message : '持仓加载失败');
      }
    }
    load();
    const timer = window.setInterval(load, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <div className="panel compact-panel">
      <div className="panel-title"><span>持仓</span><strong>{positions.length}</strong></div>
      {status && <div className="empty-state">{status}</div>}
      {!status && positions.length === 0 && <div className="empty-state">空仓</div>}
      <div className="position-list">
        {positions.map((position) => (
          <div className="position-row" key={position.symbol}>
            <strong>{position.symbol}</strong>
            <span>数量 {compact(position.positionAmt)}</span>
            <span>开仓价 {compact(position.entryPrice)}</span>
            <span>盈亏 {compact(position.unRealizedProfit)}</span>
            <span>强平价 {compact(position.liquidationPrice)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
