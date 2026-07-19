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
    emailBody: vi.fn(),
    tasks: vi.fn(),
    events: vi.fn(),
    mutedSenders: vi.fn(),
    settings: vi.fn(),
    updateSettings: vi.fn(),
    toggleTask: vi.fn(),
    dismissEmail: vi.fn(),
    muteSender: vi.fn(),
    reindex: vi.fn(),
    reextract: vi.fn(),
  },
  streamChat: vi.fn(),
}))

const STATUS = {
  ollama: {
    up: true,
    url: 'http://localhost:11434',
    chat_model: 'qwen3:8b',
    extraction_model: 'qwen3:8b',
    embed_model: 'nomic-embed-text',
    chat_model_pulled: true,
    extraction_model_pulled: true,
    models: [
      { name: 'qwen3:8b', size: 5_200_000_000 },
      { name: 'qwen3:4b', size: 2_600_000_000 },
    ],
  },
  claude: { configured: false, model: 'claude-opus-4-8' },
  chat_provider: 'ollama',
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

// upcoming event fixture: always tomorrow, so the "events" tab never rots
// as the real date advances (local-time parts to avoid UTC day shifts)
const EVENT_DATE = (() => {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
})()
const pad2 = (n) => String(n).padStart(2, '0')
const EVENT_DATE_ISO = `${EVENT_DATE.getFullYear()}-${pad2(EVENT_DATE.getMonth() + 1)}-${pad2(EVENT_DATE.getDate())}`
const EVENT_DATE_DMY = `${pad2(EVENT_DATE.getDate())}/${pad2(EVENT_DATE.getMonth() + 1)}/${EVENT_DATE.getFullYear()}`

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
    events: [{ id: 21, title: 'Review meeting', date: EVENT_DATE_ISO, time: '10:00' }],
  },
]

const TASKS = [
  { id: 11, email_id: 1, text: 'Review Q3 report', due: 'Friday', done: false, source: 'Sarah Chen', date_utc: '2026-07-10' },
]

