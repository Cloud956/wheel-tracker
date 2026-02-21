import React from 'react';
import { useNavigate } from 'react-router-dom';
import Logout from './logins/logout';
import './Home.css';

function Home({ onLogout }) {
  const navigate = useNavigate();

  return (
    <div className="home-page">
      <div className="home-header">
        <h1>🎡 Wheel Strategy Tracker</h1>
        <Logout onLogout={onLogout} />
      </div>

      <p className="home-subtitle">Select a module to get started</p>

      <div className="home-cards">
        <div className="home-card" onClick={() => navigate('/dashboard')}>
          <div className="home-card-icon">📋</div>
          <h2>Wheels Overview</h2>
          <p>View all your wheels, trade history, and sync data from IBKR.</p>
          <button className="home-card-btn">Open →</button>
        </div>

        <div className="home-card" onClick={() => navigate('/pnl')}>
          <div className="home-card-icon">📈</div>
          <h2>PnL Tracker</h2>
          <p>Track your daily strategy performance over time with an interactive chart.</p>
          <button className="home-card-btn">Open →</button>
        </div>

        <div className="home-card" onClick={() => navigate('/analytics')}>
          <div className="home-card-icon">📊</div>
          <h2>Wheel Analytics</h2>
          <p>Win rate, average PnL, hold times, monthly performance, symbol breakdown and more.</p>
          <button className="home-card-btn">Open →</button>
        </div>

        <div className="home-card" onClick={() => navigate('/snake')}>
          <div className="home-card-icon">🐍</div>
          <h2>Snake Game</h2>
          <p>Take a break and play Snake. Compete for the top spot on the leaderboard.</p>
          <button className="home-card-btn">Play →</button>
        </div>
      </div>
    </div>
  );
}

export default Home;
