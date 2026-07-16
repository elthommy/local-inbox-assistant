export const AVATAR_COLORS = ['#F87171', '#FBBF24', '#38BDF8', '#4ADE80', '#A78BFA', '#F472B6', '#2DD4BF']

export function avatarColor(name) {
  let h = 0
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) >>> 0
  return AVATAR_COLORS[h % AVATAR_COLORS.length]
}

export function priorityColor(p) {
  return p === 'high' ? '#F87171' : p === 'medium' ? '#FBBF24' : p === 'low' ? '#4ADE80' : '#3a4048'
}

// User-selectable date rendering. 'system' delegates to the browser locale;
// the persisted preference lives in localStorage (see App).
export const DATE_FORMATS = [
  { id: 'system', label: 'system locale' },
  { id: 'dmy', label: 'DD/MM/YYYY' },
  { id: 'mdy', label: 'MM/DD/YYYY' },
  { id: 'ymd', label: 'YYYY-MM-DD' },
]

export function formatDate(d, fmt = 'system') {
  const dd = String(d.getDate()).padStart(2, '0')
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  if (fmt === 'dmy') return `${dd}/${mm}/${d.getFullYear()}`
  if (fmt === 'mdy') return `${mm}/${dd}/${d.getFullYear()}`
  if (fmt === 'ymd') return `${d.getFullYear()}-${mm}-${dd}`
  return d.toLocaleDateString()
}

export function formatEmailTime(iso, fmt = 'system') {
  const d = new Date(iso)
  const now = new Date()
  const sameDay = (a, b) => a.toDateString() === b.toDateString()
  if (sameDay(d, now)) return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (sameDay(d, yesterday)) return 'Yesterday'
  if (fmt === 'system') return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
  return formatDate(d, fmt)
}

export function relativeTime(iso) {
  if (!iso) return 'never'
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (secs < 60) return 'just now'
  if (secs < 3600) return `${Math.floor(secs / 60)} min ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)} h ago`
  return `${Math.floor(secs / 86400)} d ago`
}

const WEEKDAYS = {
  dimanche: 0, lundi: 1, mardi: 2, mercredi: 3, jeudi: 4, vendredi: 5, samedi: 6,
  sunday: 0, monday: 1, tuesday: 2, wednesday: 3, thursday: 4, friday: 5, saturday: 6,
}
const WEEKDAY_RE = new RegExp(`\\b(${Object.keys(WEEKDAYS).join('|')})\\b`)

