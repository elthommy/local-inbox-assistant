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

export function eventDateShort(raw) {
  if (!raw) return '—'
  // dd/mm/yyyy (French) — JS Date would read it as mm/dd
  const fr = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/)
  const d = fr ? new Date(`${fr[3]}-${fr[2].padStart(2, '0')}-${fr[1].padStart(2, '0')}`) : new Date(raw)
  if (!isNaN(d.getTime())) {
    return d.toLocaleDateString('en', { month: 'short', day: 'numeric' }).toUpperCase()
  }
  return raw.slice(0, 8).toUpperCase()
}

export function nowTime() {
  return new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}
