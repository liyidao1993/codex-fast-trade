import { useEffect, useRef, useState } from 'react';

declare global {
  interface Window {
    TradingView?: {
      widget: new (options: Record<string, unknown>) => unknown;
    };
  }
}

export function TradingViewWidget({ symbol }: { symbol: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState('正在加载 TradingView 图表');
  const tvSymbol = `BINANCE:${symbol}.P`;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    setStatus('正在加载 TradingView 图表');
    container.innerHTML = '<div id="tv_chart"></div>';
    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/tv.js';
    script.async = true;
    script.onload = () => {
      if (!window.TradingView) {
        setStatus('TradingView 脚本未就绪');
        return;
      }
      new window.TradingView.widget({
        autosize: true,
        symbol: tvSymbol,
        interval: '15',
        timezone: 'Asia/Shanghai',
        theme: 'dark',
        style: '1',
        locale: 'zh_CN',
        enable_publishing: false,
        hide_side_toolbar: false,
        allow_symbol_change: false,
        container_id: 'tv_chart'
      });
      setStatus('');
    };
    script.onerror = () => setStatus('TradingView 脚本加载失败，请检查当前网络');
    container.appendChild(script);
    return () => {
      container.innerHTML = '';
    };
  }, [tvSymbol]);

  return (
    <div className="chart-shell-wrap">
      <div className="chart-shell" ref={containerRef} />
      {status && <div className="chart-status">{status}</div>}
    </div>
  );
}
