const BASE = '/api'

async function getJSON(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
  return res.json()
}

async function postJSON(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
  return res.json()
}

export const api = {
  status: () => getJSON('/status'),
  stats: () => getJSON('/stats'),
  emails: (filter) => getJSON(`/emails?filter=${filter}`),
  tasks: () => getJSON('/tasks'),
  events: () => getJSON('/events'),
  toggleTask: (id) => postJSON(`/tasks/${id}/toggle`),
  dismissEmail: (id) => postJSON(`/emails/${id}/dismiss`),
  muteSender: (senderEmail) => postJSON('/senders/mute', { sender_email: senderEmail }),
  mutedSenders: () => getJSON('/senders/muted'),
  settings: () => getJSON('/settings'),
  updateSettings: (values) => postJSON('/settings', values),
  reindex: () => postJSON('/reindex'),
}

/**
 * Stream a chat response over SSE.
 * Calls onToken(text) per chunk; resolves when done; throws on error events.
 */
export async function streamChat({ messages, model, useContext }, onToken) {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, model, use_context: useContext }),
  })
  if (!res.ok || !res.body) throw new Error(`chat: HTTP ${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let eventName = 'message'

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buffer.indexOf('\n')) !== -1) {
      const line = buffer.slice(0, idx).trimEnd()
      buffer = buffer.slice(idx + 1)
      if (line.startsWith('event: ')) {
        eventName = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6))
        if (eventName === 'error') throw new Error(data.message)
        if (eventName === 'done') return
        if (data.token) onToken(data.token)
      } else if (line === '') {
        eventName = 'message'
      }
    }
  }
}
