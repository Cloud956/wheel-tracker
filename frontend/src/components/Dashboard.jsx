import React, { useState, useEffect } from 'react';
import Cookies from 'js-cookie';
import { useNavigate } from 'react-router-dom';
import WheelSummaryTable from './WheelSummaryTable';
import TradeHistoryTable from './TradeHistoryTable';
import Logout from './logins/logout';

// Use localhost instead of 0.0.0.0
const API_BASE = 'http://localhost:8000';

function Dashboard({ onLogout }) {
  const [wheelSummary, setWheelSummary] = useState([]);
  const [tradeHistory, setTradeHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchAllData();
  }, []);

  const fetchAllData = async () => {
    try {
      setLoading(true);
      setError(null);

      const token = Cookies.get("token");
      if (!token) {
        throw new Error("No authentication token found");
      }

      const headers = {
        'Authorization': `Bearer ${token}`
      };

      const [summaryResp, historyResp] = await Promise.all([
        fetch(`${API_BASE}/wheel-summary`, { headers }),
        fetch(`${API_BASE}/history`, { headers })
      ]);

      if (summaryResp.status === 401 || historyResp.status === 401) {
        onLogout(); // Token invalid or expired
        return;
      }

      if (!summaryResp.ok || !historyResp.ok) {
        throw new Error('Failed to fetch data from backend');
      }

      const summaryData = await summaryResp.json();
      const historyData = await historyResp.json();

      setWheelSummary(summaryData);
      setTradeHistory(historyData);
    } catch (e) {
      console.error('API Error:', e);
      if (e.message === "No authentication token found") {
          onLogout();
      } else {
        setError(`Failed to connect to backend at ${API_BASE}. Is it running?`);
      }
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="loading">Loading data...</div>;
  }

  if (error) {
    return <div className="error">{error}</div>;
  }

  return (
    <div className="dashboard">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h1>Wheel Strategy Tracker version 1.0</h1>
          <div style={{ display: 'flex', gap: '10px' }}>
              <button className="btn btn-settings" onClick={() => navigate('/settings')}>Settings</button>
              <Logout onLogout={onLogout} />
          </div>
      </div>

      <h2>List of Wheels</h2>
      <WheelSummaryTable data={wheelSummary} />

      <h2>Complete Trade History</h2>
      <TradeHistoryTable data={tradeHistory} />
    </div>
  );
}

export default Dashboard;
