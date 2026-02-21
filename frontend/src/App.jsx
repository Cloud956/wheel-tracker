import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Cookies from 'js-cookie';
import Login from './components/logins/login';
import Home from './components/Home';
import Dashboard from './components/Dashboard';
import PnlPage from './components/PnlPage';
import AnalyticsPage from './components/AnalyticsPage';
import AccountSettings from './components/AccountSettings';
import SnakeGame from './components/SnakeGame';
import './App.css';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    // Check if user is already logged in by checking the cookie
    const token = Cookies.get("token");
    if (token) {
      setIsAuthenticated(true);
    }
  }, []);

  const handleLoginSuccess = (credential) => {
    // In a real app, you'd verify the token with backend here
    // For now, we assume success if we get a credential
    // Store token in a cookie that expires in 7 days
    Cookies.set("token", credential, { expires: 7 });
    setIsAuthenticated(true);
  };

  const handleLogout = () => {
    Cookies.remove("token");
    setIsAuthenticated(false);
  };

  return (
    <Router>
      <div className="app">
        <Routes>
          <Route 
            path="/login" 
            element={
              !isAuthenticated ? (
                <div className="login-page">
                    <h1>Wheel Strategy Tracker Login</h1>
                    <div className="login-wrapper">
                        <Login onLoginSuccess={handleLoginSuccess} />
                    </div>
                </div>
              ) : (
                <Navigate to="/" replace />
              )
            } 
          />
          <Route
            path="/"
            element={
              isAuthenticated ? (
                <Home onLogout={handleLogout} />
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />
          <Route 
            path="/dashboard" 
            element={
              isAuthenticated ? (
                <Dashboard onLogout={handleLogout} />
              ) : (
                <Navigate to="/login" replace />
              )
            } 
          />
          <Route
            path="/pnl"
            element={
              isAuthenticated ? (
                <PnlPage onLogout={handleLogout} />
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />
          <Route
            path="/analytics"
            element={
              isAuthenticated ? (
                <AnalyticsPage onLogout={handleLogout} />
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />
          <Route 
            path="/settings" 
            element={
              isAuthenticated ? (
                <AccountSettings onLogout={handleLogout} />
              ) : (
                <Navigate to="/login" replace />
              )
            } 
          />
          <Route 
            path="/snake" 
            element={
              isAuthenticated ? (
                <SnakeGame />
              ) : (
                <Navigate to="/login" replace />
              )
            } 
          />
          <Route path="*" element={<Navigate to={isAuthenticated ? "/" : "/login"} replace />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