const EVENTS = [
  { id: 21, email_id: 1, title: 'Review meeting', date: EVENT_DATE_ISO, time: '10:00', source: 'Sarah Chen', date_utc: '2026-07-10' },
]

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  api.status.mockResolvedValue(STATUS)
  api.stats.mockResolvedValue({ unread: 1, high_priority: 1 })
  api.emails.mockResolvedValue(EMAILS)
  api.email.mockResolvedValue(EMAILS[0])
  // no reading view by default: rows fall back to the snippet
  api.emailBody.mockResolvedValue({ id: 1, format: 'text', body: '' })
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
    expect(screen.getByText('claude · no key')).toBeInTheDocument()
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
    const chipDate = EVENT_DATE.toLocaleDateString()
    expect(screen.getByText(`◷ Review meeting · ${chipDate} 10:00`)).toBeInTheDocument()
  })

  it('loads the full email body when a row is expanded', async () => {
    const FULL_BODY = 'please take one more pass before Friday.\n\nThe deck is attached; focus on the revenue slide.'
    api.emailBody.mockResolvedValue({ id: 1, format: 'text', body: FULL_BODY })
    render(<App />)
    await userEvent.click(await screen.findByText('Sarah Chen'))
    expect(api.emailBody).toHaveBeenCalledWith(1)
    expect(await screen.findByText(/focus on the revenue slide/)).toBeInTheDocument()
  })

  it('renders a markdown reading view with safe links and no images', async () => {
    api.emailBody.mockResolvedValue({
      id: 1,
      format: 'markdown',
      body: '# Q3 numbers\n\nthey look **good**, see [the report](https://corp.com/q3)\n\n![pixel](https://t.corp.com/p.gif)',
    })
    render(<App />)
    await userEvent.click(await screen.findByText('Sarah Chen'))
    expect((await screen.findByText('Q3 numbers')).tagName).toBe('H1')
    expect(screen.getByText('good').tagName).toBe('STRONG')
    const link = screen.getByRole('link', { name: 'the report' })
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('flags a degraded rendering and offers a render-anyway override', async () => {
    api.emailBody
      .mockResolvedValueOnce({ id: 1, format: 'text', body: 'plain fallback text', degraded: true })
      .mockResolvedValueOnce({ id: 1, format: 'markdown', body: 'now **forced** markdown', degraded: true })
      .mockResolvedValueOnce({ id: 1, format: 'text', body: 'plain fallback text', degraded: true })
    render(<App />)
    await userEvent.click(await screen.findByText('Sarah Chen'))
    // degraded: plain text shown, flagged, with the override offered
    expect(await screen.findByText(/layout too complex — showing plain text/)).toBeInTheDocument()
    expect(screen.getByText('plain fallback text')).toBeInTheDocument()
    await userEvent.click(screen.getByText('render anyway'))
    expect(api.emailBody).toHaveBeenLastCalledWith(1, true)
    expect((await screen.findByText('forced')).tagName).toBe('STRONG')
    // still flagged, and reversible
    expect(screen.getByText(/complex layout — rendered anyway/)).toBeInTheDocument()
    await userEvent.click(screen.getByText('show plain text'))
    expect(api.emailBody).toHaveBeenLastCalledWith(1, false)
    expect(await screen.findByText('plain fallback text')).toBeInTheDocument()
  })

  it('keeps showing the snippet when the body fetch fails', async () => {
    api.emailBody.mockRejectedValue(new Error('fetch failed'))
    render(<App />)
    await userEvent.click(await screen.findByText('Sarah Chen'))
    expect(await screen.findByText(/one more pass/)).toBeInTheDocument()
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
      { id: 22, email_id: 2, title: 'Stellaris leaving Game Pass', date: EVENT_DATE_ISO, time: '', source: 'Paradox', date_utc: '2026-07-01' },
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

  it('keeps the open-tasks tile in sync with the tasks tab when toggling', async () => {
    render(<App />)
    const tile = (await screen.findByText('open tasks')).parentElement
    expect(tile).toHaveTextContent('1')
    await userEvent.click(screen.getByText('tasks (1)'))
    const row = (await screen.findByText('Review Q3 report')).closest('div').parentElement
    const checkbox = within(row.parentElement).getAllByText('', { selector: 'div' })
      .find((d) => d.style.width === '18px')
    await userEvent.click(checkbox)
    expect(tile).toHaveTextContent('0')
    expect(screen.getByText('tasks (0)')).toBeInTheDocument()
  })

  it('shows events under a date header with sender and time', async () => {
    render(<App />)
    await userEvent.click(await screen.findByText('events (1)'))
    expect(await screen.findByText('Review meeting')).toBeInTheDocument()
    // EVENT_DATE is always tomorrow → the date group header says so
    expect(screen.getByText(`▸ tomorrow · ${EVENT_DATE.toLocaleDateString()}`)).toBeInTheDocument()
    expect(screen.getByText('10:00')).toBeInTheDocument()
    expect(screen.getByText('from Sarah Chen')).toBeInTheDocument()
  })

  it('groups events by day and sender, collapsing reminder duplicates', async () => {
    api.events.mockResolvedValue([
      { id: 31, email_id: 3, title: 'Livraison prévue', date: EVENT_DATE_ISO, time: '', source: 'Amazon.fr', date_utc: '2026-07-12T08:00:00' },
      { id: 32, email_id: 4, title: 'Livraison prévue', date: EVENT_DATE_ISO, time: '13:00', source: 'Amazon.fr', date_utc: '2026-07-13T08:00:00' },
      { id: 33, email_id: 5, title: 'livraison  prévue', date: EVENT_DATE_ISO, time: '', source: 'Amazon.fr', date_utc: '2026-07-11T08:00:00' },
      ...EVENTS,
    ])
    render(<App />)
    // 4 raw events → 2 deduped rows, in both the tab label and the tile
    await screen.findByText('events (2)')
    expect(screen.getByText('upcoming events').parentElement).toHaveTextContent('2')
    await userEvent.click(screen.getByText('events (2)'))
    expect(await screen.findByText('Livraison prévue')).toBeInTheDocument()
    // one shared date header, sender sub-headers, ×3 collapse badge
    expect(screen.getAllByText(/▸ tomorrow ·/)).toHaveLength(1)
    expect(screen.getByText('Amazon.fr')).toBeInTheDocument()
    expect(screen.getByText('×3')).toBeInTheDocument()
    expect(screen.getByText('from Amazon.fr · 3 emails')).toBeInTheDocument()
    // the newest reminder's details win (its time shows on the badge)
    expect(screen.getByText('13:00')).toBeInTheDocument()
    // dismissing the collapsed row dismisses every source email
    await userEvent.click(screen.getAllByTitle(/dismiss the source email/i)[0])
    expect(api.dismissEmail).toHaveBeenCalledTimes(3)
    for (const id of [3, 4, 5]) expect(api.dismissEmail).toHaveBeenCalledWith(id)
  })

  it('applies and persists the date format chosen in settings', async () => {
    render(<App />)
    await userEvent.click(await screen.findByText('events (1)'))
    await screen.findByText('Review meeting')
    await userEvent.click(screen.getByText('⚙ MCP / RAG'))
    await userEvent.selectOptions(screen.getByLabelText('date format'), 'dmy')
    expect(localStorage.getItem('date_format')).toBe('dmy')
    // the events date group header re-renders in the chosen format
    expect(screen.getByText(`▸ tomorrow · ${EVENT_DATE_DMY}`)).toBeInTheDocument()
  })

  it('opens the settings drawer with real index data and MCP command', async () => {
    render(<App />)
    await screen.findByText('Sarah Chen')
    await userEvent.click(screen.getByText('⚙ MCP / RAG'))
    expect(screen.getByText('MCP / RAG settings')).toBeInTheDocument()
    expect(screen.getByText(/Ollama · localhost:11434/)).toBeInTheDocument()
    expect(screen.getByText('online')).toBeInTheDocument()
    expect(screen.getByText(/set INBOX_ANTHROPIC_API_KEY to enable cloud chat/)).toBeInTheDocument()
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

  it('disables the Claude model option without an API key', async () => {
    render(<App />)
    await screen.findByText('Sarah Chen')
    const option = screen.getByRole('option', { name: /Claude \(cloud\) — no API key/ })
    expect(option).toBeDisabled()
    expect(screen.getByRole('option', { name: /qwen3:8b · Ollama \(local\)/ })).toBeInTheDocument()
  })

  it('enables Claude when a key is configured and selects it', async () => {
    api.status.mockResolvedValue({ ...STATUS, claude: { configured: true, model: 'claude-opus-4-8' } })
    render(<App />)
    await screen.findByText('Sarah Chen')
    expect(screen.getByText('claude · cloud')).toBeInTheDocument()
    const option = screen.getByRole('option', { name: /claude-opus-4-8 · Claude \(cloud\)/ })
    expect(option).not.toBeDisabled()
    await userEvent.selectOptions(screen.getAllByLabelText('chat model')[0], 'claude')
    expect(api.updateSettings).toHaveBeenCalledWith({ chat_provider: 'claude' })
  })

  it('sends chat to Claude when it is the selected provider', async () => {
    api.status.mockResolvedValue({ ...STATUS, claude: { configured: true, model: 'claude-opus-4-8' }, chat_provider: 'claude' })
    streamChat.mockImplementation(async ({ model }, onToken) => {
      expect(model).toBe('claude')
      onToken('Bonjour.')
    })
    render(<App />)
    await screen.findByText('Sarah Chen')
    await userEvent.type(screen.getByPlaceholderText('Ask about your inbox…'), 'hello')
    await userEvent.keyboard('{Enter}')
    expect(await screen.findByText('Bonjour.')).toBeInTheDocument()
    // the answer is labeled with the Claude model, not the Ollama one
    expect(screen.getByText(/claude-opus-4-8 · \d/)).toBeInTheDocument()
  })

  it('switches the chat model from the chat pane dropdown', async () => {
    api.updateSettings.mockResolvedValue({
      window_days: 90,
      extraction_window_days: 14,
      extraction_max_emails: 300,
      chat_model: 'qwen3:4b',
      extraction_model: 'qwen3:8b',
    })
    render(<App />)
    await screen.findByText('Sarah Chen')
    // two "chat model" selects exist (chat pane + drawer); the pane comes first
    await userEvent.selectOptions(screen.getAllByLabelText('chat model')[0], 'qwen3:4b')
    expect(api.updateSettings).toHaveBeenCalledWith({ chat_provider: 'ollama', chat_model: 'qwen3:4b' })
  })

  it('switches the email parsing model and re-parses from the drawer', async () => {
    api.reextract.mockResolvedValue({ started: true, reset: 42 })
    render(<App />)
    await screen.findByText('Sarah Chen')
    await userEvent.click(screen.getByText('⚙ MCP / RAG'))
    const select = screen.getByLabelText('email parsing model')
    expect(within(select).getByRole('option', { name: 'qwen3:4b · 2.6 GB' })).toBeInTheDocument()
    await userEvent.selectOptions(select, 'qwen3:4b')
    expect(api.updateSettings).toHaveBeenCalledWith({ extraction_model: 'qwen3:4b' })
    await userEvent.click(screen.getByText('re-parse recent emails'))
    expect(api.reextract).toHaveBeenCalled()
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
    // assistant bubble label: "qwen3:8b · <time>" (select options also start
    // with "qwen3:8b ·", so require the hh:mm time pattern)
    expect(screen.getByText(/^qwen3:8b · \d+:\d{2}/)).toBeInTheDocument()
  })

  it('renders assistant markdown as HTML, user text as plain text', async () => {
    streamChat.mockImplementation(async (_opts, onToken) => {
      onToken('**Urgent**: reply to Sarah\n\n- `Q3.pdf`\n- meeting')
    })
    render(<App />)
    await screen.findByText('Sarah Chen')
    await userEvent.type(screen.getByPlaceholderText('Ask about your inbox…'), 'what is *urgent*?')
    await userEvent.click(screen.getByText('send'))
    const bold = await screen.findByText('Urgent')
    expect(bold.tagName).toBe('STRONG')
    expect(screen.getByText('Q3.pdf').tagName).toBe('CODE')
    expect(screen.getByRole('list')).toBeInTheDocument()
    // the user message is NOT parsed as markdown: the * stay literal
    expect(screen.getByText('what is *urgent*?')).toBeInTheDocument()
  })

  it('summarizes an email into the chat panel and pins it for follow-ups', async () => {
    const calls = []
    streamChat.mockImplementation(async ({ messages, emailId }, onToken) => {
      calls.push({ last: messages.at(-1), emailId })
      onToken('Résumé du mail.')
    })
    render(<App />)
    await userEvent.click(await screen.findByText('Sarah Chen'))
    // summarize is offered in the all-mail tab only
    expect(screen.queryByText('≡ summarize')).not.toBeInTheDocument()
    await userEvent.click(screen.getByText('all mail (2106)'))
    await userEvent.click(await screen.findByText('≡ summarize'))
    expect(calls[0].emailId).toBe(1)
    expect(calls[0].last).toEqual({
      role: 'user',
      content: 'Summarize this email from Sarah Chen: "Q3 report — review needed"',
    })
    expect(await screen.findByText('Résumé du mail.')).toBeInTheDocument()
    // the pinned email shows as a chip and sticks for follow-up questions
    expect(screen.getByText('✉ in context:')).toBeInTheDocument()
    await userEvent.type(screen.getByPlaceholderText('Ask about your inbox…'), 'who sent it?')
    await userEvent.click(screen.getByText('send'))
    expect(calls[1]).toMatchObject({ emailId: 1, last: { content: 'who sent it?' } })
    // the ✕ on the chip unpins the email
    await userEvent.click(screen.getByTitle('Drop this email from the chat context'))
    expect(screen.queryByText('✉ in context:')).not.toBeInTheDocument()
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
    const indicators = await screen.findAllByText('adding to RAG DB… 50/200 (25%)')
    expect(indicators.length).toBeGreaterThanOrEqual(1)
  })

  it('shows a live file count while the maildir walk runs', async () => {
    api.status.mockResolvedValue({
      ...STATUS,
      index: { ...STATUS.index, progress: { phase: 'scanning', done: 12000, total: 0, error: null } },
    })
    render(<App />)
    const indicators = await screen.findAllByText(/scanning mail folders… 12[\s,. ]000 files/)
    expect(indicators.length).toBeGreaterThanOrEqual(1)
  })
})
