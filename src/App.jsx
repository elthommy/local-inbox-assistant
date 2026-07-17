import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, streamChat } from './api.js'
import { DATE_FORMATS, avatarColor, eventChipDate, eventGroupLabel, formatEmailTime, groupUpcomingEvents, nowTime, priorityColor, relativeTime } from './utils.js'

const MONO = "'IBM Plex Mono', monospace"
const SANS = "'IBM Plex Sans', system-ui, sans-serif"
const TRACK_ON = '#1f6feb'
const TRACK_OFF = '#2a2f38'

function Switch({ on, onClick, width = 32, height = 18, knob = 14 }) {
  return (
    <div
      onClick={onClick}
      style={{
        cursor: 'pointer',
        width,
        height,
        borderRadius: height / 2,
        background: on ? TRACK_ON : TRACK_OFF,
        position: 'relative',
        flex: 'none',
        transition: 'background .15s',
      }}
    >
      <span
        style={{
          position: 'absolute',
          top: 2,
          left: on ? width - knob - 2 : 2,
          width: knob,
          height: knob,
          borderRadius: '50%',
          background: '#fff',
          transition: 'left .15s',
        }}
      />
    </div>
  )
}

function StatusDot({ color, label, glow = true }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontFamily: MONO, fontSize: 12, color: '#9aa1ac' }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: color, boxShadow: glow ? `0 0 6px ${color}` : 'none' }} />
      {label}
    </div>
  )
}

function Header({ ollamaUp, onOpenSettings }) {
  return (
    <div
      style={{
        height: 56,
        flex: 'none',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 20px',
        background: '#12151a',
        borderBottom: '1px solid #232830',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span style={{ fontFamily: MONO, fontWeight: 700, fontSize: 15, color: '#e8eaed' }}>▍local-inbox-assistant</span>
        <span style={{ fontSize: 12, color: '#6b7280', fontFamily: MONO }}>AI-assisted inbox</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
        <StatusDot color={ollamaUp ? '#4ADE80' : '#F87171'} label={ollamaUp ? 'ollama · local' : 'ollama · offline'} />
        <StatusDot color="#3a4048" glow={false} label="claude · soon" />
        <button
          className="settings-btn"
          onClick={onOpenSettings}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            background: '#1a1f27',
            border: '1px solid #262b33',
            color: '#c4c9d1',
            fontFamily: MONO,
            fontSize: 12,
            padding: '7px 12px',
            borderRadius: 6,
            cursor: 'pointer',
          }}
        >
          ⚙ MCP / RAG
        </button>
      </div>
    </div>
  )
}

function ChatPane({ chatModel, model, onModelChange, useContext, toggleContext, indexedCount, messages, isTyping, input, onInputChange, onSend, focusEmail, onClearFocus }) {
  const scrollRef = useRef(null)
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, isTyping])

  return (
    <div style={{ flex: '0 0 45%', display: 'flex', flexDirection: 'column', borderRight: '1px solid #232830', minWidth: 0 }}>
      <div
        style={{
          flex: 'none',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderBottom: '1px solid #1c2027',
          background: '#0e1116',
          gap: 12,
        }}
      >
        <select
          value={model}
          onChange={onModelChange}
          style={{
            background: '#161a20',
            border: '1px solid #262b33',
            color: '#e8eaed',
            fontFamily: MONO,
            fontSize: 12,
            padding: '7px 10px',
            borderRadius: 6,
            cursor: 'pointer',
            flex: 'none',
            maxWidth: '55%',
          }}
        >
          <option value="ollama">{chatModel} · Ollama (local)</option>
          <option value="claude" disabled>
            Claude (cloud) — coming soon
          </option>
        </select>
        <div
          onClick={toggleContext}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            cursor: 'pointer',
            padding: '6px 10px',
            borderRadius: 6,
            background: useContext ? '#12241c' : '#161a20',
            border: `1px solid ${useContext ? '#1f4a34' : '#232830'}`,
            minWidth: 0,
          }}
        >
          <Switch on={useContext} width={28} height={16} knob={12} />
          <span
            style={{
              fontFamily: MONO,
              fontSize: 11,
              color: useContext ? '#4ADE80' : '#6b7280',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            inbox context · {indexedCount.toLocaleString()}
          </span>
        </div>
      </div>

      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: 20, display: 'flex', flexDirection: 'column', gap: 16, minHeight: 0 }}>
        {messages.length === 0 && (
          <div style={{ fontFamily: MONO, fontSize: 12, color: '#3a4048', margin: 'auto', textAlign: 'center', lineHeight: 2 }}>
            ▍no messages yet
            <br />
            ask anything about your inbox
          </div>
        )}
        {messages.map((m) => {
          const isUser = m.role === 'user'
          return (
            <div key={m.id} style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', gap: 4 }}>
              <span
                style={{
                  fontFamily: MONO,
                  fontSize: 10.5,
                  color: isUser ? '#6b7280' : m.error ? '#F87171' : '#4ADE80',
                  padding: '0 2px',
                }}
              >
                {isUser ? 'you' : m.model} · {m.time}
              </span>
              <div
                className={isUser ? undefined : 'chat-md'}
                style={{
                  maxWidth: '88%',
                  background: isUser ? '#16324a' : '#161a20',
                  border: `1px solid ${isUser ? '#1f4a68' : m.error ? '#4a1f1f' : '#232830'}`,
                  color: '#e2e5ea',
                  padding: '11px 14px',
                  borderRadius: 10,
                  fontSize: 13.5,
                  lineHeight: 1.55,
                  whiteSpace: isUser ? 'pre-wrap' : 'normal',
                }}
              >
                {isUser ? m.text : <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>}
              </div>
            </div>
          )
        })}
        {isTyping && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}>
            <span style={{ fontFamily: MONO, fontSize: 10.5, color: '#6b7280', padding: '0 2px' }}>{chatModel}</span>
            <div
              style={{
                background: '#161a20',
                border: '1px solid #232830',
                padding: '11px 14px',
                borderRadius: 10,
                fontFamily: MONO,
                fontSize: 13,
                color: '#6b7280',
              }}
            >
              ···
            </div>
          </div>
        )}
      </div>

      {focusEmail && (
        <div
          style={{
            flex: 'none',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '7px 16px',
            borderTop: '1px solid #1c2027',
            background: '#0e1116',
            fontFamily: MONO,
            fontSize: 11,
            color: '#7dd3fc',
            minWidth: 0,
          }}
        >
          <span style={{ flex: 'none', color: '#6b7280' }}>✉ in context:</span>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{focusEmail.subject}</span>
          <button
            onClick={onClearFocus}
            title="Drop this email from the chat context"
            style={{ background: 'none', border: 'none', color: '#6b7280', fontFamily: MONO, fontSize: 12, cursor: 'pointer', flex: 'none', padding: '0 2px' }}
          >
            ✕
          </button>
        </div>
      )}
      <div style={{ flex: 'none', display: 'flex', gap: 8, padding: '14px 16px', borderTop: '1px solid #1c2027', background: '#0e1116' }}>
        <input
          type="text"
          value={input}
          onChange={onInputChange}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onSend()
          }}
          placeholder="Ask about your inbox…"
          style={{
            flex: 1,
            background: '#161a20',
            border: '1px solid #262b33',
            color: '#e8eaed',
            fontFamily: SANS,
            fontSize: 13.5,
            padding: '11px 14px',
            borderRadius: 8,
            outline: 'none',
          }}
        />
        <button
          className="send-btn"
          onClick={onSend}
          style={{
            background: '#1f6feb',
            border: '1px solid #1f6feb',
            color: '#fff',
            fontFamily: MONO,
            fontSize: 12,
            fontWeight: 600,
            padding: '0 18px',
            borderRadius: 8,
            cursor: 'pointer',
          }}
        >
          send
        </button>
      </div>
    </div>
  )
}