// Resolve relative wordings ("vendredi soir", "demain", "tonight") against
// the date the email was sent; same weekday as the send day means that day.
function resolveRelativeDate(raw, emailIso) {
  if (!emailIso) return null
  const base = new Date(emailIso)
  if (isNaN(base.getTime())) return null
  const day = new Date(base.getFullYear(), base.getMonth(), base.getDate())
  const lower = raw.toLowerCase()
  if (/\b(aujourd['’]hui|ce soir|today|tonight)\b/.test(lower)) return day
  if (/\b(demain|tomorrow)\b/.test(lower)) {
    day.setDate(day.getDate() + 1)
    return day
  }
  const m = lower.match(WEEKDAY_RE)
  if (!m) return null
  day.setDate(day.getDate() + ((WEEKDAYS[m[1]] - day.getDay() + 7) % 7))
  return day
}

export function parseEventDate(raw, emailIso) {
  if (!raw) return null
  // dd/mm/yyyy (French) — JS Date would read it as mm/dd
  const fr = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/)
  const iso = fr
    ? `${fr[3]}-${fr[2].padStart(2, '0')}-${fr[1].padStart(2, '0')}`
    : /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : null
  // bare ISO dates parse as UTC midnight; add a time so they land on the
  // local calendar day instead
  const d = iso ? new Date(`${iso}T00:00:00`) : new Date(raw)
  if (isNaN(d.getTime())) return resolveRelativeDate(raw, emailIso)
  // year-less dates ("July 20") default to 2001 in JS — pin to current year
  if (!/\d{4}/.test(raw)) d.setFullYear(new Date().getFullYear())
  return d
}

export function eventDateShort(raw, emailIso, fmt = 'system') {
  if (!raw) return '—'
  const d = parseEventDate(raw, emailIso)
  if (!d) return raw.slice(0, 8).toUpperCase()
  if (fmt === 'system') {
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' }).toUpperCase()
  }
  return formatDate(d, fmt)
}

// Event chips inside an email row: the stored (usually ISO) date rendered in
// the user's format; unresolvable free text is shown as written.
export function eventChipDate(raw, emailIso, fmt = 'system') {
  const d = parseEventDate(raw, emailIso)
  return d ? formatDate(d, fmt) : raw
}

// Events happening today or later, soonest first. Events whose date can't be
// parsed go last: they can't be proven past, so they stay visible.
export function upcomingEvents(events, now = new Date()) {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const dated = []
  const undated = []
  for (const ev of events) {
    const d = parseEventDate(ev.date, ev.date_utc)
    if (!d) undated.push(ev)
    else if (d >= startOfToday) dated.push([d, ev])
  }
  dated.sort((a, b) => a[0] - b[0])
  return dated.map(([, ev]) => ev).concat(undated)
}

// Same local calendar day as a stable grouping key (YYYY-MM-DD).
function dayKey(d) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

// Case/whitespace-insensitive title key for spotting reminder duplicates.
function titleKey(title) {
  return (title || '').toLowerCase().replace(/\s+/g, ' ').trim()
}

// Fold a duplicate into its collapsed entry: the copy from the newest email
// wins (latest reminder has the freshest details), but a time carried by any
// copy is never lost.
function mergeDuplicate(entry, ev) {
  if (!entry.emailIds.includes(ev.email_id)) entry.emailIds.push(ev.email_id)
  entry.count = entry.emailIds.length
  if ((ev.date_utc || '') > (entry.date_utc || '')) {
    const keptTime = entry.time
    Object.assign(entry, ev)
    if (!entry.time) entry.time = keptTime
  } else if (!entry.time && ev.time) {
    entry.time = ev.time
  }
}

// Upcoming events grouped by calendar day, then by sender, for the events
// tab. Within one (day, sender) group, events with the same title — reminder
// emails resent by the same service — are collapsed into a single entry
// carrying `count` and the `emailIds` of every copy. Days come soonest
// first; events whose date can't be parsed form a trailing date:null group
// (same policy as upcomingEvents: they can't be proven past).
export function groupUpcomingEvents(events, now = new Date()) {
  const groups = []
  const byDay = new Map()
  for (const ev of upcomingEvents(events, now)) {
    const d = parseEventDate(ev.date, ev.date_utc)
    const key = d ? dayKey(d) : 'no-date'
    let group = byDay.get(key)
    if (!group) {
      group = { key, date: d, senders: [], _senders: new Map() }
      byDay.set(key, group)
      groups.push(group)
    }
    let senderGroup = group._senders.get(ev.source)
    if (!senderGroup) {
      senderGroup = { sender: ev.source, events: [], _titles: new Map() }
      group._senders.set(ev.source, senderGroup)
      group.senders.push(senderGroup)
    }
    const entry = senderGroup._titles.get(titleKey(ev.title))
    if (entry) {
      mergeDuplicate(entry, ev)
    } else {
      const fresh = { ...ev, count: 1, emailIds: [ev.email_id] }
      senderGroup._titles.set(titleKey(ev.title), fresh)
      senderGroup.events.push(fresh)
    }
  }
  return groups.map(({ key, date, senders }) => ({
    key,
    date,
    senders: senders.map(({ sender, events: evs }) => ({ sender, events: evs })),
  }))
}

// Header label for a date group: "today · 18/07/2026", "tomorrow · …", or
// weekday + date for later days; null date (unresolvable) → "no date".
export function eventGroupLabel(d, fmt = 'system', now = new Date()) {
  if (!d) return 'no date'
  const sameDay = (a, b) => a.toDateString() === b.toDateString()
  const label = formatDate(d, fmt)
  if (sameDay(d, now)) return `today · ${label}`
  const tomorrow = new Date(now)
  tomorrow.setDate(now.getDate() + 1)
  if (sameDay(d, tomorrow)) return `tomorrow · ${label}`
  return `${d.toLocaleDateString([], { weekday: 'short' })} · ${label}`
}

export function nowTime() {
  return new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}
