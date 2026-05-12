import { useEffect, useState } from 'react';
import { BinanceKeyStatus, deleteBinanceKey, fetchBinanceKeyStatus, saveBinanceKey, testBinanceKey } from '../api/client';

type BinanceEnv = 'testnet' | 'mainnet';

const ENV_LABELS: Record<BinanceEnv, string> = {
  testnet: '合约测试网',
  mainnet: '合约实盘'
};

export function SettingsPanel({ onStatusChange }: { onStatusChange?: (status: BinanceKeyStatus) => void }) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<BinanceKeyStatus | null>(null);
  const [env, setEnv] = useState<BinanceEnv>('testnet');
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  function applyStatus(nextStatus: BinanceKeyStatus) {
    setStatus(nextStatus);
    setEnv(nextStatus.env);
    onStatusChange?.(nextStatus);
  }

  async function load() {
    try {
      applyStatus(await fetchBinanceKeyStatus());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '设置加载失败');
    }
  }

  useEffect(() => {
    if (open) {
      load();
    }
  }, [open]);

  async function save() {
    if (env === 'mainnet') {
      const confirmed = window.confirm('确认保存币安合约实盘 API Key？保存后行情、持仓和下单都会走实盘 fapi.binance.com。');
      if (!confirmed) return;
    }
    setBusy(true);
    setMessage('正在保存 Key...');
    try {
      const result = await saveBinanceKey({
        api_key: apiKey.trim(),
        api_secret: apiSecret.trim(),
        env,
        confirm_mainnet: env === 'mainnet',
        label: env === 'mainnet' ? '币安合约实盘' : '币安合约测试网'
      });
      applyStatus(result);
      setApiKey('');
      setApiSecret('');
      setMessage(`已保存 ${ENV_LABELS[result.env]}：${result.key_masked ?? '已配置'}。当前接口：${result.base_url ?? '-'}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '保存失败');
    } finally {
      setBusy(false);
    }
  }

  async function testConnection() {
    setBusy(true);
    setMessage('');
    try {
      const result = await testBinanceKey();
      setMessage(
        `连接成功：${ENV_LABELS[result.env as BinanceEnv] ?? result.env}，可交易=${String(result.can_trade)}，资产=${result.assets}，持仓=${result.positions}`
      );
      await load();
    } catch (error) {
      const text = error instanceof Error ? error.message : '连接测试失败';
      setMessage(text.startsWith('币安接口错误') ? `连接测试失败：${text}` : text);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    const confirmed = window.confirm(`确认删除已保存的币安${ENV_LABELS[env]} Key？`);
    if (!confirmed) return;
    setBusy(true);
    try {
      const result = await deleteBinanceKey();
      applyStatus(result);
      setMessage('已删除。');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '删除失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-shell">
      <button type="button" onClick={() => setOpen((value) => !value)}>设置</button>
      {open && (
        <div className="settings-panel">
          <div className="panel-title">
            <span>币安 API</span>
            <strong>{ENV_LABELS[env]}</strong>
          </div>
          <div className="segmented">
            <button type="button" className={env === 'testnet' ? 'active' : ''} onClick={() => setEnv('testnet')} disabled={busy}>
              测试网
            </button>
            <button type="button" className={env === 'mainnet' ? 'active red' : 'red'} onClick={() => setEnv('mainnet')} disabled={busy}>
              实盘
            </button>
          </div>
          <div className="key-state">
            <span>
              {status?.configured && status.env === env ? `已配置 ${status.key_masked}` : `未配置 ${ENV_LABELS[env]}`}
            </span>
            <em>{env === 'mainnet' ? 'https://fapi.binance.com' : 'https://demo-fapi.binance.com'}</em>
          </div>
          <label>
            <span>API Key（密钥）</span>
            <input value={apiKey} onChange={(event) => setApiKey(event.target.value)} autoComplete="off" />
          </label>
          <label>
            <span>API Secret（私钥）</span>
            <input value={apiSecret} onChange={(event) => setApiSecret(event.target.value)} type="password" autoComplete="off" />
          </label>
          <div className="settings-actions">
            <button type="button" disabled={busy || !apiKey.trim() || !apiSecret.trim()} onClick={save}>{busy ? '处理中' : '保存 Key'}</button>
            <button type="button" disabled={busy || !status?.configured || status.env !== env} onClick={testConnection}>测试连接</button>
            <button type="button" disabled={busy || !status?.configured || status.env !== env} className="danger" onClick={remove}>删除</button>
          </div>
          {message && <div className="status-line">{message}</div>}
        </div>
      )}
    </div>
  );
}
