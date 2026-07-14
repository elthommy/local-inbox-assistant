import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App.jsx'
import { api, streamChat } from '../api.js'

vi.mock('../api.js', () => ({
  api: {
    status: vi.fn(),
    stats: vi.fn(),
    emails: vi.fn(),
    email: vi.fn(),
    tasks: vi.fn(),
    events: vi.fn(),
    mutedSenders: vi.fn(),
    settings: vi.fn(),
    updateSettings: vi.fn(),
    toggleTask: vi.fn(),
    dismissEmail: vi.fn(),
    muteSender: vi.fn(),
    reindex: vi.fn(),
  },
  streamChat: vi.fn(),
}))

const STATUS = {
  ollama: {
    up: true,
    url: 'http://localhost:11434',
    chat_model: 'qwen3.6',
    embed_model: 'nomic-embed-text',
    chat_model_pulled: true,
  },
  claude: { configured: false, implemented: false },
  index: {
    emails: 2106,
    chunks: 8600,
    last_indexed: new Date().toISOString(),
    window_days: 90,
    maildir: '/home/user/.thunderbird/x/INBOX/cur',
    backend_dir: '/home/user/project/backend',
    progress: { phase: 'idle', done: 0, total: 0, error: null },
  },
}

const EMAILS = [
  {
    id: 1,
    sender: 'Sarah Chen',
    sender_email: 'sarah@corp.com',
    subject: 'Q3 report — review needed',
    date_utc: '2026-07-10T07:14:00+00:00',
    unread: true,
    priority: 'high',
    dismissed: false,
    muted: false,
    snippet: 'please take one more pass before Friday',
    tasks: [{ id: 11, text: 'Review Q3 report', due: 'Friday', done: false }],
    events: [{ id: 21, title: 'Review meeting', date: '2026-07-14', time: '10:00' }],
  },
]

const TASKS = [
  { id: 11, email_id: 1, text: 'Review Q3 report', due: 'Friday', done: false, source: 'Sarah Chen', date_utc: '2026-07-10' },
]

const EVENTS = [
  { id: 21, email_id: 1, title: 'Review meeting', date: '2026-07-14', time: '10:00', source: 'Sarah Chen', date_utc: '2026-07-10' },
]

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  api.status.mockResolvedValue(STATUS)
  api.stats.mockResolvedValue({ unread: 1, open_tasks: 1, events: 1, high_priority: 1 })
  api.emails.mockResolvedValue(EMAILS)
  api.email.mockResolvedValue(EMAILS[0])
  api.tasks.mockResolvedValue(TASKS)
  api.events.mockResolvedValue(EVENTS)
  api.mutedSenders.mockResolvedValue([])
  api.settings.mockResolvedValue({ window_days: 90, extraction_window_days: 14, extraction_max_emails: 300 })
  api.updateSettings.mockResolvedValue({ window_days: 90, extraction_window_days: 30, extraction_max_emails: 300 })
  api.toggleTask.mockResolvedValue({ id: 11, done: true })
  api.dismissEmail.mockResolvedValue({ id: 1, dismissed: true })
  api.muteSender.mockResolvedValue({ sender_email: 'sarah@corp.com', muted: true })
})

