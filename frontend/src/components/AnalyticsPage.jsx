import React, { useState, useEffect, useCallback } from 'react';
import Cookies from 'js-cookie';
import { useNavigate } from 'react-router-dom';
import {
  BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import './AnalyticsPage.css';

const API_BASE = '/api';

// Format a month string "2026-02" → "Feb '26"
const fmtMonth = (m) => {
  const [y, mo] = m.split('-');
  const label = new Date(Number(y), Number(mo) - 1)
    .toLocaleString('default', { month: 'short' });
  return `${label} '${String(y).slice(2)}`;
};

const fmt$ = (v) =>
  v === undefined || v === null ? '—'
    : `${v < 0 ? '-' : ''}$${Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const MonthTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="an-tooltip">
      <p className="an-tooltip-title">{fmtMonth(label)}</p>
      <p>PnL: <span className={d.pnl >= 0 ? 'c-green' : 'c-red'}>{fmt$(d.pnl)}</span></p>
      <p>New wheels: {d.new_wheels}</p>
      <p>Closed: {d.closed_wheels}</p>
      <p>Premiums: <span className="c-green">{fmt$(d.premiums)}</span></p>
    </div>
  );
};

function AnalyticsPage({ onLogout }) {
  const navigate = useNavigate();
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState(null);

  const fetchAnalytics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = Cookies.get('token');
      if (!token) { onLogout(); return; }
      const resp = await fetch(`${API_BASE}/analytics`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.status === 401) { onLogout(); return; }
      if (!resp.ok) throw new Error('Failed to fetch analytics');
      setData(await resp.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [onLogout]);

  useEffect(() => { fetchAnalytics(); }, [fetchAnalytics]);

  if (loading) return <div className="an-page an-center">Loading analytics…</div>;
  if (error)   return <div className="an-page an-center an-error">{error}</div>;

  const { overview: ov, by_symbol, monthly, close_reasons } = data;

  if (!ov) return (
    <div className="an-page">
      <div className="an-header">
        <button className="an-back" onClick={() => navigate('/')}>← Home</button>
        <h1>📊 Wheel Analytics</h1>
        <span />
      </div>
      <div className="an-center" style={{ marginTop: 80 }}>
        <span style={{ fontSize: '3rem' }}>📭</span>
        <p style={{ color: '#666', marginTop: 16 }}>No wheel data yet. Sync from IBKR to get started.</p>
      </div>
    </div>
  );

  const tiles = [
    // Row 1 — Counts
    { label: 'Total Wheels',     value: ov.total_wheels,      icon: '🎡', cls: '' },
    { label: 'Open Wheels',      value: ov.open_wheels,       icon: '🔓', cls: 'c-blue' },
    { label: 'Closed Wheels',    value: ov.closed_wheels,     icon: '✅', cls: '' },
    { label: 'Win Rate',         value: `${ov.win_rate}%`,    icon: '🎯',
      cls: ov.win_rate >= 50 ? 'c-green' : 'c-red' },
    // Row 2 — PnL
    { label: 'Total PnL',        value: fmt$(ov.total_realized_pnl),  icon: '💰',
      cls: ov.total_realized_pnl >= 0 ? 'c-green' : 'c-red' },
    { label: 'Best Wheel',       value: fmt$(ov.best_wheel_pnl),      icon: '🏆', cls: 'c-green' },
    { label: 'Worst Wheel',      value: fmt$(ov.worst_wheel_pnl),     icon: '📉',
      cls: ov.worst_wheel_pnl >= 0 ? 'c-green' : 'c-red' },
    { label: 'Avg PnL / Wheel',  value: fmt$(ov.avg_pnl_per_wheel),   icon: '📊',
      cls: ov.avg_pnl_per_wheel >= 0 ? 'c-green' : 'c-red' },
    // Row 3 — Premiums & Costs
    { label: 'Total Premiums',   value: fmt$(ov.total_premiums),      icon: '💵', cls: 'c-green' },
    { label: 'Total Commissions',value: fmt$(ov.total_commissions),   icon: '🏦', cls: 'c-red' },
    { label: 'Avg Premium / Wheel', value: fmt$(ov.avg_premium_per_wheel), icon: '💹', cls: 'c-green' },
    { label: 'Best Single Premium', value: fmt$(ov.max_single_premium), icon: '⭐', cls: 'c-green' },
    // Row 4 — Time & Activity
    { label: 'Avg Hold Days',    value: `${ov.avg_hold_days}d`,        icon: '⏱️', cls: '' },
    { label: 'Return / Day',     value: fmt$(ov.return_per_day),       icon: '📅',
      cls: ov.return_per_day >= 0 ? 'c-green' : 'c-red' },
    { label: 'Total Trades',     value: ov.total_trades,               icon: '🔢', cls: '' },
    { label: 'Symbols Traded',   value: ov.unique_symbols,             icon: '🎯', cls: '' },
  ];

  const totalClosed = (close_reasons.full_cycle || 0) + (close_reasons.put_closed || 0);
  const crTotal = totalClosed + (close_reasons.open || 0) || 1;
  const crItems = [
    { label: 'Full Cycle (Call Assigned)', count: close_reasons.full_cycle || 0,  cls: 'c-green', bg: '#00ff88' },
    { label: 'Put Bought Back',            count: close_reasons.put_closed || 0,  cls: 'c-yellow', bg: '#ffaa00' },
    { label: 'Still Open',                 count: close_reasons.open || 0,        cls: 'c-blue',   bg: '#4488ff' },
  ];

  return (
    <div className="an-page">
      {/* Header */}
      <div className="an-header">
        <button className="an-back" onClick={() => navigate('/')}>← Home</button>
        <h1>📊 Wheel Analytics</h1>
        <button className="an-refresh" onClick={fetchAnalytics}>↻ Refresh</button>
      </div>

      {/* Stats Grid */}
      <div className="an-grid">
        {tiles.map((t, i) => (
          <div className="an-tile" key={i}>
            <span className="an-tile-icon">{t.icon}</span>
            <span className="an-tile-label">{t.label}</span>
            <span className={`an-tile-value ${t.cls}`}>{t.value}</span>
          </div>
        ))}
      </div>

      {/* Charts Row */}
      <div className="an-charts-row">
        {/* Monthly Bar Chart */}
        <div className="an-card an-chart-card">
          <h3>Monthly PnL</h3>
          {monthly.length === 0 ? (
            <div className="an-empty">No monthly data</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={monthly} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2a40" vertical={false} />
                <XAxis dataKey="month" tickFormatter={fmtMonth}
                  tick={{ fill: '#888', fontSize: 11 }} tickLine={false} />
                <YAxis tick={{ fill: '#888', fontSize: 11 }} tickLine={false} axisLine={false}
                  tickFormatter={v => `$${v}`} />
                <Tooltip content={<MonthTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                <ReferenceLine y={0} stroke="#555" strokeDasharray="4 2" />
                <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
                  {monthly.map((entry, i) => (
                    <Cell key={i} fill={entry.pnl >= 0 ? '#00ff88' : '#ff4444'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Close Reasons */}
        <div className="an-card an-reasons-card">
          <h3>How Wheels Closed</h3>
          <div className="an-reasons">
            {crItems.map((cr, i) => (
              <div className="an-reason-row" key={i}>
                <div className="an-reason-meta">
                  <span className={`an-reason-label ${cr.cls}`}>{cr.label}</span>
                  <span className="an-reason-count">{cr.count}</span>
                </div>
                <div className="an-reason-bar-track">
                  <div
                    className="an-reason-bar-fill"
                    style={{ width: `${(cr.count / crTotal) * 100}%`, background: cr.bg }}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* Win / Loss split for closed wheels */}
          {totalClosed > 0 && (
            <div className="an-winloss">
              <h4>Closed Wheel Outcome</h4>
              <div className="an-winloss-bar">
                <div
                  className="an-winloss-win"
                  style={{ width: `${ov.win_rate}%` }}
                  title={`${ov.win_rate}% wins`}
                />
                <div
                  className="an-winloss-loss"
                  style={{ width: `${100 - ov.win_rate}%` }}
                  title={`${(100 - ov.win_rate).toFixed(1)}% losses`}
                />
              </div>
              <div className="an-winloss-labels">
                <span className="c-green">Win {ov.win_rate}%</span>
                <span className="c-red">Loss {(100 - ov.win_rate).toFixed(1)}%</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* By Symbol Table */}
      <div className="an-card">
        <h3>Performance by Symbol</h3>
        {by_symbol.length === 0 ? (
          <div className="an-empty">No symbol data</div>
        ) : (
          <div className="an-table-wrapper">
            <table className="an-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Total Wheels</th>
                  <th>Closed</th>
                  <th>Win Rate</th>
                  <th>Total PnL</th>
                  <th>Avg PnL</th>
                  <th>Total Premiums</th>
                  <th>Avg Hold Days</th>
                </tr>
              </thead>
              <tbody>
                {by_symbol.map((s, i) => (
                  <tr key={i}>
                    <td><strong>{s.symbol}</strong></td>
                    <td>{s.count}</td>
                    <td>{s.closed}</td>
                    <td>
                      <span className={s.win_rate >= 50 ? 'c-green' : 'c-red'}>
                        {s.closed > 0 ? `${s.win_rate}%` : '—'}
                      </span>
                    </td>
                    <td className={s.total_pnl >= 0 ? 'c-green' : 'c-red'}>{fmt$(s.total_pnl)}</td>
                    <td className={s.avg_pnl >= 0 ? 'c-green' : 'c-red'}>
                      {s.closed > 0 ? fmt$(s.avg_pnl) : '—'}
                    </td>
                    <td className="c-green">{fmt$(s.premiums)}</td>
                    <td>{s.avg_hold_days > 0 ? `${s.avg_hold_days}d` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default AnalyticsPage;
