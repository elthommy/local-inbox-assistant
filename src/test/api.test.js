import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, streamChat } from '../api.js'

afterEach(() => vi.unstubAllGlobals())

function jsonResponse(data, ok = true, status = 200) {
  return Promise.resolve({ ok, status, json: () => Promise.resolve(data) })
}

/** Build a fetch Response whose body streams the given SSE frames. */
function sseResponse(frames) {
  const encoder = new TextEncoder()
  const body = new ReadableStream({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame))
      controller.close()
    },
  })
  return Promise.resolve({ ok: true, status: 200, body })
}

describe('api', () => {
  it('GET endpoints hit the right paths', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ unread: 3 }))
    vi.stubGlobal('fetch', fetchMock)
    expect(await api.stats()).toEqual({ unread: 3 })
    await api.emails('priority')
    await api.tasks()
    await api.events()
    await api.status()
    const urls = fetchMock.mock.calls.map((c) => c[0])
    expect(urls).toEqual(['/api/stats', '/api/emails?filter=priority', '/api/tasks', '/api/events', '/api/status'])
  })

  it('POST endpoints send POST', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ done: true }))
    vi.stubGlobal('fetch', fetchMock)
    await api.toggleTask(7)
    await api.dismissEmail(3)
    await api.muteSender('spam@news.com')
    await api.updateSettings({ window_days: 120 })
    await api.reindex()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/tasks/7/toggle')
    expect(fetchMock.mock.calls[0][1].method).toBe('POST')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/emails/3/dismiss')
    expect(fetchMock.mock.calls[2][0]).toBe('/api/senders/mute')
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ sender_email: 'spam@news.com' })
    expect(fetchMock.mock.calls[3][0]).toBe('/api/settings')
    expect(JSON.parse(fetchMock.mock.calls[3][1].body)).toEqual({ window_days: 120 })
    expect(fetchMock.mock.calls[4][0]).toBe('/api/reindex')
  })

  it('throws on non-ok responses', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({}, false, 500)))
    await expect(api.stats()).rejects.toThrow('HTTP 500')
  })
})

describe('streamChat', () => {
  it('delivers tokens in order and resolves on done', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        sseResponse([
          'data: {"token": "Hel"}\n\n',
          'data: {"token": "lo"}\n\n',
          'event: done\ndata: {}\n\n',
        ]),
      ),
    )
    const tokens = []
    await streamChat({ messages: [], model: 'ollama', useContext: true }, (t) => tokens.push(t))
    expect(tokens).toEqual(['Hel', 'lo'])
  })

  it('handles frames split across network chunks', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        sseResponse(['data: {"tok', 'en": "AB"}\n\ndata: {"token"', ': "CD"}\n\nevent: done\ndata: {}\n\n']),
      ),
    )
    const tokens = []
    await streamChat({ messages: [] }, (t) => tokens.push(t))
    expect(tokens).toEqual(['AB', 'CD'])
  })

  it('throws on error events with the server message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => sseResponse(['event: error\ndata: {"message": "Claude not configured"}\n\n'])),
    )
    await expect(streamChat({ messages: [] }, () => {})).rejects.toThrow('Claude not configured')
  })

  it('tokens after an error are not delivered', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        sseResponse(['event: error\ndata: {"message": "boom"}\n\ndata: {"token": "late"}\n\n']),
      ),
    )
    const tokens = []
    await expect(streamChat({ messages: [] }, (t) => tokens.push(t))).rejects.toThrow('boom')
    expect(tokens).toEqual([])
  })

  it('sends the request payload the backend expects', async () => {
    const fetchMock = vi.fn(() => sseResponse(['event: done\ndata: {}\n\n']))
    vi.stubGlobal('fetch', fetchMock)
    await streamChat(
      { messages: [{ role: 'user', content: 'hi' }], model: 'ollama', useContext: false },
      () => {},
    )
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body).toEqual({
      messages: [{ role: 'user', content: 'hi' }],
      model: 'ollama',
      use_context: false,
    })
  })

  it('throws on HTTP failure', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 502, body: null })))
    await expect(streamChat({ messages: [] }, () => {})).rejects.toThrow('HTTP 502')
  })
})