describe('App', () => {
  it('renders header with live ollama status and indexed count', async () => {
    render(<App />)
    expect(screen.getByText('▍local-inbox-assistant')).toBeInTheDocument()
    expect(await screen.findByText('ollama · local')).toBeInTheDocument()
    expect(screen.getByText('claude · soon')).toBeInTheDocument()
    expect(await screen.findByText('inbox context · 2,106')).toBeInTheDocument()
  })

  it('shows ollama as offline when status says down', async () => {
    api.status.mockResolvedValue({ ...STATUS, ollama: { ...STATUS.ollama, up: false } })
    render(<App />)
    expect(await screen.findByText('ollama · offline')).toBeInTheDocument()
  })

  it('renders stat tiles from the API', async () => {
    render(<App />)
    expect(await screen.findByText('unread')).toBeInTheDocument()
    expect(screen.getByText('open tasks')).toBeInTheDocument()
    expect(await screen.findByText('priority (1)')).toBeInTheDocument()
    expect(screen.getByText('all mail (2106)')).toBeInTheDocument()
  })

  it('lists emails and expands one on click', async () => {
    render(<App />)
    const sender = await screen.findByText('Sarah Chen')
    expect(screen.getByText('Q3 report — review needed')).toBeInTheDocument()
    expect(screen.queryByText(/one more pass/)).not.toBeInTheDocument()
    await userEvent.click(sender)
    expect(screen.getByText(/one more pass/)).toBeInTheDocument()
    expect(screen.getByText('corp.com')).toBeInTheDocument()
    expect(screen.getByText(/☐ Review Q3 report · Friday/)).toBeInTheDocument()
    // event chip date rendered in the system locale by default
    const chipDate = new Date(2026, 6, 14).toLocaleDateString()
    expect(screen.getByText(`◷ Review meeting · ${chipDate} 10:00`)).toBeInTheDocument()
  })

  it('switches filters and requests the matching email set', async () => {
    render(<App />)
    await screen.findByText('Sarah Chen')
    expect(api.emails).toHaveBeenLastCalledWith('priority')
    await userEvent.click(screen.getByText('all mail (2106)'))
    expect(api.emails).toHaveBeenLastCalledWith('all')
  })

  it('dismisses an email through the API and refreshes the lists', async () => {
    render(<App />)
    await userEvent.click(await screen.findByText('Sarah Chen'))
    api.emails.mockClear()
    await userEvent.click(screen.getByText('✕ not important'))
    expect(api.dismissEmail).toHaveBeenCalledWith(1)
    expect(api.emails).toHaveBeenCalled() // refetched after the change
  })

  it('mutes a sender through the API', async () => {
    render(<App />)
    await userEvent.click(await screen.findByText('Sarah Chen'))
    await userEvent.click(screen.getByText('⊘ mute sender'))
    expect(api.muteSender).toHaveBeenCalledWith('sarah@corp.com')
  })

  it('marks dismissed emails and offers restore', async () => {
    api.emails.mockResolvedValue([{ ...EMAILS[0], dismissed: true }])
    render(<App />)
    await userEvent.click(await screen.findByText('Sarah Chen'))
    expect(screen.getByText(/✕ dismissed ·/)).toBeInTheDocument()
    expect(screen.getByText('↩ restore')).toBeInTheDocument()
  })

  it('lists muted senders in the settings drawer and unmutes from there', async () => {
    api.mutedSenders.mockResolvedValue([{ sender_email: 'spam@news.com', created_utc: '2026-07-13' }])
    render(<App />)
    await screen.findByText('Sarah Chen')
    await userEvent.click(screen.getByText('⚙ MCP / RAG'))
    expect(screen.getByText('⊘ spam@news.com')).toBeInTheDocument()
    await userEvent.click(screen.getByText('unmute'))
    expect(api.muteSender).toHaveBeenCalledWith('spam@news.com')
  })

  it('dismisses the source email from the task view', async () => {
    render(<App />)
    await userEvent.click(await screen.findByText('tasks (1)'))
    await screen.findByText('Review Q3 report')
    await userEvent.click(screen.getByTitle(/dismiss the source email/i))
    expect(api.dismissEmail).toHaveBeenCalledWith(1)
  })

  it('dismisses the source email from the events view', async () => {
    render(<App />)
    await userEvent.click(await screen.findByText('events (1)'))
    await screen.findByText('Review meeting')
    await userEvent.click(screen.getByTitle(/dismiss the source email/i))
    expect(api.dismissEmail).toHaveBeenCalledWith(1)
  })

  it('jumps to the source email in all mail from the task view', async () => {
    render(<App />)
    await userEvent.click(await screen.findByText('tasks (1)'))
    await screen.findByText('Review Q3 report')
    api.emails.mockClear()
    await userEvent.click(screen.getByTitle('Show source email in all mail'))
    expect(api.emails).toHaveBeenLastCalledWith('all')
    // the email row is rendered expanded (snippet visible)
    expect(await screen.findByText(/one more pass/)).toBeInTheDocument()
  })

  it('pulls an email older than the all-mail window into the list when jumping to it', async () => {
    const OLD_EMAIL = {
      id: 2,
      sender: 'Paradox',
      sender_email: 'news@paradox.com',
      subject: 'Stellaris news',
      date_utc: '2026-07-01T10:00:00+00:00',
      unread: false,
      priority: 'low',
      dismissed: false,
      muted: false,
      snippet: 'leaving Game Pass on July 15',
      tasks: [],
      events: [],
    }
    api.events.mockResolvedValue([
      { id: 22, email_id: 2, title: 'Stellaris leaving Game Pass', date: '2026-07-15', time: '', source: 'Paradox', date_utc: '2026-07-01' },
    ])
    api.email.mockResolvedValue(OLD_EMAIL)
    render(<App />)
    await userEvent.click(await screen.findByText('events (1)'))
    await screen.findByText('Stellaris leaving Game Pass')
    await userEvent.click(screen.getByTitle('Show source email in all mail'))
    expect(api.email).toHaveBeenCalledWith(2)
    // rendered expanded, spliced in below the newer email from the window
    expect(await screen.findByText('Stellaris news')).toBeInTheDocument()
    expect(screen.getByText(/leaving Game Pass on July 15/)).toBeInTheDocument()
    const subjects = screen.getAllByText(/Q3 report — review needed|Stellaris news/).map((n) => n.textContent)
    expect(subjects).toEqual(['Q3 report — review needed', 'Stellaris news'])
  })

  it('offers "show in all mail" on priority emails', async () => {
    render(<App />)
    await userEvent.click(await screen.findByText('Sarah Chen'))
    api.emails.mockClear()
    await userEvent.click(screen.getByText('✉ show in all mail'))
    expect(api.emails).toHaveBeenLastCalledWith('all')
  })

  it('shows tasks and toggles one through the API', async () => {
    render(<App />)
    await userEvent.click(await screen.findByText('tasks (1)'))
    expect(await screen.findByText('Review Q3 report')).toBeInTheDocument()
    expect(screen.getByText(/from Sarah Chen · due Friday/)).toBeInTheDocument()
    // the checkbox is the only 18px square div
    const row = screen.getByText('Review Q3 report').closest('div').parentElement
    const checkbox = within(row.parentElement).getAllByText('', { selector: 'div' })
      .find((d) => d.style.width === '18px')
    await userEvent.click(checkbox)
    expect(api.toggleTask).toHaveBeenCalledWith(11)
  })

  it('shows events with formatted date chip', async () => {
    render(<App />)
    await userEvent.click(await screen.findByText('events (1)'))
    expect(await screen.findByText('Review meeting')).toBeInTheDocument()
    const badge = new Date(2026, 6, 14)
      .toLocaleDateString([], { month: 'short', day: 'numeric' })
      .toUpperCase()
    expect(screen.getByText(badge)).toBeInTheDocument()
    expect(screen.getByText(/10:00 · from Sarah Chen/)).toBeInTheDocument()
  })

  it('applies and persists the date format chosen in settings', async () => {
    render(<App />)
    await userEvent.click(await screen.findByText('events (1)'))
    await screen.findByText('Review meeting')
    await userEvent.click(screen.getByText('⚙ MCP / RAG'))
    await userEvent.selectOptions(screen.getByLabelText('date format'), 'dmy')
    expect(localStorage.getItem('date_format')).toBe('dmy')
    expect(screen.getByText('14/07/2026')).toBeInTheDocument()
  })

  it('opens the settings drawer with real index data and MCP command', async () => {
    render(<App />)
    await screen.findByText('Sarah Chen')
    await userEvent.click(screen.getByText('⚙ MCP / RAG'))
    expect(screen.getByText('MCP / RAG settings')).toBeInTheDocument()
    expect(screen.getByText(/Ollama · localhost:11434/)).toBeInTheDocument()
    expect(screen.getByText('online')).toBeInTheDocument()
    expect(screen.getByText(/cloud support — planned \(step 2\)/)).toBeInTheDocument()
    expect(screen.getByText(/8,600 chunks · last indexed just now/)).toBeInTheDocument()
    expect(
      screen.getByText('claude mcp add localmail -- uv --directory /home/user/project/backend run python mcp_server.py'),
    ).toBeInTheDocument()
  })

  it('edits indexing settings from the drawer', async () => {
    render(<App />)
    await screen.findByText('Sarah Chen')
    await userEvent.click(screen.getByText('⚙ MCP / RAG'))
    const input = screen.getByLabelText('extraction window (days)')
    expect(input).toHaveValue(14)
    // save is disabled until something changes
    expect(screen.getByText('save')).toBeDisabled()
    await userEvent.clear(input)
    await userEvent.type(input, '30')
    await userEvent.click(screen.getByText('save'))
    expect(api.updateSettings).toHaveBeenCalledWith({
      window_days: 90,
      extraction_window_days: 30,
      extraction_max_emails: 300,
    })
    expect(input).toHaveValue(30) // reflects the saved response
  })

  it('disables save on invalid settings input', async () => {
    render(<App />)
    await screen.findByText('Sarah Chen')
    await userEvent.click(screen.getByText('⚙ MCP / RAG'))
    const input = screen.getByLabelText('index window (days)')
    await userEvent.clear(input)
    expect(screen.getByText('save')).toBeDisabled()
    expect(api.updateSettings).not.toHaveBeenCalled()
  })

  it('disables the Claude model option', async () => {
    render(<App />)
    await screen.findByText('Sarah Chen')
    const option = screen.getByRole('option', { name: /Claude \(cloud\) — coming soon/ })
    expect(option).toBeDisabled()
    expect(screen.getByRole('option', { name: /qwen3\.6 · Ollama \(local\)/ })).toBeInTheDocument()
  })

  it('sends a chat message and renders the streamed answer', async () => {
    streamChat.mockImplementation(async ({ messages, model, useContext }, onToken) => {
      expect(messages.at(-1)).toEqual({ role: 'user', content: 'what is urgent?' })
      expect(model).toBe('ollama')
      expect(useContext).toBe(true)
      onToken('Rien ')
      onToken("d'urgent.")
    })
    render(<App />)
    await screen.findByText('Sarah Chen')
    await userEvent.type(screen.getByPlaceholderText('Ask about your inbox…'), 'what is urgent?')
    await userEvent.click(screen.getByText('send'))
    expect(await screen.findByText('what is urgent?')).toBeInTheDocument()
    expect(await screen.findByText("Rien d'urgent.")).toBeInTheDocument()
    // assistant bubble label: "qwen3.6 · <time>" (the select option also
    // contains "qwen3.6 ·", so scope to the label pattern with a time)
    expect(screen.getByText(/^qwen3\.6 · \d/)).toBeInTheDocument()
  })

  it('renders a chat error bubble when the stream fails', async () => {
    streamChat.mockRejectedValue(new Error('backend exploded'))
    render(<App />)
    await screen.findByText('Sarah Chen')
    await userEvent.type(screen.getByPlaceholderText('Ask about your inbox…'), 'hello')
    await userEvent.keyboard('{Enter}')
    expect(await screen.findByText('backend exploded')).toBeInTheDocument()
  })

  it('shows an error banner when the backend is unreachable', async () => {
    api.stats.mockRejectedValue(new Error('fetch failed'))
    api.emails.mockRejectedValue(new Error('fetch failed'))
    render(<App />)
    expect(await screen.findByText(/backend unreachable/)).toBeInTheDocument()
  })

  it('shows indexing progress when a run is active', async () => {
    api.status.mockResolvedValue({
      ...STATUS,
      index: { ...STATUS.index, progress: { phase: 'embedding', done: 50, total: 200, error: null } },
    })
    render(<App />)
    // shown both in the filter bar and the settings drawer
    const indicators = await screen.findAllByText('embedding… 50/200 (25%)')
    expect(indicators.length).toBeGreaterThanOrEqual(1)
  })
})
