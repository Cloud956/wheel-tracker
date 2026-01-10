import React, { useState, useEffect } from 'react'
import WheelSummaryTable from './components/WheelSummaryTable'
import TradeHistoryTable from './components/TradeHistoryTable'
import './App.css'

const API_BASE = 'http://localhost:8000' 


function App() {
  const [wheelSummary, setWheelSummary] = useState([])
  const [tradeHistory, setTradeHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchAllData()
  }, [])

  const fetchAllData = async () => {
    try {
      setLoading(true)
      setError(null)

      const [summaryResp, historyResp] = await Promise.all([
        fetch(`${API_BASE}/wheel-summary`),
        fetch(`${API_BASE}/history`)
      ])

      if (!summaryResp.ok || !historyResp.ok) {
        throw new Error('Failed to fetch data from backend')
      }

      const summaryData = await summaryResp.json()
      const historyData = await historyResp.json()

      setWheelSummary(summaryData)
      setTradeHistory(historyData)
    } catch (e) {
      console.error('API Error:', e)
      setError('Failed to connect to backend. Is it running on port 8000?')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <div className="loading">Loading data...</div>
  }

  if (error) {
    return <div className="error">{error}</div>
  }

  return (
    <div className="app">
      <h1>Wheel Strategy Tracker version 1.0</h1>
      
      <h2>List of Wheels</h2>
      <WheelSummaryTable data={wheelSummary} />

      <h2>Complete Trade History</h2>
      <TradeHistoryTable data={tradeHistory} />
    </div>
  )
}

export default App