function EmailRow({ email, expanded, onToggle, onDismiss, onMute, onGoTo, onSummarize, dateFormat }) {
  const initial = (email.sender || '?').replace(/^["']/, '').charAt(0).toUpperCase()
  const domain = email.sender_email ? email.sender_email.split('@').pop() : ''
  const suppressed = email.dismissed || email.muted
  const actionBtn = {
    background: '#1a1f27',
    border: '1px solid #262b33',
    color: '#9aa1ac',
    fontFamily: MONO,
    fontSize: 10.5,
    padding: '5px 10px',
    borderRadius: 5,
    cursor: 'pointer',
  }
  return (
    <div
      id={`email-${email.id}`}
      onClick={onToggle}
      style={{ background: '#12151a', border: '1px solid #232830', borderRadius: 8, padding: '12px 14px', cursor: 'pointer', opacity: suppressed ? 0.55 : 1 }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: priorityColor(email.priority), flex: 'none' }} />
        <span
          style={{
            width: 26,
            height: 26,
            borderRadius: '50%',
            background: avatarColor(email.sender || '?'),
            color: '#0b0d10',
            fontFamily: MONO,
            fontSize: 11,
            fontWeight: 700,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flex: 'none',
          }}
        >
          {initial}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
            <span
              style={{
                fontSize: 13,
                fontWeight: email.unread ? 600 : 400,
                color: '#e2e5ea',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {email.sender}
            </span>
            <span style={{ fontFamily: MONO, fontSize: 10.5, color: '#6b7280', flex: 'none' }}>
              {email.muted ? '⊘ muted · ' : email.dismissed ? '✕ dismissed · ' : ''}
              {formatEmailTime(email.date_utc, dateFormat)}
            </span>
          </div>
          <div
            style={{
              fontSize: 12.5,
              color: email.unread ? '#e2e5ea' : '#8a909a',
              fontWeight: email.unread ? 600 : 400,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              marginTop: 1,
            }}
          >
            {email.subject}
          </div>
        </div>
      </div>
      {expanded && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid #1c2027' }}>
          <div style={{ fontSize: 12.5, color: '#9aa1ac', lineHeight: 1.6 }}>{email.snippet}</div>
          <div style={{ display: 'flex', gap: 6, marginTop: 9, flexWrap: 'wrap' }}>
            {domain && (
              <span style={{ fontFamily: MONO, fontSize: 10, background: '#1a1f27', color: '#9aa1ac', padding: '3px 8px', borderRadius: 4 }}>
                {domain}
              </span>
            )}
            {(email.tasks || []).map((t) => (
              <span key={`t${t.id}`} style={{ fontFamily: MONO, fontSize: 10, background: '#2a2013', color: '#FBBF24', padding: '3px 8px', borderRadius: 4 }}>
                {t.done ? '☑' : '☐'} {t.text}
                {t.due ? ` · ${t.due}` : ''}
              </span>
            ))}
            {(email.events || []).map((ev) => (
              <span key={`e${ev.id}`} style={{ fontFamily: MONO, fontSize: 10, background: '#132a24', color: '#4ADE80', padding: '3px 8px', borderRadius: 4 }}>
                ◷ {ev.title}
                {ev.date ? ` · ${eventChipDate(ev.date, email.date_utc, dateFormat)}` : ''}
                {ev.time ? ` ${ev.time}` : ''}
              </span>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            {onGoTo && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onGoTo()
                }}
                style={actionBtn}
                title="Show this email in the all mail tab"
              >
                ✉ show in all mail
              </button>
            )}
            {onSummarize && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onSummarize()
                }}
                style={actionBtn}
                title="Summarize this email in the chat panel (keeps it in context for follow-up questions)"
              >
                ≡ summarize
              </button>
            )}
            <button
              onClick={(e) => {
                e.stopPropagation()
                onDismiss()
              }}
              style={actionBtn}
              title="Exclude this email from priority, tasks and events"
            >
              {email.dismissed ? '↩ restore' : '✕ not important'}
            </button>
            {email.sender_email && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onMute()
                }}
                style={actionBtn}
                title="Exclude every email from this sender from priority, tasks and events"
              >
                {email.muted ? '↩ unmute sender' : '⊘ mute sender'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function RowIconButton({ icon, title, onClick, hoverColor, hoverBorder }) {
  return (
    <button
      onClick={onClick}
      title={title}
      style={{
        background: 'none',
        border: '1px solid transparent',
        color: '#5b6270',
        fontFamily: MONO,
        fontSize: 12,
        padding: '4px 8px',
        borderRadius: 5,
        cursor: 'pointer',
        flex: 'none',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.color = hoverColor
        e.currentTarget.style.borderColor = hoverBorder
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.color = '#5b6270'
        e.currentTarget.style.borderColor = 'transparent'
      }}
    >
      {icon}
    </button>
  )
}

function GoToEmailButton({ onGoTo }) {
  return (
    <RowIconButton
      icon="✉"
      title="Show source email in all mail"
      onClick={onGoTo}
      hoverColor="#7dd3fc"
      hoverBorder="#2a5a8c"
    />
  )
}

function DismissSourceButton({ onDismiss }) {
  return (
    <RowIconButton
      icon="✕"
      title="Not important — dismiss the source email (removes all its tasks and events)"
      onClick={onDismiss}
      hoverColor="#F87171"
      hoverBorder="#4a1f1f"
    />
  )
}

function TaskRow({ task, onToggle, onDismiss, onGoTo }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, background: '#12151a', border: '1px solid #232830', borderRadius: 8, padding: '12px 14px' }}>
      <div
        onClick={onToggle}
        style={{
          width: 18,
          height: 18,
          borderRadius: 4,
          border: `1.5px solid ${task.done ? '#4ADE80' : '#3a4048'}`,
          background: task.done ? '#4ADE80' : 'transparent',
          flex: 'none',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#0b0d10',
          fontSize: 12,
        }}
      >
        {task.done ? '✓' : ''}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, color: task.done ? '#5b6270' : '#e2e5ea', textDecoration: task.done ? 'line-through' : 'none' }}>{task.text}</div>
        <div style={{ fontFamily: MONO, fontSize: 10.5, color: '#6b7280', marginTop: 2 }}>
          from {task.source}
          {task.due ? ` · due ${task.due}` : ''}
        </div>
      </div>
      <GoToEmailButton onGoTo={onGoTo} />
      <DismissSourceButton onDismiss={onDismiss} />
    </div>
  )
}

