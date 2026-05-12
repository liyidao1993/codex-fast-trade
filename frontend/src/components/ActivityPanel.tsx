import { useEffect, useState } from 'react';
import { ActivityItemView, cancelOrder, fetchRecentActivity } from '../api/client';

function timeLabel(value: string) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function sourceLabel(value: string) {
  const labels: Record<string, string> = {
    order: '订单',
    'order event': '订单事件',
    protection: '保护单',
    alert: '告警',
    monitor: '监控',
    strategy: '策略'
  };
  return labels[value] ?? value;
}

export function ActivityPanel({ symbol }: { symbol: string }) {
  const [items, setItems] = useState<ActivityItemView[]>([]);
  const [status, setStatus] = useState('登录后加载活动');

  async function load(active = true) {
    try {
      const result = await fetchRecentActivity(symbol);
      if (active) {
        setItems(result);
        setStatus('');
      }
    } catch (error) {
        if (active) setStatus(error instanceof Error ? error.message : '活动加载失败');
    }
  }

  async function cancel(clientOrderId: string) {
    const pin = window.prompt('请输入本地 PIN');
    if (!pin) return;
    try {
      await cancelOrder(clientOrderId, pin);
      setStatus('撤单已提交');
      await load();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : '撤单失败');
    }
  }

  useEffect(() => {
    let active = true;
    load(active);
    const timer = window.setInterval(() => load(active), 4000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [symbol]);

  return (
    <div className="panel compact-panel activity-panel">
      <div className="panel-title"><span>活动</span><strong>{symbol}</strong></div>
      {status && <div className="empty-state">{status}</div>}
      {!status && items.length === 0 && <div className="empty-state">暂无本地活动</div>}
      <div className="activity-list">
        {items.map((item) => (
          <div className="activity-row" key={item.id}>
            <span>{timeLabel(item.time)}</span>
            <strong className={item.tone === 'green' ? 'green-text' : item.tone === 'red' ? 'red-text' : ''}>{item.title}</strong>
            <em>{sourceLabel(item.source)}</em>
            <p>{item.detail}</p>
            {item.cancel_client_order_id && (
              <button type="button" className="mini-action danger" onClick={() => cancel(item.cancel_client_order_id ?? '')}>撤单</button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
