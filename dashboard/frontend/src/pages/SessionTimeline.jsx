import { useState, useEffect } from 'react'
import { api } from '../api/client.js'
import '../styles/SessionTimeline.css'

function SessionTimeline({ sessionId, onBack }) {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchSessionDetail = async () => {
      try {
        setLoading(true)
        const data = await api.getSessionDetail(sessionId)
        setSession(data)
        setError(null)
      } catch (err) {
        setError(err.message)
        console.error('Error fetching session detail:', err)
      } finally {
        setLoading(false)
      }
    }

    fetchSessionDetail()
    const interval = setInterval(fetchSessionDetail, 2000)
    return () => clearInterval(interval)
  }, [sessionId])

  if (loading && !session) {
    return (
      <div className="timeline-container">
        <button className="back-btn" onClick={onBack}>← Back to Sessions</button>
        <p>Loading session details...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="timeline-container">
        <button className="back-btn" onClick={onBack}>← Back to Sessions</button>
        <div className="error">Error: {error}</div>
      </div>
    )
  }

  if (!session) {
    return (
      <div className="timeline-container">
        <button className="back-btn" onClick={onBack}>← Back to Sessions</button>
        <p>Session not found</p>
      </div>
    )
  }

  return (
    <div className="timeline-container">
      <button className="back-btn" onClick={onBack}>← Back to Sessions</button>

      <div className="session-header">
        <div className="session-meta">
          <h2>Session {session.session_id}</h2>
          <p className="session-ip">
            <strong>IP:</strong> {session.src_ip || 'unknown'}
          </p>
          <p className="session-time">
            <strong>Started:</strong> {new Date(session.started_at).toLocaleString()}
            {session.ended_at && (
              <>
                {' | '}
                <strong>Ended:</strong> {new Date(session.ended_at).toLocaleString()}
              </>
            )}
          </p>
        </div>
        <div className="session-stats">
          <div className="stat">
            <span className="stat-value">{session.commands.length}</span>
            <span className="stat-label">Total Commands</span>
          </div>
          <div className="stat">
            <span className="stat-value fast-path">
              {session.commands.filter((c) => c.served_by === 'fast-path').length}
            </span>
            <span className="stat-label">Fast-Path</span>
          </div>
          <div className="stat">
            <span className="stat-value llm">
              {session.commands.filter((c) => c.served_by === 'llm').length}
            </span>
            <span className="stat-label">LLM</span>
          </div>
        </div>
      </div>

      <div className="commands-timeline">
        <h3>Command Timeline</h3>
        {session.commands.length === 0 ? (
          <p className="no-data">No commands recorded</p>
        ) : (
          <div className="commands-list">
            {session.commands.map((cmd, idx) => (
              <div key={idx} className="command-item">
                <div className="command-header">
                  <span className="timestamp">
                    {new Date(cmd.ts).toLocaleTimeString()}
                  </span>
                  <span className={`badge ${cmd.served_by}`}>
                    {cmd.served_by === 'fast-path' ? '⚡ Fast-Path' : '🧠 LLM'}
                  </span>
                  <span className={`exit-code ${cmd.exit_code === 0 ? 'success' : 'error'}`}>
                    {cmd.exit_code === 0 ? '✓' : '✗'} {cmd.exit_code}
                  </span>
                </div>

                <div className="command-body">
                  <div className="command-input">
                    <strong>$</strong> {cmd.input}
                  </div>

                  {cmd.cwd && (
                    <div className="command-cwd">
                      <em>cwd: {cmd.cwd}</em>
                    </div>
                  )}

                  {cmd.output && (
                    <pre className="command-output">{cmd.output}</pre>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default SessionTimeline
