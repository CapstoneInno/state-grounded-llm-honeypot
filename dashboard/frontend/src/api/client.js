/**
 * API client for backend endpoints
 */

const API_BASE = (() => {
  // В Docker: frontend на 5173, backend на 8000 (оба на localhost:host)
  // Используем текущий хост:8000
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol
    const hostname = window.location.hostname
    return `${protocol}//${hostname}:8000`
  }
  return 'http://localhost:8000'
})()

console.log('[API] Using base URL:', API_BASE)

export const api = {
  async getSessions(limit = 50, offset = 0) {
    try {
      const response = await fetch(
        `${API_BASE}/api/sessions?limit=${limit}&offset=${offset}`
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response.json()
    } catch (err) {
      console.error('[API] getSessions failed:', err)
      throw err
    }
  },

  async getSessionDetail(sessionId) {
    try {
      const response = await fetch(`${API_BASE}/api/sessions/${sessionId}`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response.json()
    } catch (err) {
      console.error('[API] getSessionDetail failed:', err)
      throw err
    }
  },

  async getStats() {
    try {
      const response = await fetch(`${API_BASE}/api/stats`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response.json()
    } catch (err) {
      console.error('[API] getStats failed:', err)
      throw err
    }
  },

  subscribeToStream(onMessage, onError) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const hostname = window.location.hostname
    const wsUrl = `${protocol}//${hostname}:8000/api/stream`
    
    console.log('[WebSocket] Connecting to:', wsUrl)
    
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      console.log('[WebSocket] Connected to live stream')
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        onMessage(data)
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err)
      }
    }

    ws.onerror = (error) => {
      console.error('[WebSocket] Error:', error)
      if (onError) onError(error)
    }

    ws.onclose = () => {
      console.log('[WebSocket] Disconnected')
    }

    return ws
  },
}