// One (possibly collapsed) event in the events tab: the date lives in the
// group header above, so the badge shows the time; count > 1 means reminder
// duplicates from several emails were folded into this row.
function EventRow({ event, onDismiss, onGoTo }) {
  const count = event.count || 1
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, background: '#12151a', border: '1px solid #232830', borderRadius: 8, padding: '12px 14px' }}>
      <div
        style={{
          fontFamily: MONO,
          fontSize: 11,
          color: '#4ADE80',
          background: '#132a24',
          borderRadius: 6,
          padding: '8px 10px',
          textAlign: 'center',
          flex: 'none',
          minWidth: 54,
        }}
      >
        {event.time || '—'}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <span style={{ fontSize: 13, color: '#e2e5ea', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{event.title}</span>
          {count > 1 && (
            <span
              title={`Mentioned in ${count} emails (reminders collapsed)`}
              style={{ fontFamily: MONO, fontSize: 10, color: '#FBBF24', background: '#2a2013', padding: '2px 7px', borderRadius: 9, flex: 'none' }}
            >
              ×{count}
            </span>
          )}
        </div>
        <div style={{ fontFamily: MONO, fontSize: 10.5, color: '#6b7280', marginTop: 2 }}>
          from {event.source}
          {count > 1 ? ` · ${count} emails` : ''}
        </div>
      </div>
      <GoToEmailButton onGoTo={onGoTo} />
      <DismissSourceButton onDismiss={onDismiss} />
    </div>
  )
}

// phase -> human label; scanning is indeterminate (total unknown during the walk)
const PHASE_LABELS = {
  scanning: (p) => `scanning mail folders… ${p.done.toLocaleString()} files`,
  checking: (p) => `discovering new emails… ${p.done}/${p.total}`,
  parsing: (p) => `reading new emails… ${p.done}/${p.total}`,
  embedding: (p) => `adding to RAG DB… ${p.done}/${p.total}`,
  extracting: (p) => `model analysis… ${p.done}/${p.total}`,
}

