import { useState, useEffect } from 'react'
import SessionsList from './pages/SessionsList.jsx'
import SessionTimeline from './pages/SessionTimeline.jsx'
import Analytics from './pages/Analytics.jsx'
import './App.css'

function App() {
  const [currentView, setCurrentView] = useState('sessions') // 'sessions', 'timeline', 'analytics'
  const [selectedSessionId, setSelectedSessionId] = useState(null)

  const handleSelectSession = (sessionId) => {
    setSelectedSessionId(sessionId)
    setCurrentView('timeline')
  }

  const handleBackToSessions = () => {
    setCurrentView('sessions')
    setSelectedSessionId(null)
  }

  return (
    <div className="app">
      <header className="header">
        <h1>🍯 State-Grounded Honeypot Dashboard</h1>
        <div className="nav">
          <button
            className={`nav-btn ${currentView === 'sessions' ? 'active' : ''}`}
            onClick={() => setCurrentView('sessions')}
          >
            Sessions
          </button>
          <button
            className={`nav-btn ${currentView === 'analytics' ? 'active' : ''}`}
            onClick={() => setCurrentView('analytics')}
          >
            Analytics
          </button>
        </div>
      </header>

      <main className="main-content">
        {currentView === 'sessions' && (
          <SessionsList onSelectSession={handleSelectSession} />
        )}
        {currentView === 'timeline' && selectedSessionId && (
          <SessionTimeline
            sessionId={selectedSessionId}
            onBack={handleBackToSessions}
          />
        )}
        {currentView === 'analytics' && <Analytics />}
      </main>
    </div>
  )
}

export default App
