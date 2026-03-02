import React, { useState, useEffect, useCallback } from 'react';
import Cookies from 'js-cookie';
import { useNavigate } from 'react-router-dom';
import {
  AreaChart, Area, BarChart, Bar, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import './FuturisticWheel.css';

const API_BASE = '/api';

// ── Formatters ────────────────────────────────────────────────────────────────

const fmt$ = (v) =>
  v == null ? '—'
    : `${v < 0 ? '-' : ''}$${Math.abs(v).toLocaleString(undefined, {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
      })}`;

const fmtDate = (s) => (s ? s.slice(0, 10) : '—');

/** Normalise expiry to YYYY-MM-DD regardless of whether it arrives as YYYYMMDD */
const normalizeExpiry = (expiry) => {
  if (!expiry) return '';
  const s = expiry.slice(0, 10);
  if (s.length === 8 && !s.includes('-'))
    return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
  return s;
};

// ── Custom Tooltips ───────────────────────────────────────────────────────────

const LeapTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="fw-tooltip">
      <p className="fw-tooltip-title">{label}</p>
      <p className="fw-purple">Contracts: <strong>{payload[0].value}</strong></p>
    </div>
  );
};

const CumulativeTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="fw-tooltip">
      <p className="fw-tooltip-title">{label}</p>
      <p>Day P&L: <span className={d.daily_pnl >= 0 ? 'fw-green' : 'fw-red'}>{fmt$(d.daily_pnl)}</span></p>
      <p>Cumulative: <span className="fw-green">{fmt$(d.cumulative_pnl)}</span></p>
    </div>
  );
};

const TradeBarTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="fw-tooltip">
      <p className="fw-tooltip-title">Trade #{label}</p>
      <p style={{ fontSize: '0.75rem', color: '#888', marginBottom: 2 }}>{d.label}</p>
      <p>P&L: <span className={d.pnl >= 0 ? 'fw-green' : 'fw-red'}>{fmt$(d.pnl)}</span></p>
    </div>
  );
};

// ── Component ─────────────────────────────────────────────────────────────────

