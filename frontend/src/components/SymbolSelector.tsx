import { useEffect, useMemo, useState } from 'react';
import { SymbolView, fetchSymbols } from '../api/client';

const FAVORITES_KEY = 'cft.favoriteSymbols';
const HISTORY_KEY = 'cft.symbolHistory';
const DEFAULT_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'LINKUSDT'];

function readList(key: string) {
  try {
    const value = window.localStorage.getItem(key);
    return value ? (JSON.parse(value) as string[]) : [];
  } catch {
    return [];
  }
}

function writeList(key: string, value: string[]) {
  window.localStorage.setItem(key, JSON.stringify(value.slice(0, 20)));
}

function uniqueList(items: string[]) {
  return [...new Set(items.map((item) => item.trim().toUpperCase()).filter(Boolean))];
}

export function SymbolSelector({ symbol, onSymbolChange }: { symbol: string; onSymbolChange: (symbol: string) => void }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [symbols, setSymbols] = useState<string[]>(DEFAULT_SYMBOLS);
  const [favorites, setFavorites] = useState<string[]>(() => readList(FAVORITES_KEY));
  const [history, setHistory] = useState<string[]>(() => readList(HISTORY_KEY));
  const [source, setSource] = useState('默认列表');

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const result = await fetchSymbols();
        const loaded = result.map((item: SymbolView) => item.symbol).filter(Boolean).sort();
        if (active && loaded.length > 0) {
          setSymbols(loaded);
          setSource('币安合约');
        }
      } catch {
        if (active) setSource('默认列表');
      }
    }
    load();
    return () => {
      active = false;
    };
  }, []);

  function choose(nextSymbol: string) {
    const normalized = nextSymbol.toUpperCase();
    onSymbolChange(normalized);
    const nextHistory = [normalized, ...history.filter((item) => item !== normalized)].slice(0, 12);
    setHistory(nextHistory);
    writeList(HISTORY_KEY, nextHistory);
    setQuery('');
    setOpen(false);
  }

  function toggleFavorite(nextSymbol: string) {
    const normalized = nextSymbol.toUpperCase();
    const nextFavorites = favorites.includes(normalized)
      ? favorites.filter((item) => item !== normalized)
      : [normalized, ...favorites].slice(0, 12);
    setFavorites(nextFavorites);
    writeList(FAVORITES_KEY, nextFavorites);
  }

  const results = useMemo(() => {
    const normalized = query.trim().toUpperCase();
    if (normalized) return symbols.filter((item) => item.includes(normalized)).slice(0, 24);
    if (history.length > 0) return uniqueList(history).slice(0, 12);
    return DEFAULT_SYMBOLS.filter((item) => symbols.includes(item)).slice(0, 12);
  }, [history, query, symbols]);

  return (
    <section className="symbol-selector">
      <button type="button" className="symbol-current-trigger" onClick={() => setOpen((value) => !value)}>
        <span>
          <em>当前交易对</em>
          <strong>{symbol}</strong>
        </span>
        <b>{open ? '收起' : '切换'}</b>
      </button>

      {open && (
        <div className="symbol-popover">
          <div className="symbol-popover-head">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索币种，例如 BTC / ETH / SOL"
              autoFocus
            />
            <button
              type="button"
              className={favorites.includes(symbol) ? 'active-star' : ''}
              onClick={() => toggleFavorite(symbol)}
            >
              {favorites.includes(symbol) ? '已收藏' : '收藏'}
            </button>
          </div>
          <div className="symbol-meta">来源：{source}</div>

          {favorites.length > 0 && (
            <div className="symbol-popup-section">
              <span>收藏</span>
              <div className="symbol-chips">
                {favorites.map((item) => (
                  <button key={item} type="button" className={item === symbol ? 'active' : ''} onClick={() => choose(item)}>
                    {item}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="symbol-popup-section">
            <span>{query.trim() ? '搜索结果' : history.length > 0 ? '最近搜索' : '常用交易对'}</span>
            <div className="symbol-results expanded">
              {results.map((item) => (
                <div className="symbol-result" key={item}>
                  <button type="button" className={item === symbol ? 'active' : ''} onClick={() => choose(item)}>
                    {item}
                  </button>
                  <button type="button" className="star-button" onClick={() => toggleFavorite(item)}>
                    {favorites.includes(item) ? '★' : '☆'}
                  </button>
                </div>
              ))}
              {results.length === 0 && <div className="symbol-empty">没有匹配币种</div>}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