function IndexProgress({ progress }) {
  if (!progress || progress.phase === 'idle') return null
  if (progress.phase === 'error') {
    return <div style={{ fontFamily: MONO, fontSize: 11, color: '#F87171' }}>indexing error: {progress.error}</div>
  }
  const label = (PHASE_LABELS[progress.phase] || ((p) => `${p.phase}… ${p.done}/${p.total}`))(progress)
  const pct = progress.total ? Math.round((progress.done / progress.total) * 100) : null
  return (
    <div style={{ fontFamily: MONO, fontSize: 11, color: '#FBBF24', minWidth: 170 }}>
      <span>{pct === null ? label : `${label} (${pct}%)`}</span>
      <div style={{ height: 3, background: '#262b33', borderRadius: 2, marginTop: 3, overflow: 'hidden' }}>
        {pct === null ? (
          <div className="index-progress-indeterminate" style={{ width: '40%', height: '100%', background: '#FBBF24', borderRadius: 2 }} />
        ) : (
          <div style={{ width: `${pct}%`, height: '100%', background: '#FBBF24', borderRadius: 2, transition: 'width .3s' }} />
        )}
      </div>
    </div>
  )
}

const TUNABLE_FIELDS = [
  { key: 'window_days', label: 'index window (days)', hint: 'mail newer than this is parsed + embedded' },
  { key: 'extraction_window_days', label: 'extraction window (days)', hint: 'mail newer than this gets priority/tasks/events' },
  { key: 'extraction_max_emails', label: 'extraction max emails / run', hint: 'LLM-call budget per indexing run' },
]

function IndexingSettings({ tunables, onSave }) {
  const [draft, setDraft] = useState(null)
  useEffect(() => {
    setDraft(tunables ? Object.fromEntries(TUNABLE_FIELDS.map((f) => [f.key, String(tunables[f.key])])) : null)
  }, [tunables])

  if (!draft) return <div style={{ fontFamily: MONO, fontSize: 11, color: '#6b7280' }}>…</div>
  const parsed = Object.fromEntries(TUNABLE_FIELDS.map((f) => [f.key, parseInt(draft[f.key], 10)]))
  const valid = TUNABLE_FIELDS.every((f) => Number.isInteger(parsed[f.key]) && parsed[f.key] >= 1)
  const dirty = tunables && TUNABLE_FIELDS.some((f) => parsed[f.key] !== tunables[f.key])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {TUNABLE_FIELDS.map((f) => (
        <div key={f.key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 12.5, color: '#e2e5ea' }}>{f.label}</div>
            <div style={{ fontFamily: MONO, fontSize: 10, color: '#6b7280', marginTop: 1 }}>{f.hint}</div>
          </div>
          <input
            type="number"
            min="1"
            value={draft[f.key]}
            aria-label={f.label}
            onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
            style={{
              width: 70,
              background: '#0e1116',
              border: '1px solid #262b33',
              color: '#e8eaed',
              fontFamily: MONO,
              fontSize: 12,
              padding: '6px 8px',
              borderRadius: 6,
              outline: 'none',
              flex: 'none',
            }}
          />
        </div>
      ))}
      <button
        onClick={() => onSave(parsed)}
        disabled={!valid || !dirty}
        style={{
          alignSelf: 'flex-start',
          background: valid && dirty ? '#1f6feb' : '#1a1f27',
          border: `1px solid ${valid && dirty ? '#1f6feb' : '#262b33'}`,
          color: valid && dirty ? '#fff' : '#5b6270',
          fontFamily: MONO,
          fontSize: 11,
          padding: '6px 12px',
          borderRadius: 6,
          cursor: valid && dirty ? 'pointer' : 'default',
        }}
      >
        save
      </button>
      <div style={{ fontFamily: MONO, fontSize: 10, color: '#6b7280' }}>
        applies from the next re-index · already-extracted mail is not redone
      </div>
    </div>
  )
}

