import { useState, useEffect } from 'react'
import { api } from '../api/client.js'
import '../styles/Analytics.css'

function Analytics() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchStats = async () => {
      try {
        setLoading(true)
        const data = await api.getStats()
        setStats(data)
        setError(null)
      } catch (err) {
        setError(err.message)
        console.error('Error fetching stats:', err)
      } finally {
        setLoading(false)
      }
    }

    fetchStats()
    const interval = setInterval(fetchStats, 5000)
    return () => clearInterval(interval)
  }, [])

  if (loading && !stats) {
    return <div className="analytics-container"><p>Loading analytics...</p></div>
  }

  if (error) {
    return (
      <div className="analytics-container">
        <div className="error">Error: {error}</div>
      </div>
    )
  }

  if (!stats) {
    return <div className="analytics-container"><p>No analytics data</p></div>
  }

  const llmPercentage = (stats.llm_call_rate * 100).toFixed(1)
  const fastPathPercentage = (100 - stats.llm_call_rate * 100).toFixed(1)

  return (
    <div className="analytics-container">
      <h2>Analytics & Metrics</h2>

      <div className="stats-grid">
        <div className="stat-card">
          <h3>Total Sessions</h3>
          <p className="big-number">{stats.total_sessions}</p>
        </div>

        <div className="stat-card">
          <h3>Total Commands</h3>
          <p className="big-number">{stats.total_commands}</p>
        </div>

        <div className="stat-card">
          <h3>Avg Commands/Session</h3>
          <p className="big-number">{stats.avg_commands_per_session.toFixed(1)}</p>
        </div>

        <div className="stat-card">
          <h3>LLM Call Rate</h3>
          <div className="rate-display">
            <p className="big-number">{llmPercentage}%</p>
            <div className="rate-bar">
              <div
                className="rate-bar-fill llm"
                style={{ width: `${llmPercentage}%` }}
              ></div>
            </div>
            <small>Fast-Path: {fastPathPercentage}%</small>
          </div>
        </div>
      </div>

      <div className="top-commands">
        <h3>Top Commands</h3>
        {stats.top_commands && stats.top_commands.length > 0 ? (
          <table className="commands-table">
            <thead>
              <tr>
                <th>Command</th>
                <th>Count</th>
                <th>Usage</th>
              </tr>
            </thead>
            <tbody>
              {stats.top_commands.map(([cmd, count], idx) => {
                const percentage =
                  stats.total_commands > 0
                    ? ((count / stats.total_commands) * 100).toFixed(1)
                    : 0
                return (
                  <tr key={idx}>
                    <td className="cmd-name">{cmd}</td>
                    <td className="cmd-count">{count}</td>
                    <td className="cmd-usage">
                      <div className="usage-bar">
                        <div
                          className="usage-bar-fill"
                          style={{ width: `${percentage}%` }}
                        ></div>
                      </div>
                      <span>{percentage}%</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : (
          <p className="no-data">No command data yet</p>
        )}
      </div>
    </div>
  )
}

export default Analytics
