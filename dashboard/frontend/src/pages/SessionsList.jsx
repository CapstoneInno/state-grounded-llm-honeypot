import { useState, useEffect } from 'react'
import { api } from '../api/client.js'
import '../styles/SessionsList.css'

function SessionsList({ onSelectSession }) {
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [liveStatus, setLiveStatus] = useState('● disconnected')

  useEffect(() => {
    const fetchSessions = async () => {
      try {
        setLoading(true)
        const data = await api.getSessions(50, 0)
        setSessions(data)
        setError(null)
      } catch (err) {
        setError(err.message)
        console.error('Error fetching sessions:', err)
      } finally {
        setLoading(false)
      }
    }

    fetchSessions()
    const interval = setInterval(fetchSessions, 3000)

    // Subscribe to live stream
    const ws = api.subscribeToStream(
      (event) => {
        if (event.type === 'command') {
          setLiveStatus('● live')
          // Refresh sessions on new command
          fetchSessions()
          setTimeout(() => setLiveStatus('● connected'), 2000)
        }
      },
      () => setLiveStatus('● error')
    )

    return () => {
      clearInterval(interval)
      if (ws && ws.readyState === WebSocket.OPEN) ws.close()
    }
  }, [])

  if (loading && sessions.length === 0) {
    return <div className="sessions-container"><p>Loading sessions...</p></div>
  }

  return (
    <div className="sessions-container">
      <div className="sessions-header">
        <h2>Sessions</h2>
        <span className={`live-status ${liveStatus.includes('live') ? 'live' : ''}`}>
          {liveStatus}
        </span>
      </div>

      {error && <div className="error">Error: {error}</div>}

      {sessions.length === 0 ? (
        <p className="no-data">No sessions yet</p>
      ) : (
        <table className="sessions-table">
          <thead>
            <tr>
              <th>Session ID</th>
              <th>Source IP</th>
              <th>Commands</th>
              <th>Fast-Path</th>
              <th>LLM</th>
              <th>Started At</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((session) => (
              <tr
                key={session.session_id}
                className="session-row"
                onClick={() => onSelectSession(session.session_id)}
              >
                <td className="session-id">{session.session_id}</td>
                <td>{session.src_ip || 'unknown'}</td>
                <td className="command-count">{session.command_count}</td>
                <td className="fast-path-count">{session.fast_path_calls}</td>
                <td className="llm-count">{session.llm_calls}</td>
                <td className="timestamp">
                  {new Date(session.started_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default SessionsList