function SettingsDrawer({ open, onClose, status, useContext, toggleContext, onReindex, mutedSenders, onUnmute, tunables, onSaveSettings, dateFormat, onDateFormatChange }) {
  const [showMcp, setShowMcp] = useState(true)
  const sectionTitle = {
    fontFamily: MONO,
    fontSize: 11,
    color: '#6b7280',
    textTransform: 'uppercase',
    letterSpacing: '.05em',
    marginBottom: 10,
  }
  const card = { background: '#161a20', border: '1px solid #232830', borderRadius: 8, padding: 12 }
  const ollama = status?.ollama
  const index = status?.index
  const mcpCmd = index ? `claude mcp add localmail -- uv --directory ${index.backend_dir} run python mcp_server.py` : ''

  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.45)',
          opacity: open ? 1 : 0,
          pointerEvents: open ? 'auto' : 'none',
          transition: 'opacity .18s',
          zIndex: 20,
        }}
      />
      <div
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          height: '100%',
          width: 400,
          maxWidth: '92vw',
          background: '#12151a',
          borderLeft: '1px solid #232830',
          zIndex: 21,
          display: 'flex',
          flexDirection: 'column',
          transform: open ? 'translateX(0)' : 'translateX(100%)',
          transition: 'transform .2s ease',
          fontFamily: SANS,
          color: '#e8eaed',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 18px', borderBottom: '1px solid #232830' }}>
          <span style={{ fontFamily: MONO, fontWeight: 700, fontSize: 13.5 }}>MCP / RAG settings</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#6b7280', fontSize: 16, cursor: 'pointer', padding: 4 }}>
            ✕
          </button>
        </div>

        <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 22, overflowY: 'auto' }}>
          <div>
            <div style={sectionTitle}>Model connections</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ ...card, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px' }}>
                <div>
                  <div style={{ fontSize: 12.5, color: '#e2e5ea' }}>Ollama · {ollama ? ollama.url.replace(/^https?:\/\//, '') : '…'}</div>
                  <div style={{ fontFamily: MONO, fontSize: 10.5, color: '#6b7280', marginTop: 2 }}>
                    {ollama ? [ollama.chat_model, ollama.extraction_model, ollama.embed_model].filter((m, i, all) => m && all.indexOf(m) === i).join(' + ') : ''}
                  </div>
                </div>
                {ollama?.up ? (
                  <span style={{ fontFamily: MONO, fontSize: 10.5, color: '#4ADE80', display: 'flex', alignItems: 'center', gap: 5 }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#4ADE80' }} />
                    online
                  </span>
                ) : (
                  <span style={{ fontFamily: MONO, fontSize: 10.5, color: '#F87171', display: 'flex', alignItems: 'center', gap: 5 }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#F87171' }} />
                    offline
                  </span>
                )}
              </div>
              <div style={{ ...card, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', opacity: 0.6 }}>
                <div>
                  <div style={{ fontSize: 12.5, color: '#e2e5ea' }}>Claude · api.anthropic.com</div>
                  <div style={{ fontFamily: MONO, fontSize: 10.5, color: '#6b7280', marginTop: 2 }}>cloud support — planned (step 2)</div>
                </div>
                <span style={{ fontFamily: MONO, fontSize: 10.5, color: '#6b7280', display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#3a4048' }} />
                  soon
                </span>
              </div>
            </div>
          </div>

          <div>
            <div style={sectionTitle}>Data sources</div>
            <div style={card}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 12.5, color: '#e2e5ea' }}>Thunderbird mailboxes (.eml)</div>
                  <div
                    style={{ fontFamily: MONO, fontSize: 10.5, color: '#6b7280', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                    title={index?.maildir}
                  >
                    {index ? `${index.emails.toLocaleString()} messages · last ${index.window_days} days` : '…'}
                  </div>
                </div>
                <Switch on={useContext} onClick={toggleContext} />
              </div>
            </div>
          </div>

          <div>
            <div style={sectionTitle}>Indexing</div>
            <div style={card}>
              <IndexingSettings tunables={tunables} onSave={onSaveSettings} />
            </div>
          </div>

          <div>
            <div style={sectionTitle}>Display</div>
            <div style={{ ...card, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 12.5, color: '#e2e5ea' }}>date format</div>
                <div style={{ fontFamily: MONO, fontSize: 10, color: '#6b7280', marginTop: 1 }}>
                  how dates appear in mail, tasks and events
                </div>
              </div>
              <select
                value={dateFormat}
                aria-label="date format"
                onChange={(e) => onDateFormatChange(e.target.value)}
                style={{
                  background: '#0e1116',
                  border: '1px solid #262b33',
                  color: '#e8eaed',
                  fontFamily: MONO,
                  fontSize: 12,
                  padding: '6px 8px',
                  borderRadius: 6,
                  cursor: 'pointer',
                  flex: 'none',
                }}
              >
                {DATE_FORMATS.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <div style={sectionTitle}>Muted senders</div>
            <div style={{ ...card, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {mutedSenders.length === 0 && (
                <div style={{ fontFamily: MONO, fontSize: 11, color: '#6b7280' }}>
                  none — use “⊘ mute sender” on an email to exclude a sender from priority, tasks and events
                </div>
              )}
              {mutedSenders.map((s) => (
                <div key={s.sender_email} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                  <span
                    style={{ fontFamily: MONO, fontSize: 11, color: '#e2e5ea', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                    title={s.sender_email}
                  >
                    ⊘ {s.sender_email}
                  </span>
                  <button
                    onClick={() => onUnmute(s.sender_email)}
                    style={{
                      background: '#1a1f27',
                      border: '1px solid #262b33',
                      color: '#c4c9d1',
                      fontFamily: MONO,
                      fontSize: 10.5,
                      padding: '4px 10px',
                      borderRadius: 5,
                      cursor: 'pointer',
                      flex: 'none',
                    }}
                  >
                    unmute
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div>
            <div style={sectionTitle}>RAG index</div>
            <div style={{ ...card, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 12.5, color: '#e2e5ea' }}>Enable retrieval (inbox context)</span>
                <Switch on={useContext} onClick={toggleContext} />
              </div>
              <div style={{ fontFamily: MONO, fontSize: 11, color: '#6b7280' }}>
                {index ? `${index.chunks.toLocaleString()} chunks · last indexed ${relativeTime(index.last_indexed)}` : '…'}
              </div>
              <IndexProgress progress={index?.progress} />
              <button
                onClick={onReindex}
                disabled={index?.progress?.phase && !['idle', 'error'].includes(index.progress.phase)}
                style={{
                  alignSelf: 'flex-start',
                  background: '#1a1f27',
                  border: '1px solid #262b33',
                  color: '#c4c9d1',
                  fontFamily: MONO,
                  fontSize: 11,
                  padding: '6px 12px',
                  borderRadius: 6,
                  cursor: 'pointer',
                }}
              >
                ↻ re-index now
              </button>
            </div>
          </div>

          <div>
            <div style={sectionTitle}>MCP server</div>
            <div style={{ ...card, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 12.5, color: '#e2e5ea' }}>Mail tools via MCP (stdio)</span>
                <Switch on={showMcp} onClick={() => setShowMcp((v) => !v)} />
              </div>
              {showMcp ? (
                <>
                  <div style={{ fontFamily: MONO, fontSize: 11, color: '#4ADE80' }}>
                    tools: search_mail, get_thread, list_tasks, list_events
                  </div>
                  <div
                    style={{
                      fontFamily: MONO,
                      fontSize: 10.5,
                      color: '#9aa1ac',
                      background: '#0e1116',
                      border: '1px solid #1c2027',
                      borderRadius: 6,
                      padding: '8px 10px',
                      wordBreak: 'break-all',
                      cursor: 'copy',
                    }}
                    title="Click to copy"
                    onClick={() => navigator.clipboard?.writeText(mcpCmd)}
                  >
                    {mcpCmd}
                  </div>
                </>
              ) : (
                <div style={{ fontFamily: MONO, fontSize: 11, color: '#6b7280' }}>register command hidden</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

export default function App() {
  const [status, setStatus] = useState(null)
  const [stats, setStats] = useState(null)
  const [emails, setEmails] = useState([])
  const [tasks, setTasks] = useState([])
  const [events, setEvents] = useState([])
  const [mutedSenders, setMutedSenders] = useState([])
  const [tunables, setTunables] = useState(null)
  const [model, setModel] = useState('ollama')
  const [useContext, setUseContext] = useState(true)
  const [settingsOpen, setSettingsOpen] = useState(false)
  // display preference, per browser (not a backend tunable)
  const [dateFormat, setDateFormat] = useState(() => {
    const saved = localStorage.getItem('date_format')
    return DATE_FORMATS.some((f) => f.id === saved) ? saved : 'system'
  })
  const changeDateFormat = (fmt) => {
    setDateFormat(fmt)
    localStorage.setItem('date_format', fmt)
  }
  const [filter, setFilter] = useState('priority')
  const [expandedId, setExpandedId] = useState(null)
  const [pendingScrollId, setPendingScrollId] = useState(null)
  const [input, setInput] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [messages, setMessages] = useState([])
  // email pinned into the chat context by "summarize" ({id, subject}); stays
  // pinned for follow-up questions until cleared or replaced
  const [focusEmail, setFocusEmail] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const indexingRef = useRef(false)
  // email pulled in on demand by "go to mail" when it's older than the
  // newest-100 window the all-mail tab loads; merged into the list at render
  const [jumpedEmail, setJumpedEmail] = useState(null)
  const jumpedIdRef = useRef(null)

  const refreshData = useCallback(async () => {
    try {
      const jumpedId = jumpedIdRef.current
      const [st, em, tk, ev, ms, tu, je] = await Promise.all([
        api.stats(),
        api.emails(filter),
        api.tasks(),
        api.events(),
        api.mutedSenders(),
        api.settings(),
        jumpedId ? api.email(jumpedId).catch(() => null) : null,
      ])
      setStats(st)
      setEmails(em)
      setTasks(tk)
      setEvents(ev)
      setMutedSenders(ms)
      setTunables(tu)
      setJumpedEmail(je)
      setLoadError(null)
    } catch (e) {
      setLoadError(String(e.message || e))
    }
  }, [filter])

  // status polling: fast while indexing, slow otherwise; refresh data when
  // an indexing run finishes
  useEffect(() => {
    let stop = false
    let timer
    const poll = async () => {
      try {
        const s = await api.status()
        if (stop) return
        setStatus(s)
        const indexing = !['idle', 'error'].includes(s.index.progress.phase)
        if (indexingRef.current && !indexing) refreshData()
        indexingRef.current = indexing
        timer = setTimeout(poll, indexing ? 2000 : 15000)
      } catch {
        if (!stop) timer = setTimeout(poll, 5000)
      }
    }
    poll()
    return () => {
      stop = true
      clearTimeout(timer)
    }
  }, [refreshData])

  useEffect(() => {
    refreshData()
  }, [refreshData])

  const chatModel = status?.ollama?.chat_model || 'ollama'
  const indexedCount = status?.index?.emails ?? 0

  // shared by the chat input and the per-email "summarize" button: append the
  // user message and stream the assistant reply, optionally pinning an email
  const runChatTurn = async (userMsg, emailId) => {
    const history = [...messages, userMsg]
    setMessages(history)
    setIsTyping(true)

    const assistantId = Date.now() + 1
    let started = false
    try {
      await streamChat(
        {
          messages: history.filter((m) => !m.error).map((m) => ({ role: m.role, content: m.text })),
          model,
          useContext,
          emailId,
        },
        (token) => {
          if (!started) {
            started = true
            setIsTyping(false)
            setMessages((prev) => [...prev, { id: assistantId, role: 'assistant', model: chatModel, text: token, time: nowTime() }])
          } else {
            setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, text: m.text + token } : m)))
          }
        },
      )
    } catch (e) {
      const errText = String(e.message || e)
      if (started) {
        setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, text: m.text + `\n\n[error: ${errText}]`, error: true } : m)))
      } else {
        setMessages((prev) => [...prev, { id: assistantId, role: 'assistant', model: 'error', text: errText, time: nowTime(), error: true }])
      }
    } finally {
      setIsTyping(false)
    }
  }

  const sendMessage = () => {
    const text = input.trim()
    if (!text || isTyping) return
    setInput('')
    runChatTurn({ id: Date.now(), role: 'user', text, time: nowTime() }, focusEmail?.id)
  }

  // "summarize" on an email: ask in the chat panel with the full email pinned
  // into the context, and keep it pinned so follow-up questions work
  const summarizeEmail = (email) => {
    if (isTyping) return
    const subject = email.subject || '(no subject)'
    setFocusEmail({ id: email.id, subject })
    runChatTurn(
      { id: Date.now(), role: 'user', text: `Summarize this email from ${email.sender}: "${subject}"`, time: nowTime() },
      email.id,
    )
  }

  const toggleTask = async (id) => {
    setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, done: !t.done } : t)))
    try {
      const res = await api.toggleTask(id)
      setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, done: res.done } : t)))
    } catch {
      setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, done: !t.done } : t)))
    }
  }

  // jump to an email in "all mail": switch tab, expand it, scroll it into
  // view once the list for the new filter has rendered
  const goToEmail = async (emailId) => {
    setExpandedId(emailId)
    setPendingScrollId(emailId)
    setFilter('all')
    if (!emails.some((e) => e.id === emailId)) {
      jumpedIdRef.current = emailId
      try {
        setJumpedEmail(await api.email(emailId))
      } catch {
        setPendingScrollId(null) // email gone from DB; the row will never render
      }
    }
  }

  // all-mail list with the jumped-to email spliced in at its date-sorted
  // position when the newest-100 window doesn't include it
  const displayEmails = useMemo(() => {
    if (filter !== 'all' || !jumpedEmail || emails.some((e) => e.id === jumpedEmail.id)) {
      return emails
    }
    const idx = emails.findIndex((e) => e.date_utc < jumpedEmail.date_utc)
    const merged = [...emails]
    merged.splice(idx === -1 ? merged.length : idx, 0, jumpedEmail)
    return merged
  }, [emails, jumpedEmail, filter])

  useEffect(() => {
    if (pendingScrollId === null) return
    const el = document.getElementById(`email-${pendingScrollId}`)
    if (el) {
      if (typeof el.scrollIntoView === 'function') el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      setPendingScrollId(null)
    }
  }, [pendingScrollId, displayEmails])

  // both change what several tabs and counters show → refetch everything.
  // Collapsed event rows carry several source emails: dismiss them all.
  const dismissEmails = async (ids) => {
    try {
      await Promise.all(ids.map((id) => api.dismissEmail(id)))
    } catch {
      /* partial failure: the refresh below shows the real state */
    }
    await refreshData()
  }
  const dismissEmail = (id) => dismissEmails([id])

  const muteSender = async (senderEmail) => {
    try {
      await api.muteSender(senderEmail)
      await refreshData()
    } catch {
      /* refresh keeps UI consistent even on failure */
    }
  }

  const saveSettings = async (values) => {
    try {
      const saved = await api.updateSettings(values)
      setTunables(saved)
    } catch {
      /* leave the draft as-is; the drawer keeps showing unsaved values */
    }
  }

  const reindex = async () => {
    try {
      await api.reindex()
      const s = await api.status()
      setStatus(s)
      indexingRef.current = true
    } catch {
      /* status poll will surface it */
    }
  }

  const openTasks = tasks.filter((t) => !t.done)
  // events tab structure: day → sender → deduped rows; the tile/tab counts
  // use the deduped rows so they match what the tab shows
  const groupedEvents = useMemo(() => groupUpcomingEvents(events), [events])
  const upcomingCount = useMemo(
    () => groupedEvents.reduce((n, g) => n + g.senders.reduce((m, s) => m + s.events.length, 0), 0),
    [groupedEvents],
  )
  // tasks/events tiles count the same client-side lists as the tabs below,
  // so the two can never disagree; stats is only the source for counts the
  // UI doesn't hold (unread, high priority). `stats` doubles as the
  // "first load done" flag: refreshData sets it together with tasks/events.
  const statTiles = [
    { label: 'unread', value: stats?.unread ?? '–', color: '#e8eaed' },
    { label: 'open tasks', value: stats ? openTasks.length : '–', color: '#FBBF24' },
    { label: 'upcoming events', value: stats ? upcomingCount : '–', color: '#4ADE80' },
    { label: 'high priority', value: stats?.high_priority ?? '–', color: '#F87171' },
  ]

  const filterDefs = [
    { id: 'priority', label: `priority (${stats?.high_priority ?? 0})` },
    { id: 'all', label: `all mail (${indexedCount})` },
    { id: 'tasks', label: `tasks (${openTasks.length})` },
    { id: 'events', label: `events (${upcomingCount})` },
  ]

  return (
    <div
      style={{
        height: '100vh',
        width: '100vw',
        display: 'flex',
        flexDirection: 'column',
        background: '#0b0d10',
        color: '#e8eaed',
        fontFamily: SANS,
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      <Header ollamaUp={status?.ollama?.up ?? false} onOpenSettings={() => setSettingsOpen(true)} />

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>
        <ChatPane
          chatModel={chatModel}
          model={model}
          onModelChange={(e) => setModel(e.target.value)}
          useContext={useContext}
          toggleContext={() => setUseContext((v) => !v)}
          indexedCount={indexedCount}
          messages={messages}
          isTyping={isTyping}
          input={input}
          onInputChange={(e) => setInput(e.target.value)}
          onSend={sendMessage}
          focusEmail={focusEmail}
          onClearFocus={() => setFocusEmail(null)}
        />

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}>
          <div style={{ flex: 'none', display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10, padding: '18px 20px 14px' }}>
            {statTiles.map((s) => (
              <div key={s.label} style={{ background: '#12151a', border: '1px solid #232830', borderRadius: 8, padding: '12px 14px' }}>
                <div style={{ fontFamily: MONO, fontSize: 22, fontWeight: 700, color: s.color }}>{s.value}</div>
                <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2, textTransform: 'uppercase', letterSpacing: '.04em' }}>{s.label}</div>
              </div>
            ))}
          </div>

          <div style={{ flex: 'none', display: 'flex', gap: 8, padding: '0 20px 14px', alignItems: 'center' }}>
            {filterDefs.map((f) => {
              const active = filter === f.id
              return (
                <button
                  key={f.id}
                  onClick={() => setFilter(f.id)}
                  style={{
                    background: active ? '#1a2b3d' : '#12151a',
                    border: `1px solid ${active ? '#2a5a8c' : '#232830'}`,
                    color: active ? '#7dd3fc' : '#9aa1ac',
                    fontFamily: MONO,
                    fontSize: 11.5,
                    padding: '6px 12px',
                    borderRadius: 16,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {f.label}
                </button>
              )
            })}
            <div style={{ marginLeft: 'auto' }}>
              <IndexProgress progress={status?.index?.progress} />
            </div>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: '0 20px 20px', display: 'flex', flexDirection: 'column', gap: 9, minHeight: 0 }}>
            {loadError && (
              <div style={{ fontFamily: MONO, fontSize: 12, color: '#F87171', padding: 12, background: '#1a1214', border: '1px solid #4a1f1f', borderRadius: 8 }}>
                backend unreachable: {loadError}
              </div>
            )}
            {(filter === 'priority' || filter === 'all') &&
              displayEmails.map((e) => (
                <EmailRow
                  key={e.id}
                  email={e}
                  expanded={expandedId === e.id}
                  onToggle={() => setExpandedId((cur) => (cur === e.id ? null : e.id))}
                  onDismiss={() => dismissEmail(e.id)}
                  onMute={() => muteSender(e.sender_email)}
                  onGoTo={filter === 'priority' ? () => goToEmail(e.id) : null}
                  onSummarize={filter === 'all' ? () => summarizeEmail(e) : null}
                  dateFormat={dateFormat}
                />
              ))}
            {(filter === 'priority' || filter === 'all') && displayEmails.length === 0 && !loadError && (
              <div style={{ fontFamily: MONO, fontSize: 12, color: '#3a4048', textAlign: 'center', marginTop: 40 }}>
                {filter === 'priority' ? 'no high-priority mail (yet — extraction may still be running)' : 'no mail indexed yet'}
              </div>
            )}
            {filter === 'tasks' &&
              tasks.map((t) => (
                <TaskRow
                  key={t.id}
                  task={t}
                  onToggle={() => toggleTask(t.id)}
                  onDismiss={() => dismissEmail(t.email_id)}
                  onGoTo={() => goToEmail(t.email_id)}
                />
              ))}
            {filter === 'tasks' && tasks.length === 0 && (
              <div style={{ fontFamily: MONO, fontSize: 12, color: '#3a4048', textAlign: 'center', marginTop: 40 }}>no tasks extracted yet</div>
            )}
            {filter === 'events' &&
              groupedEvents.map((g) => (
                <div key={g.key} style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                  <div
                    style={{
                      fontFamily: MONO,
                      fontSize: 11,
                      color: '#7dd3fc',
                      textTransform: 'uppercase',
                      letterSpacing: '.05em',
                      marginTop: 8,
                      paddingBottom: 4,
                      borderBottom: '1px solid #1c2027',
                    }}
                  >
                    ▸ {eventGroupLabel(g.date, dateFormat)}
                  </div>
                  {g.senders.map((s) => (
                    <div key={s.sender || '(unknown)'} style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                      <div style={{ fontFamily: MONO, fontSize: 10.5, color: '#6b7280', paddingLeft: 2 }}>{s.sender || '(unknown sender)'}</div>
                      {s.events.map((ev) => (
                        <EventRow key={ev.id} event={ev} onDismiss={() => dismissEmails(ev.emailIds)} onGoTo={() => goToEmail(ev.email_id)} />
                      ))}
                    </div>
                  ))}
                </div>
              ))}
            {filter === 'events' && upcomingCount === 0 && (
              <div style={{ fontFamily: MONO, fontSize: 12, color: '#3a4048', textAlign: 'center', marginTop: 40 }}>
                {events.length ? 'no upcoming events' : 'no events extracted yet'}
              </div>
            )}
          </div>
        </div>
      </div>

      <SettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        status={status}
        useContext={useContext}
        toggleContext={() => setUseContext((v) => !v)}
        onReindex={reindex}
        mutedSenders={mutedSenders}
        onUnmute={muteSender}
        tunables={tunables}
        onSaveSettings={saveSettings}
        dateFormat={dateFormat}
        onDateFormatChange={changeDateFormat}
      />
    </div>
  )
}
