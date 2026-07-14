export const AVATAR_COLORS = ['#F87171', '#FBBF24', '#38BDF8', '#4ADE80', '#A78BFA', '#F472B6', '#2DD4BF']

export function avatarColor(name) {
  let h = 0
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) >>> 0
  return AVATAR_COLORS[h % AVATAR_COLORS.length]
}

export function priorityColor(p) {
  return p === 'high' ? '#F87171' : p === 'medium' ? '#FBBF24' : p === 'low' ? '#4ADE80' : '#3a4048'
}

export function formatEmailTime(iso) {
  const d = new Date(iso)
  const now = new Date()
  const sameDay = (a, b) => a.toDateString() === b.toDateString()
  if (sameDay(d, now)) return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (sameDay(d, yesterday)) return 'Yesterday'
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
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

export function eventDateShort(raw, emailIso) {
  if (!raw) return '—'
  const d = parseEventDate(raw, emailIso)
  if (d) return d.toLocaleDateString('en', { month: 'short', day: 'numeric' }).toUpperCase()
  return raw.slice(0, 8).toUpperCase()
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

export function nowTime() {
  return new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}
