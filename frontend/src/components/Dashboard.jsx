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
  const [syncResults, setSyncResults] = useState(null);
  const [syncing, setSyncing] = useState(false);
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

  const handleSync = async () => {
    try {
      setSyncing(true);
      setSyncResults(null); 
      const token = Cookies.get("token");
      if (!token) throw new Error("No authentication token found");

      const response = await fetch(`${API_BASE}/sync`, { 
        headers: { 'Authorization': `Bearer ${token}` } 
      });

      if (response.status === 401) {
        onLogout();
        return;
      }
      
      const data = await response.json();
      if (!response.ok) {
        alert("Sync Failed: " + (data.detail || "Unknown error"));
      } else {
        setSyncResults(data);
      }
    } catch (e) {
      alert("Sync Error: " + e.message);
    } finally {
      setSyncing(false);
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
              <button className="btn" onClick={handleSync} disabled={syncing}>
                {syncing ? 'Syncing...' : 'Sync IBKR'}
              </button>
              <button className="btn btn-settings" onClick={() => navigate('/settings')}>Settings</button>
              <Logout onLogout={onLogout} />
          </div>
      </div>

      {syncResults && (
        <div style={{ padding: '20px', background: '#f5f5f5', margin: '20px 0', border: '1px solid #ddd', color: '#333' }}>
          <h3 style={{color: '#333'}}>Sync Results (Categorization Test)</h3>
          <p style={{color: '#333'}}>Status: {syncResults.status}</p>
          <p style={{color: '#333'}}>Count: {syncResults.count}</p>
          {syncResults.categorized_trades && syncResults.categorized_trades.length > 0 ? (
            <table className="summary-table" style={{ width: '100%', fontSize: '0.9em', color: '#111' }}>
              <thead>
                <tr style={{background: '#e0e0e0', color: '#000'}}>
                  <th style={{padding: '8px', textAlign: 'left'}}>Date</th>
                  <th style={{padding: '8px', textAlign: 'left'}}>Symbol</th>
                  <th style={{padding: '8px', textAlign: 'left'}}>Category</th>
                  <th style={{padding: '8px', textAlign: 'left'}}>Action Needed</th>
                  <th style={{padding: '8px', textAlign: 'left'}}>Details</th>
                </tr>
              </thead>
              <tbody>
                {syncResults.categorized_trades.map((t, i) => (
                  <tr key={i} style={{borderBottom: '1px solid #ddd', background: i % 2 === 0 ? '#fff' : '#f9f9f9'}}>
                    <td style={{padding: '8px', color: '#333'}}>{t.date.split('T')[0]}</td>
                    <td style={{padding: '8px', color: '#333'}}>{t.symbol}</td>
                    <td style={{padding: '8px', color: '#333'}}><b>{t.action}</b></td>
                    <td style={{padding: '8px', color: '#333'}}>
                      <span style={{
                        padding: '4px 8px', 
                        borderRadius: '4px',
                        background: t.suggested_action === 'Start New Wheel' ? '#d4edda' :
                                    t.suggested_action === 'Close Open Wheel' ? '#f8d7da' : '#fff3cd',
                        color: t.suggested_action === 'Start New Wheel' ? '#155724' :
                               t.suggested_action === 'Close Open Wheel' ? '#721c24' : '#856404'
                      }}>
                        {t.suggested_action}
                      </span>
                    </td>
                    <td style={{padding: '8px', color: '#333'}}>{t.details}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p style={{color: '#333'}}>No new trades found to categorize.</p>
          )}
          <button onClick={() => setSyncResults(null)} style={{marginTop: '10px'}}>Close Results</button>
        </div>
      )}

      <h2>List of Wheels</h2>
      <WheelSummaryTable data={wheelSummary} />

      <h2>Complete Trade History</h2>
      <TradeHistoryTable data={tradeHistory} />
    </div>
  );
}

export default Dashboard;