function FuturisticWheel({ onLogout }) {
  const navigate = useNavigate();

  const [data,        setData]        = useState(null);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState(null);
  const [syncing,     setSyncing]     = useState(false);
  const [syncResult,  setSyncResult]  = useState(null);
  const [purging,     setPurging]     = useState(false);
  const [autoSync,    setAutoSync]    = useState(false);
  const [deltaInputs,    setDeltaInputs]    = useState({});    // { GOOGL: "0.35" }
  const [savingDelta,    setSavingDelta]    = useState({});    // { GOOGL: true/false }
  const [marketData,     setMarketData]     = useState({});    // { GOOGL: { price, leaps } }
  const [fetchingMarket, setFetchingMarket] = useState(false);
  const [marketError,    setMarketError]    = useState(null);

  // ── Fetch data ──────────────────────────────────────────────────────────────
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = Cookies.get('token');
      if (!token) { onLogout(); return; }
      const resp = await fetch(`${API_BASE}/futuristic-wheel`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.status === 401) { onLogout(); return; }
      if (!resp.ok) throw new Error('Failed to load Futuristic Wheel data');
      const d = await resp.json();
      setData(d);
      setAutoSync(d.settings?.auto_sync ?? false);
      // Pre-populate delta inputs from stored values
      const storedDeltas = d.leaps?.pmcc_deltas || {};
      const inputs = {};
      (d.leaps?.current || []).forEach(l => {
        inputs[l.symbol] = storedDeltas[l.symbol] != null
          ? String(storedDeltas[l.symbol])
          : '';
      });
      setDeltaInputs(inputs);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [onLogout]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // ── Sync ────────────────────────────────────────────────────────────────────
  const handleSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const token = Cookies.get('token');
      if (!token) { onLogout(); return; }
      const resp = await fetch(`${API_BASE}/futuristic-wheel/sync`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.status === 401) { onLogout(); return; }
      const result = await resp.json();
      setSyncResult(result);
      if (result.status === 'success') await fetchData();
    } catch (e) {
      setSyncResult({ status: 'error', message: e.message });
    } finally {
      setSyncing(false);
    }
  };

  // ── Purge ────────────────────────────────────────────────────────────────────
  const handlePurge = async () => {
    if (!window.confirm('Delete ALL stored short call records? You will need to sync again to repopulate.')) return;
    setPurging(true);
    setSyncResult(null);
    try {
      const token = Cookies.get('token');
      if (!token) { onLogout(); return; }
      const resp = await fetch(`${API_BASE}/futuristic-wheel/purge-calls`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.status === 401) { onLogout(); return; }
      const result = await resp.json();
      setSyncResult({ status: 'success', message: `🗑️ Purged ${result.deleted} record(s). Sync to repopulate.` });
      await fetchData();
    } catch (e) {
      setSyncResult({ status: 'error', message: e.message });
    } finally {
      setPurging(false);
    }
  };

  // ── Auto-sync toggle ──────────────────────────────────────────────
  const handleAutoSyncToggle = async (e) => {
    const enabled = e.target.checked;
    setAutoSync(enabled);
    try {
      const token = Cookies.get('token');
      if (!token) { onLogout(); return; }
      await fetch(`${API_BASE}/futuristic-wheel/auto-sync`, {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      });
    } catch (e) {
      setAutoSync(!enabled); // revert on error
      alert('Failed to save auto-sync setting');
    }
  };

  // ── Delta save ──────────────────────────────────────────────────────────────
  const handleDeltaSave = async (symbol) => {
    const val = parseFloat(deltaInputs[symbol]);
    if (isNaN(val) || val < 0 || val > 1) {
      alert('Delta must be between 0 and 1  (e.g. 0.35 for Δ 0.35)');
      return;
    }
    setSavingDelta(prev => ({ ...prev, [symbol]: true }));
    try {
      const token = Cookies.get('token');
      const resp = await fetch(`${API_BASE}/futuristic-wheel/delta`, {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, delta: val }),
      });
      if (!resp.ok) throw new Error('Failed to save delta');
      await fetchData();
    } catch (e) {
      alert('Error saving delta: ' + e.message);
    } finally {
      setSavingDelta(prev => ({ ...prev, [symbol]: false }));
    }
  };

  // ── Fetch live market data (manual) ────────────────────────────────────────
  const handleFetchMarketData = async () => {
    setFetchingMarket(true);
    setMarketError(null);
    try {
      const token = Cookies.get('token');
      if (!token) { onLogout(); return; }
      const resp = await fetch(`${API_BASE}/futuristic-wheel/market-data`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.status === 401) { onLogout(); return; }
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to fetch market data');
      }
      const result = await resp.json();
      setMarketData(result.results || {});
    } catch (e) {
      setMarketError(e.message);
    } finally {
      setFetchingMarket(false);
    }
  };

  /** Return the matching options greek entry from marketData for a given LEAP row. */
  const getLiveGreeks = (symbol, strike, expiry) => {
    const symData = marketData[symbol];
    if (!symData) return null;
    const norm = normalizeExpiry(expiry || '');
    return symData.leaps?.find(l =>
      Math.abs((l.strike || 0) - parseFloat(strike || 0)) < 0.01 &&
      l.expiry === norm
    ) ?? null;
  };

  // ── Loading / error states ──────────────────────────────────────────────────
  if (loading) return (
    <div className="fw-page fw-center">
      <span style={{ fontSize: '2rem' }}>⏳</span>
      <p>Loading Futuristic Wheel…</p>
    </div>
  );

  if (error) return (
    <div className="fw-page fw-center">
      <span style={{ fontSize: '2rem' }}>⚠️</span>
      <p className="fw-red">{error}</p>
      <button className="fw-sync-btn" onClick={fetchData}>Retry</button>
    </div>
  );

  const { leaps, short_calls } = data;
  const hasLeaps = leaps.current.length > 0;
  const hasCalls = short_calls.all.length > 0;

  // Bar chart data: closed/expired trades oldest→newest
  const tradeBarData = [...short_calls.all]
    .filter(c => c.status !== 'open' && c.pnl != null)
    .reverse()
    .map((c, i) => ({
      idx:    i + 1,
      label:  `${c.symbol} ${c.strike ?? ''} ${fmtDate(c.expiry)}`.trim(),
      pnl:    c.pnl,
      status: c.status,
    }));

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="fw-page">

      {/* Header */}
      <div className="fw-header">
        <button className="fw-back" onClick={() => navigate('/')}>← Home</button>
        <h1>⚡ Futuristic Wheel</h1>
        <button className="fw-sync-btn" onClick={handleSync} disabled={syncing || purging}>
          {syncing ? '⏳ Syncing…' : '🔄 Sync'}
        </button>
        <button className="fw-purge-btn" onClick={handlePurge} disabled={purging || syncing}>
          {purging ? '⏳ Purging…' : '🗑️ Purge Data'}
        </button>
        <label className="fw-autosync-label" title="Automatically sync every day at 02:00 CET">
          <span className="fw-autosync-text">Auto-sync 02:00</span>
          <span className={`fw-autosync-track ${autoSync ? 'fw-autosync-on' : ''}`}
                onClick={() => handleAutoSyncToggle({ target: { checked: !autoSync } })}>
            <span className="fw-autosync-thumb" />
          </span>
        </label>
      </div>

      {/* Sync result banner */}
      {syncResult && (
        <div className={`fw-banner ${syncResult.status === 'success' ? 'fw-banner-ok' : 'fw-banner-err'}`}>
          {syncResult.status === 'success'
            ? (syncResult.message ?? `✅ ${syncResult.leaps_found ?? 0} LEAP(s) snapshotted (${syncResult.leap_symbols?.join(', ')}) · ${syncResult.calls_processed ?? 0} calls processed`)
            : `❌ ${syncResult.message || 'Sync failed'}`}
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════
          LEAPS SECTION
      ═══════════════════════════════════════════════════════════ */}
      <section className="fw-section">
        <div className="fw-section-header">
          <h2 className="fw-section-title">📈 LEAP Positions</h2>
          <button
            className="fw-market-btn"
            onClick={handleFetchMarketData}
            disabled={fetchingMarket || !hasLeaps}
            title="Fetch live price + greeks from Alpha Vantage (manual to preserve 25 req/day limit)"
          >
            {fetchingMarket ? '⏳ Fetching…' : '📡 Live Data'}
          </button>
        </div>
        {marketError && (
          <div className="fw-banner fw-banner-err">❌ Market data error: {marketError}</div>
        )}

        {/* Summary tiles */}
        <div className="fw-grid">
          <div className="fw-tile">
            <span className="fw-tile-icon">📦</span>
            <span className="fw-tile-label">Total Contracts</span>
            <span className="fw-tile-value fw-purple">{leaps.total_contracts}</span>
          </div>
          <div className="fw-tile">
            <span className="fw-tile-icon">💰</span>
            <span className="fw-tile-label">Total Cost Basis</span>
            <span className="fw-tile-value">{fmt$(leaps.total_cost)}</span>
          </div>
          <div className="fw-tile">
            <span className="fw-tile-icon">📊</span>
            <span className="fw-tile-label">Unrealized P&L</span>
            <span className={`fw-tile-value ${leaps.total_unrealized_pnl >= 0 ? 'fw-green' : 'fw-red'}`}>
              {fmt$(leaps.total_unrealized_pnl)}
            </span>
          </div>
          <div className="fw-tile">
            <span className="fw-tile-icon">Δ</span>
            <span className="fw-tile-label">Total Delta</span>
            <span className={`fw-tile-value ${leaps.total_delta != null ? 'fw-purple' : ''}`}>
              {leaps.total_delta != null ? leaps.total_delta.toFixed(2) : '—'}
            </span>
          </div>
          <div className="fw-tile">
            <span className="fw-tile-icon">➕</span>
            <span className="fw-tile-label">Extra Contracts</span>
            <span className="fw-tile-value fw-green">{leaps.extra_contracts ?? 0}</span>
          </div>
          <div className="fw-tile">
            <span className="fw-tile-icon">💎</span>
            <span className="fw-tile-label">Value of Extra Contracts</span>
            <span className="fw-tile-value fw-green">{fmt$(leaps.extra_contracts_value)}</span>
          </div>
        </div>

        {/* Delta input (one row per LEAP symbol) */}
        {hasLeaps && (
          <div className="fw-delta-row">
            {leaps.current.map(leap => {
              const inputVal = deltaInputs[leap.symbol] ?? '';
              const parsed   = parseFloat(inputVal);
              const liveTotal = !isNaN(parsed)
                ? (leap.contracts * 100 * parsed).toFixed(2)
                : leap.total_delta != null
                  ? leap.total_delta.toFixed(2)
                  : '—';
              return (
                <div className="fw-delta-box" key={leap.symbol}>
                  <label>{leap.symbol} — Δ per contract:</label>
                  <input
                    className="fw-delta-input"
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    placeholder="0.35"
                    value={inputVal}
                    onChange={e => setDeltaInputs(prev => ({ ...prev, [leap.symbol]: e.target.value }))}
                    onKeyDown={e => e.key === 'Enter' && handleDeltaSave(leap.symbol)}
                  />
                  <button
                    className="fw-delta-save-btn"
                    onClick={() => handleDeltaSave(leap.symbol)}
                    disabled={!!savingDelta[leap.symbol]}
                  >
                    {savingDelta[leap.symbol] ? '…' : 'Save'}
                  </button>
                  <span className="fw-delta-hint">Total Δ: {liveTotal}</span>
                </div>
              );
            })}
          </div>
        )}

        {/* Current positions table */}
        {hasLeaps && (
          <div className="fw-card">
            <h3>Current Positions</h3>
            <div className="fw-table-wrapper">
              <table className="fw-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Contracts</th>
                    <th>Strike</th>
                    <th>Expiry</th>
                    <th>Cost / Share</th>
                    <th>Mark Price</th>
                    <th>Unrealized P&L</th>
                    <th>Delta (Δ)</th>
                    <th>Total Δ</th>
                    <th>Live Price</th>
                    <th>Live Δ</th>
                    <th>Live Γ</th>
                  </tr>
                </thead>
                <tbody>
                  {leaps.current.map((l, i) => (
                    <tr key={i}>
                      <td>{l.symbol}</td>
                      <td>{l.contracts}</td>
                      <td>{l.strike ?? '—'}</td>
                      <td>{l.expiry ? fmtDate(l.expiry) : '—'}</td>
                      <td>{fmt$(l.cost_basis)}</td>
                      <td>{fmt$(l.mark_price)}</td>
                      <td className={l.unrealized_pnl >= 0 ? 'fw-green' : 'fw-red'}>
                        {fmt$(l.unrealized_pnl)}
                      </td>
                      <td className="fw-purple">
                        {l.delta != null ? l.delta.toFixed(3) : '—'}
                      </td>
                      <td className="fw-purple">
                        {l.total_delta != null ? l.total_delta.toFixed(2) : '—'}
                      </td>
                      <td className="fw-cyan">
                        {marketData[l.symbol]?.price != null ? fmt$(marketData[l.symbol].price) : '—'}
                      </td>
                      <td className="fw-cyan">
                        {(() => { const g = getLiveGreeks(l.symbol, l.strike, l.expiry); return g?.delta != null ? g.delta.toFixed(4) : '—'; })()}
                      </td>
                      <td className="fw-cyan">
                        {(() => { const g = getLiveGreeks(l.symbol, l.strike, l.expiry); return g?.gamma != null ? g.gamma.toFixed(5) : '—'; })()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Contract count over time chart */}
        {leaps.series.length > 0 ? (
          <div className="fw-card">
            <h3>Contract Count Over Time</h3>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={leaps.series} margin={{ top: 6, right: 16, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="leapGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#a855f7" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#a855f7" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2a40" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: '#888', fontSize: 11 }} tickLine={false} />
                <YAxis
                  tick={{ fill: '#888', fontSize: 11 }} tickLine={false} axisLine={false}
                  allowDecimals={false}
                  domain={[0, dataMax => Math.max(dataMax + 1, 2)]}
                />
                <Tooltip content={<LeapTooltip />} cursor={{ stroke: 'rgba(168,85,247,0.3)', strokeWidth: 1 }} />
                <Area
                  type="monotone" dataKey="total_contracts"
                  stroke="#a855f7" fill="url(#leapGrad)" strokeWidth={2}
                  dot={{ r: 5, fill: '#a855f7', strokeWidth: 0 }}
                  activeDot={{ r: 6 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="fw-card">
            <div className="fw-empty">
              📭 No LEAP snapshot data yet — click <strong>Sync</strong> to capture today's positions.
            </div>
          </div>
        )}
      </section>

      {/* ═══════════════════════════════════════════════════════════
          SHORT CALLS SECTION
      ═══════════════════════════════════════════════════════════ */}
      <section className="fw-section">
        <h2 className="fw-section-title">📞 Short Calls</h2>

        {/* Stats tiles — 5 columns */}
        <div className="fw-grid fw-grid-5">
          <div className="fw-tile">
            <span className="fw-tile-icon">📈</span>
            <span className="fw-tile-label">Total P&L</span>
            <span className={`fw-tile-value ${short_calls.stats.total_pnl >= 0 ? 'fw-green' : 'fw-red'}`}>
              {fmt$(short_calls.stats.total_pnl)}
            </span>
          </div>
          <div className="fw-tile">
            <span className="fw-tile-icon">💰</span>
            <span className="fw-tile-label">Realized P&L</span>
            <span className={`fw-tile-value ${short_calls.stats.total_realized_pnl >= 0 ? 'fw-green' : 'fw-red'}`}>
              {fmt$(short_calls.stats.total_realized_pnl)}
            </span>
          </div>
          <div className="fw-tile">
            <span className="fw-tile-icon">🎯</span>
            <span className="fw-tile-label">Win Rate</span>
            <span className={`fw-tile-value ${short_calls.stats.win_rate >= 50 ? 'fw-green' : 'fw-red'}`}>
              {short_calls.stats.win_rate}%
            </span>
          </div>
          <div className="fw-tile">
            <span className="fw-tile-icon">📊</span>
            <span className="fw-tile-label">Avg P&L / Trade</span>
            <span className={`fw-tile-value ${short_calls.stats.avg_pnl >= 0 ? 'fw-green' : 'fw-red'}`}>
              {fmt$(short_calls.stats.avg_pnl)}
            </span>
          </div>
          <div className="fw-tile">
            <span className="fw-tile-icon">🔓</span>
            <span className="fw-tile-label">Open Trades</span>
            <span className="fw-tile-value fw-blue">{short_calls.stats.open_count}</span>
          </div>
        </div>

        {/* Charts: cumulative P&L + per-trade bar */}
        {short_calls.daily_pnl_series.length > 0 && (
          <div className="fw-charts-row">

            {/* Cumulative P&L area chart */}
            <div className="fw-card" style={{ marginBottom: 0 }}>
              <h3>Cumulative Total P&L (from 20 Feb)</h3>
              <ResponsiveContainer width="100%" height={230}>
                <AreaChart data={short_calls.daily_pnl_series} margin={{ top: 6, right: 16, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#00ff88" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#00ff88" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2a2a40" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill: '#888', fontSize: 10 }} tickLine={false} />
                  <YAxis
                    tick={{ fill: '#888', fontSize: 11 }} tickLine={false} axisLine={false}
                    tickFormatter={v => `$${v}`}
                  />
                  <Tooltip
                    content={<CumulativeTooltip />}
                    cursor={{ stroke: 'rgba(0,255,136,0.2)', strokeWidth: 1 }}
                  />
                  <ReferenceLine y={0} stroke="#555" strokeDasharray="4 2" />
                  <Area
                    type="monotone" dataKey="cumulative_pnl"
                    stroke="#00ff88" fill="url(#pnlGrad)" strokeWidth={2} dot={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* Per-trade P&L bar chart */}
            {tradeBarData.length > 0 && (
              <div className="fw-card" style={{ marginBottom: 0 }}>
                <h3>P&L Per Trade</h3>
                <ResponsiveContainer width="100%" height={230}>
                  <BarChart data={tradeBarData} margin={{ top: 6, right: 16, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2a2a40" vertical={false} />
                    <XAxis
                      dataKey="idx"
                      tick={{ fill: '#888', fontSize: 10 }} tickLine={false}
                    />
                    <YAxis
                      tick={{ fill: '#888', fontSize: 11 }} tickLine={false} axisLine={false}
                      tickFormatter={v => `$${v}`}
                    />
                    <Tooltip content={<TradeBarTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                    <ReferenceLine y={0} stroke="#555" strokeDasharray="4 2" />
                    <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
                      {tradeBarData.map((entry, i) => (
                        <Cell key={i} fill={entry.pnl >= 0 ? '#00ff88' : '#ff4444'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        )}

        {/* Trade history table */}
        {hasCalls ? (
          <div className="fw-card">
            <h3>Trade History</h3>
            <div className="fw-table-wrapper">
              <table className="fw-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Strike</th>
                    <th>Expiry</th>
                    <th>Contracts</th>
                    <th>Opened</th>
                    <th>Open Price</th>
                    <th>Closed / Expired</th>
                    <th>Close Price</th>
                    <th>Premium</th>
                    <th>P&L</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {short_calls.all.map((c, i) => (
                    <tr key={i}>
                      <td>{c.symbol}</td>
                      <td>{c.strike ?? '—'}</td>
                      <td>{fmtDate(c.expiry)}</td>
                      <td>{c.contracts}</td>
                      <td>{fmtDate(c.open_date)}</td>
                      <td>{fmt$(c.open_price)}</td>
                      <td>{c.close_date ? fmtDate(c.close_date) : '—'}</td>
                      <td>
                        {c.close_price != null && c.status !== 'expired'
                          ? fmt$(c.close_price)
                          : c.status === 'expired' ? 'Expired' : '—'}
                      </td>
                      <td className="fw-green">{fmt$(c.premium_received)}</td>
                      <td className={c.pnl != null ? (c.pnl >= 0 ? 'fw-green' : 'fw-red') : ''}>
                        {c.pnl != null ? fmt$(c.pnl) : '—'}
                      </td>
                      <td>
                        <span className={`fw-badge fw-badge-${c.status}`}>{c.status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="fw-card">
            <div className="fw-empty">
              📭 No short call data yet — click <strong>Sync</strong> to load from IBKR.
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

export default FuturisticWheel;
