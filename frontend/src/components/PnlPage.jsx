import React, { useState, useEffect } from 'react';
import Cookies from 'js-cookie';
import { useNavigate } from 'react-router-dom';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine
} from 'recharts';
import './PnlPage.css';

const API_BASE = '/api';

function PnlPage({ onLogout }) {
  const navigate = useNavigate();
  const [pnlData, setPnlData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchPnlData();
  }, []);

  const fetchPnlData = async () => {
    try {
      setLoading(true);
      setError(null);
      const token = Cookies.get('token');
      if (!token) { onLogout(); return; }

      const resp = await fetch(`${API_BASE}/pnl`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.status === 401) { onLogout(); return; }
      if (!resp.ok) throw new Error('Failed to fetch PnL data');

      const data = await resp.json();
      setPnlData(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  // Stats derived from data
  const totalPnl = pnlData.length ? pnlData[pnlData.length - 1]?.cumulative_pnl ?? 0 : 0;
  const bestDay = pnlData.length ? Math.max(...pnlData.map(d => d.daily_pnl)) : 0;
  const worstDay = pnlData.length ? Math.min(...pnlData.map(d => d.daily_pnl)) : 0;

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    return (
      <div className="pnl-tooltip">
        <p className="pnl-tooltip-date">{label}</p>
        <p>Daily: <span className={d.daily_pnl >= 0 ? 'text-green' : 'text-red'}>${d.daily_pnl?.toFixed(2)}</span></p>
        <p>Cumulative: <span className={d.cumulative_pnl >= 0 ? 'text-green' : 'text-red'}>${d.cumulative_pnl?.toFixed(2)}</span></p>
      </div>
    );
  };

  return (
    <div className="pnl-page">
      {/* Header */}
      <div className="pnl-header">
        <button className="back-btn" onClick={() => navigate('/')}>← Home</button>
        <h1>📈 PnL Tracker</h1>
      </div>

      {/* Stats row */}
      <div className="pnl-stats">
        <div className="pnl-stat">
          <span className="pnl-stat-label">Total PnL</span>
          <span className={`pnl-stat-value ${totalPnl >= 0 ? 'text-green' : 'text-red'}`}>
            ${totalPnl.toFixed(2)}
          </span>
        </div>
        <div className="pnl-stat">
          <span className="pnl-stat-label">Best Day</span>
          <span className="pnl-stat-value text-green">${bestDay.toFixed(2)}</span>
        </div>
        <div className="pnl-stat">
          <span className="pnl-stat-label">Worst Day</span>
          <span className={`pnl-stat-value ${worstDay < 0 ? 'text-red' : 'text-green'}`}>${worstDay.toFixed(2)}</span>
        </div>
        <div className="pnl-stat">
          <span className="pnl-stat-label">Days Tracked</span>
          <span className="pnl-stat-value">{pnlData.length}</span>
        </div>
      </div>

      {/* Chart */}
      <div className="pnl-chart-card">
        <h2>Cumulative PnL Over Time</h2>
        {loading ? (
          <div className="pnl-placeholder">Loading data...</div>
        ) : error ? (
          <div className="pnl-placeholder pnl-error">{error}</div>
        ) : pnlData.length === 0 ? (
          <div className="pnl-placeholder">
            <span>📊</span>
            <p>No PnL data available yet.</p>
            <p className="pnl-placeholder-sub">Data will appear here after the first nightly sync.</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={360}>
            <AreaChart data={pnlData} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
              <defs>
                <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#00ff88" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#00ff88" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2a40" />
              <XAxis dataKey="date" tick={{ fill: '#888', fontSize: 12 }} tickLine={false} />
              <YAxis
                tick={{ fill: '#888', fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => `$${v}`}
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={0} stroke="#555" strokeDasharray="4 2" />
              <Area
                type="monotone"
                dataKey="cumulative_pnl"
                stroke="#00ff88"
                strokeWidth={2}
                fill="url(#pnlGradient)"
                dot={false}
                activeDot={{ r: 5, fill: '#00ff88' }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

    </div>
  );
}

export default PnlPage;
