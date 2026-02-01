import React, { useState, useEffect } from 'react';
import Cookies from 'js-cookie';
import { useNavigate } from 'react-router-dom';
import './AccountSettings.css';

const API_BASE = 'http://localhost:8000';

function AccountSettings({ onLogout }) {
  const [settings, setSettings] = useState({
    ibkr_token: '',
    ibkr_query_id: ''
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const token = Cookies.get("token");
      if (!token) {
        throw new Error("No authentication token found");
      }

      const headers = { 'Authorization': `Bearer ${token}` };
      const response = await fetch(`${API_BASE}/account_settings`, { headers });
      
      if (response.status === 401) {
        onLogout();
        return;
      }

      if (!response.ok) {
        throw new Error('Failed to fetch settings');
      }

      const data = await response.json();
      setSettings({
        ibkr_token: data.ibkr_token || '',
        ibkr_query_id: data.ibkr_query_id || ''
      });
    } catch (e) {
      console.error(e);
      if (e.message === "No authentication token found") {
        onLogout();
      } else {
        setError('Failed to load settings.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      setSaving(true);
      setError(null);
      setSuccessMsg('');

      const token = Cookies.get("token");
      if (!token) throw new Error("No authentication token found");

      const headers = { 
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };

      const response = await fetch(`${API_BASE}/account_settings`, { 
        method: 'POST',
        headers,
        body: JSON.stringify(settings)
      });

      if (response.status === 401) {
        onLogout();
        return;
      }

      if (!response.ok) {
        throw new Error('Failed to save settings');
      }

      setSuccessMsg('Settings saved successfully!');
    } catch (e) {
      console.error(e);
      setError('Failed to save settings.');
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setSettings(prev => ({
      ...prev,
      [name]: value
    }));
  };

  if (loading) return <div className="loading">Loading settings...</div>;

  return (
    <div className="account-settings-container">
      <div className="settings-header">
          <h1>Account Settings</h1>
          <button onClick={() => navigate('/dashboard')} className="back-btn">Back to Dashboard</button>
      </div>

      {error && <div className="error-msg">{error}</div>}
      {successMsg && <div className="success-msg">{successMsg}</div>}

      <form onSubmit={handleSubmit} className="settings-form">
        <div className="form-group">
          <label htmlFor="ibkr_token">IBKR Token</label>
          <input
            type="text"
            id="ibkr_token"
            name="ibkr_token"
            value={settings.ibkr_token}
            onChange={handleChange}
            placeholder="Enter IBKR Token"
          />
        </div>

        <div className="form-group">
          <label htmlFor="ibkr_query_id">IBKR Query ID</label>
          <input
            type="text"
            id="ibkr_query_id"
            name="ibkr_query_id"
            value={settings.ibkr_query_id}
            onChange={handleChange}
            placeholder="Enter IBKR Query ID"
          />
        </div>

        <button type="submit" disabled={saving} className="save-btn">
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
      </form>
    </div>
  );
}

export default AccountSettings;
