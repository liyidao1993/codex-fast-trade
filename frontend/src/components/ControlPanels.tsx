import { useEffect, useState } from 'react';
import {
  WorkerSnapshot,
  analyzeAi,
  approveAiDraft,
  createAiDraft,
  createMonitorRule,
  createStrategy,
  evaluateMonitorLive,
  fetchWorkerStatus,
  runStrategyOnce,
  validateAiDraft
} from '../api/client';

const STATUS_TEXT: Record<string, string> = {
  approved: '已批准',
  canceled: '已取消',
  draft: '草稿',
  error: '异常',
  executed: '已执行',
  failed: '失败',
  hold: '观望',
  order: '出单',
  skipped: '已跳过',
  submitted: '已提交',
  unknown: '未知',
  validated: '已校验'
};

function statusText(value: unknown, fallback = '未知') {
  const key = String(value ?? fallback);
  return STATUS_TEXT[key] ?? key;
}

export function ControlPanels({ symbol }: { symbol: string }) {
  const [status, setStatus] = useState('');
  const [monitorId, setMonitorId] = useState<number | null>(null);
  const [strategyId, setStrategyId] = useState<number | null>(null);
  const [aiDraftId, setAiDraftId] = useState<number | null>(null);
  const [workers, setWorkers] = useState<WorkerSnapshot | null>(null);

  useEffect(() => {
    let active = true;
    async function loadWorkers() {
      try {
        const result = await fetchWorkerStatus();
        if (active) setWorkers(result);
      } catch {
        if (active) setWorkers(null);
      }
    }
    loadWorkers();
    const timer = window.setInterval(loadWorkers, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  async function addVolumeMonitor() {
    try {
      const result = await createMonitorRule({
        name: `${symbol} 成交额`,
        symbol,
        metric: 'quote_volume',
        operator: '>',
        threshold: '1000000',
        window: '5m',
        enabled: true
      });
      setMonitorId(result.id);
      setStatus(`监控已保存 #${result.id}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : '监控保存失败');
    }
  }

  async function addGridStrategy() {
    try {
      const result = await createStrategy({
        name: `${symbol} 网格`,
        type: 'grid',
        symbol,
        params: { lower: '90000', upper: '110000', qty_usdt: 100, tp_pct: '0.5' },
        stoploss_config: { mode: 'pct', value: '0.5' }
      });
      setStrategyId(result.id);
      setStatus(`策略已保存 #${result.id}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : '策略保存失败');
    }
  }

  async function addAiDraft() {
    try {
      const result = await createAiDraft({
        symbol,
        action: 'hold',
        confidence: '0.5',
        rationale: '等待更清晰的成交量和价格信号。',
        suggested_order: {}
      });
      setAiDraftId(result.id);
      setStatus(`AI 草稿 #${result.id}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'AI 草稿创建失败');
    }
  }

  async function runAiAnalyze() {
    try {
      const result = await analyzeAi(symbol);
      setAiDraftId(result.id);
      const actionText = result.action === 'long_open' ? '做多开仓' : result.action === 'short_open' ? '做空开仓' : result.action === 'close' ? '平仓' : '观望';
      setStatus(`AI ${actionText}草稿 #${result.id}，置信度 ${result.confidence}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'AI 分析失败');
    }
  }

  async function validateAi() {
    if (!aiDraftId) {
      setStatus('请先创建或分析 AI 草稿');
      return;
    }
    try {
      const result = await validateAiDraft(aiDraftId);
      setStatus(`AI 草稿状态：${statusText(result.status)}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'AI 校验失败');
    }
  }

  async function approveAi(execute: boolean) {
    if (!aiDraftId) {
      setStatus('请先创建或分析 AI 草稿');
      return;
    }
    const pin = window.prompt('请输入本地 PIN');
    if (!pin) return;
    try {
      const result = await approveAiDraft(aiDraftId, { pin, execute });
      setStatus(`AI 草稿状态：${statusText(result.status, 'approved')}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'AI 批准失败');
    }
  }

  async function evaluateMonitor() {
    if (!monitorId) {
      setStatus('请先创建监控');
      return;
    }
    try {
      const result = await evaluateMonitorLive(monitorId);
      setStatus(`监控${result.triggered ? '已触发' : '未触发'}，数值 ${result.value}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : '监控评估失败');
    }
  }

  async function dryRunStrategy() {
    if (!strategyId) {
      setStatus('请先创建策略');
      return;
    }
    try {
      const result = await runStrategyOnce(strategyId, { execute: false });
      setStatus(`策略信号：${statusText(result.signal)}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : '策略试算失败');
    }
  }

  async function executeStrategy() {
    if (!strategyId) {
      setStatus('请先创建策略');
      return;
    }
    const pin = window.prompt('请输入本地 PIN');
    if (!pin) return;
    try {
      const result = await runStrategyOnce(strategyId, { execute: true, pin });
      setStatus(`策略执行：${statusText(result.signal)}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : '策略执行失败');
    }
  }

  return (
    <div className="panel compact-panel">
      <div className="panel-title"><span>监控 / 策略 / AI</span><strong>{symbol}</strong></div>
      <div className="worker-grid">
        {(['monitor', 'strategy', 'user_stream'] as const).map((name) => {
          const item = workers?.[name];
          return (
            <div className="worker-chip" key={name}>
              <span>{name === 'user_stream' ? '用户流' : name === 'monitor' ? '监控' : '策略'}</span>
              <strong className={item?.running ? 'green-text' : ''}>{item?.running ? '运行中' : item?.enabled ? '待命' : '关闭'}</strong>
            </div>
          );
        })}
      </div>
      <div className="stack-actions">
        <button type="button" onClick={addVolumeMonitor}>保存成交额监控</button>
        <button type="button" onClick={evaluateMonitor}>实时评估监控</button>
        <button type="button" onClick={addGridStrategy}>保存网格策略模板</button>
        <button type="button" onClick={dryRunStrategy}>策略试算</button>
        <button type="button" onClick={executeStrategy}>执行一次策略</button>
        <button type="button" onClick={addAiDraft}>创建 AI 草稿</button>
        <button type="button" onClick={runAiAnalyze}>AI 分析</button>
        <button type="button" onClick={validateAi}>校验 AI 草稿</button>
        <button type="button" onClick={() => approveAi(false)}>批准 AI 草稿</button>
        <button type="button" onClick={() => approveAi(true)}>执行 AI 草稿</button>
      </div>
      {status && <div className="status-line">{status}</div>}
    </div>
  );
}
