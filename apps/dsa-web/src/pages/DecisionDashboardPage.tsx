import { useEffect, useMemo, useState } from 'react';
import { Activity, ArrowUpRight, RefreshCw, ShieldAlert, TrendingUp } from 'lucide-react';
import { historyApi } from '../api/history';
import type { HistoryItem } from '../types/analysis';

const WATCHLIST = [
  { code: '1303', name: '南亞' },
  { code: '2408', name: '南亞科' },
  { code: '2344', name: '華邦電' },
  { code: '2454', name: '聯發科' },
  { code: '3231', name: '緯創' },
  { code: '2330', name: '台積電' },
  { code: '2881', name: '富邦金' },
  { code: '2603', name: '長榮' },
  { code: '2409', name: '友達' },
];

const actionText: Record<string, string> = {
  buy: '買進', add: '加碼', hold: '續抱', watch: '觀察',
  reduce: '減碼', sell: '賣出', avoid: '避開', alert: '注意',
};

function formatPrice(value?: number) {
  return typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString('zh-TW', { maximumFractionDigits: 2 })
    : '—';
}

function formatChange(value?: number) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
}

export default function DecisionDashboardPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [updatedAt, setUpdatedAt] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await historyApi.getList({ page: 1, limit: 100 });
      setItems(response.items.filter(item => item.reportType !== 'market_review'));
      setUpdatedAt(new Date().toLocaleString('zh-TW'));
    } catch (err) {
      setError(err instanceof Error ? err.message : '讀取盤後報告失敗');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const latestByCode = useMemo(() => {
    const map = new Map<string, HistoryItem>();
    [...items].sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
      .forEach(item => { if (!map.has(item.stockCode)) map.set(item.stockCode, item); });
    return map;
  }, [items]);

  const rows = WATCHLIST.map(stock => ({ ...stock, report: latestByCode.get(stock.code) }));
  const counts = rows.reduce((acc, row) => {
    const action = row.report?.action ?? 'unknown';
    acc[action] = (acc[action] ?? 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-muted-foreground">盤後分析 · 翌日投資參考</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight">決策儀表板</h1>
          <p className="mt-1 text-sm text-muted-foreground">只呈現已產生的分析報告，不提供盤中即時訊號。</p>
        </div>
        <button type="button" onClick={() => void load()} disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50">
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> 重新整理
        </button>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border bg-card p-4"><p className="text-sm text-muted-foreground">觀察股票</p><p className="mt-2 text-3xl font-semibold">{WATCHLIST.length}</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-sm text-muted-foreground">已取得最新報告</p><p className="mt-2 text-3xl font-semibold">{rows.filter(r => r.report).length}<span className="ml-1 text-base text-muted-foreground">/ {WATCHLIST.length}</span></p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-sm text-muted-foreground">買進／加碼</p><p className="mt-2 text-3xl font-semibold">{(counts.buy ?? 0) + (counts.add ?? 0)}</p></div>
        <div className="rounded-xl border bg-card p-4"><p className="text-sm text-muted-foreground">觀望／續抱</p><p className="mt-2 text-3xl font-semibold">{(counts.watch ?? 0) + (counts.hold ?? 0)}</p></div>
      </section>

      {error && <div role="alert" className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
      <section className="overflow-hidden rounded-xl border bg-card">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b p-4">
          <div><h2 className="font-semibold">個股決策總覽</h2><p className="text-xs text-muted-foreground">依最新已儲存報告顯示；沒有報告時不推測訊號。</p></div>
          <span className="text-xs text-muted-foreground">{updatedAt ? `資料讀取時間：${updatedAt}` : '尚未更新'}</span>
        </div>
        {loading && <p className="p-6 text-sm text-muted-foreground">正在讀取歷史報告…</p>}
        {!loading && <div className="divide-y">
          {rows.map(row => {
            const report = row.report;
            const action = report?.action ?? '';
            return <article key={row.code} className="grid gap-3 p-4 md:grid-cols-[1.1fr_0.8fr_0.8fr_1.1fr] md:items-center">
              <div><p className="font-semibold">{row.name} <span className="ml-1 text-xs font-normal text-muted-foreground">{row.code}</span></p><p className="text-xs text-muted-foreground">{report ? new Date(report.createdAt).toLocaleString('zh-TW') : '尚無可用報告'}</p></div>
              <div><p className="text-xs text-muted-foreground">報告收盤價</p><p className="font-semibold tabular-nums">{formatPrice(report?.currentPrice)}</p></div>
              <div><p className="text-xs text-muted-foreground">報告漲跌幅</p><p className={`font-semibold tabular-nums ${(report?.changePct ?? 0) > 0 ? 'text-red-600' : (report?.changePct ?? 0) < 0 ? 'text-emerald-600' : ''}`}>{formatChange(report?.changePct)}</p></div>
              <div className="flex flex-wrap items-center gap-2">
                {report ? <span className="rounded-full bg-muted px-3 py-1 text-sm font-semibold">{actionText[action] ?? report.actionLabel ?? '待判讀'}</span> : <span className="rounded-full border px-3 py-1 text-sm text-muted-foreground">等待盤後報告</span>}
                {report && <span className="text-xs text-muted-foreground">情緒分數：{typeof report.sentimentScore === 'number' ? report.sentimentScore : '—'}</span>}
              </div>
              {report?.analysisSummary && <p className="text-sm text-muted-foreground md:col-span-4">{report.analysisSummary}</p>}
            </article>;
          })}
        </div>}
      </section>

      <section className="grid gap-3 md:grid-cols-3">
        <div className="rounded-xl border p-4"><div className="flex items-center gap-2 font-semibold"><TrendingUp size={17}/> 起漲訊號</div><p className="mt-2 text-sm text-muted-foreground">下一階段接入後端已驗證的起漲階段；目前不自行計算或虛構訊號。</p></div>
        <div className="rounded-xl border p-4"><div className="flex items-center gap-2 font-semibold"><ShieldAlert size={17}/> 假突破風險</div><p className="mt-2 text-sm text-muted-foreground">待完成歷史回測及風險分級校準後再顯示。</p></div>
        <div className="rounded-xl border p-4"><div className="flex items-center gap-2 font-semibold"><Activity size={17}/> 翌日交易計畫</div><p className="mt-2 text-sm text-muted-foreground">後續串接原報告的進場、加碼、失效與停利條件。</p></div>
      </section>
      <p className="text-xs text-muted-foreground">本頁為獨立原型，不更動既有盤後報告、Telegram／Email 通知或盤中通知設定。</p>
    </main>
  );
}
