import { describe, expect, it, vi, afterEach } from 'vitest'
import {
  AVATAR_COLORS,
  avatarColor,
  eventChipDate,
  eventDateShort,
  eventGroupLabel,
  formatDate,
  formatEmailTime,
  groupUpcomingEvents,
  parseEventDate,
  priorityColor,
  relativeTime,
  upcomingEvents,
} from '../utils.js'

afterEach(() => vi.useRealTimers())

describe('priorityColor', () => {
  it('maps each priority to its dot color', () => {
    expect(priorityColor('high')).toBe('#F87171')
    expect(priorityColor('medium')).toBe('#FBBF24')
    expect(priorityColor('low')).toBe('#4ADE80')
  })
  it('falls back to grey for null/unknown (not yet extracted)', () => {
    expect(priorityColor(null)).toBe('#3a4048')
    expect(priorityColor('weird')).toBe('#3a4048')
  })
})

describe('avatarColor', () => {
  it('is deterministic', () => {
    expect(avatarColor('Sarah Chen')).toBe(avatarColor('Sarah Chen'))
  })
  it('always returns a palette color', () => {
    for (const name of ['a', 'Amazon.fr', 'Rémi Dupont', '']) {
      expect(AVATAR_COLORS).toContain(avatarColor(name))
    }
  })
})

describe('formatEmailTime', () => {
  it('shows the time for today', () => {
    vi.useFakeTimers().setSystemTime(new Date('2026-07-12T15:00:00'))
    expect(formatEmailTime('2026-07-12T09:14:00')).toMatch(/9[:h]14/)
  })
  it("shows 'Yesterday' for yesterday", () => {
    vi.useFakeTimers().setSystemTime(new Date('2026-07-12T15:00:00'))
    expect(formatEmailTime('2026-07-11T23:00:00')).toBe('Yesterday')
  })
  it('shows month + day for older mail', () => {
    vi.useFakeTimers().setSystemTime(new Date('2026-07-12T15:00:00'))
    expect(formatEmailTime('2026-07-01T10:00:00')).toMatch(/1/)
    expect(formatEmailTime('2026-07-01T10:00:00')).not.toBe('Yesterday')
  })
  it('honors an explicit date format for older mail', () => {
    vi.useFakeTimers().setSystemTime(new Date('2026-07-12T15:00:00'))
    expect(formatEmailTime('2026-07-01T10:00:00', 'dmy')).toBe('01/07/2026')
    // today/yesterday wording is kept regardless of the format
    expect(formatEmailTime('2026-07-11T10:00:00', 'dmy')).toBe('Yesterday')
  })
})

describe('formatDate', () => {
  const d = new Date(2026, 6, 5)
  it('renders the explicit formats', () => {
    expect(formatDate(d, 'dmy')).toBe('05/07/2026')
    expect(formatDate(d, 'mdy')).toBe('07/05/2026')
    expect(formatDate(d, 'ymd')).toBe('2026-07-05')
  })
  it('defaults to the system locale', () => {
    expect(formatDate(d)).toBe(d.toLocaleDateString())
  })
})

describe('relativeTime', () => {
  it("returns 'never' for empty input", () => {
    expect(relativeTime('')).toBe('never')
    expect(relativeTime(null)).toBe('never')
  })
  it('scales from just now to days', () => {
    vi.useFakeTimers().setSystemTime(new Date('2026-07-12T12:00:00Z'))
    expect(relativeTime('2026-07-12T11:59:40Z')).toBe('just now')
    expect(relativeTime('2026-07-12T11:48:00Z')).toBe('12 min ago')
    expect(relativeTime('2026-07-12T09:00:00Z')).toBe('3 h ago')
    expect(relativeTime('2026-07-09T12:00:00Z')).toBe('3 d ago')
  })
})

describe('eventDateShort', () => {
  it('handles empty', () => {
    expect(eventDateShort('')).toBe('—')
    expect(eventDateShort(null)).toBe('—')
  })
  it('defaults to a short badge in the system locale', () => {
    const expected = new Date(2026, 6, 14)
      .toLocaleDateString([], { month: 'short', day: 'numeric' })
      .toUpperCase()
    expect(eventDateShort('2026-07-14')).toBe(expected)
  })
  it('honors an explicit date format', () => {
    expect(eventDateShort('2026-07-14', undefined, 'dmy')).toBe('14/07/2026')
    expect(eventDateShort('2026-07-14', undefined, 'mdy')).toBe('07/14/2026')
  })
  it('parses French dd/mm/yyyy as day/month (regression: was read as US mm/dd)', () => {
    expect(eventDateShort('11/07/2026', undefined, 'ymd')).toBe('2026-07-11')
    expect(eventDateShort('01/12/2026', undefined, 'ymd')).toBe('2026-12-01')
  })
  it('falls back to truncated raw text when unparseable', () => {
    expect(eventDateShort('vendredi soir')).toBe('VENDREDI')
  })
})

describe('eventChipDate', () => {
  it('formats resolvable dates and leaves free text as written', () => {
    expect(eventChipDate('2026-07-15', undefined, 'dmy')).toBe('15/07/2026')
    expect(eventChipDate('demain', '2026-07-14T09:00:00', 'dmy')).toBe('15/07/2026')
    expect(eventChipDate('prochainement', '2026-07-14T09:00:00', 'dmy')).toBe('prochainement')
  })
})

describe('parseEventDate', () => {
  it('returns null for empty or unparseable input', () => {
    expect(parseEventDate('')).toBeNull()
    expect(parseEventDate(null)).toBeNull()
    expect(parseEventDate('vendredi soir')).toBeNull()
  })
  it('parses ISO dates as local midnight', () => {
    const d = parseEventDate('2026-07-14')
    expect(d.getFullYear()).toBe(2026)
    expect(d.getMonth()).toBe(6)
    expect(d.getDate()).toBe(14)
    expect(d.getHours()).toBe(0)
  })
  it('parses French dd/mm/yyyy', () => {
    const d = parseEventDate('01/12/2026')
    expect(d.getMonth()).toBe(11)
    expect(d.getDate()).toBe(1)
  })
  it('pins year-less dates to the current year (JS defaults them to 2001)', () => {
    vi.useFakeTimers().setSystemTime(new Date('2026-07-12T15:00:00'))
    expect(parseEventDate('July 20').getFullYear()).toBe(2026)
  })
  it('resolves weekday names to the first such day on/after the email date', () => {
    // 2026-07-14 is a Tuesday → vendredi = Friday the 17th
    const d = parseEventDate('vendredi soir', '2026-07-14T09:00:00')
    expect([d.getMonth(), d.getDate()]).toEqual([6, 17])
    // email sent on a Friday → "vendredi" is that same day
    const same = parseEventDate('vendredi', '2026-07-17T09:00:00')
    expect(same.getDate()).toBe(17)
    const en = parseEventDate('Monday morning', '2026-07-14T09:00:00')
    expect(en.getDate()).toBe(20)
  })
  it('resolves today/tomorrow wordings against the email date', () => {
    expect(parseEventDate('ce soir', '2026-07-14T09:00:00').getDate()).toBe(14)
    expect(parseEventDate("aujourd'hui", '2026-07-14T09:00:00').getDate()).toBe(14)
    expect(parseEventDate('demain', '2026-07-14T09:00:00').getDate()).toBe(15)
    expect(parseEventDate('tomorrow', '2026-07-14T09:00:00').getDate()).toBe(15)
  })
  it('explicit dates win over the email date; no email date → relative text stays null', () => {
    expect(parseEventDate('2026-08-01', '2026-07-14T09:00:00').getDate()).toBe(1)
    expect(parseEventDate('vendredi soir')).toBeNull()
  })
})

describe('upcomingEvents', () => {
  const now = new Date('2026-07-14T15:00:00')
  it('drops past events, keeps today and future, sorted ascending', () => {
    const evs = [
      { id: 1, date: '2026-08-01' },
      { id: 2, date: '2026-07-10' },
      { id: 3, date: '2026-07-14' },
      { id: 4, date: '20/07/2026' },
    ]
    expect(upcomingEvents(evs, now).map((e) => e.id)).toEqual([3, 4, 1])
  })
  it('keeps events with unparseable dates at the end', () => {
    const evs = [
      { id: 1, date: 'vendredi soir' },
      { id: 2, date: '2026-07-15' },
      { id: 3, date: '' },
    ]
    expect(upcomingEvents(evs, now).map((e) => e.id)).toEqual([2, 1, 3])
  })
  it('resolves relative dates via the source-email date and sorts/filters them like the rest', () => {
    const evs = [
      // Friday after a Tuesday-14th email → Jul 17, sorts between 15 and 20
      { id: 1, date: 'vendredi soir', date_utc: '2026-07-14T09:00:00' },
      { id: 2, date: '2026-07-20' },
      { id: 3, date: '2026-07-15' },
      // resolved to a past Friday → dropped
      { id: 4, date: 'vendredi', date_utc: '2026-07-06T09:00:00' },
    ]
    expect(upcomingEvents(evs, now).map((e) => e.id)).toEqual([3, 1, 2])
  })
  it('returns empty for no events', () => {
    expect(upcomingEvents([], now)).toEqual([])
  })
})

describe('groupUpcomingEvents', () => {
  const now = new Date('2026-07-14T15:00:00')

  it('groups by day (soonest first) then by sender', () => {
    const evs = [
      { id: 1, email_id: 1, title: 'Livraison prévue', date: '2026-07-20', time: '', source: 'Amazon.fr', date_utc: '2026-07-13' },
      { id: 2, email_id: 2, title: 'Train Paris-Lyon', date: '2026-07-18', time: '14:32', source: 'SNCF', date_utc: '2026-07-12' },
      { id: 3, email_id: 3, title: 'Livraison prévue: chargeur', date: '2026-07-18', time: '', source: 'Amazon.fr', date_utc: '2026-07-13' },
    ]
    const groups = groupUpcomingEvents(evs, now)
    expect(groups.map((g) => g.key)).toEqual(['2026-07-18', '2026-07-20'])
    expect(groups[0].senders.map((s) => s.sender)).toEqual(['SNCF', 'Amazon.fr'])
    expect(groups[1].senders.map((s) => s.sender)).toEqual(['Amazon.fr'])
  })

  it('collapses same-sender same-title events on the same day, keeping every source email', () => {
    const evs = [
      { id: 1, email_id: 10, title: 'Livraison prévue', date: '2026-07-18', time: '', source: 'Amazon.fr', date_utc: '2026-07-12' },
      { id: 2, email_id: 11, title: 'livraison  PRÉVUE', date: '2026-07-18', time: '', source: 'Amazon.fr', date_utc: '2026-07-13' },
      { id: 3, email_id: 12, title: 'Livraison prévue', date: '2026-07-18', time: '', source: 'Amazon.fr', date_utc: '2026-07-11' },
    ]
    const groups = groupUpcomingEvents(evs, now)
    expect(groups).toHaveLength(1)
    expect(groups[0].senders[0].events).toHaveLength(1)
    const entry = groups[0].senders[0].events[0]
    expect(entry.count).toBe(3)
    expect(entry.emailIds.sort()).toEqual([10, 11, 12])
    // the copy from the newest email is the representative
    expect(entry.email_id).toBe(11)
  })

  it('does not collapse across days, senders or titles', () => {
    const evs = [
      { id: 1, email_id: 1, title: 'Livraison prévue', date: '2026-07-18', time: '', source: 'Amazon.fr', date_utc: '2026-07-12' },
      { id: 2, email_id: 2, title: 'Livraison prévue', date: '2026-07-19', time: '', source: 'Amazon.fr', date_utc: '2026-07-12' },
      { id: 3, email_id: 3, title: 'Livraison prévue', date: '2026-07-18', time: '', source: 'Cdiscount', date_utc: '2026-07-12' },
      { id: 4, email_id: 4, title: 'Retrait en point relais', date: '2026-07-18', time: '', source: 'Amazon.fr', date_utc: '2026-07-12' },
    ]
    const groups = groupUpcomingEvents(evs, now)
    const rows = groups.flatMap((g) => g.senders.flatMap((s) => s.events))
    expect(rows).toHaveLength(4)
    expect(rows.every((r) => r.count === 1)).toBe(true)
  })

  it('never loses a time carried by an older duplicate', () => {
    const evs = [
      { id: 1, email_id: 1, title: 'Livraison prévue', date: '2026-07-18', time: '13:00', source: 'Amazon.fr', date_utc: '2026-07-12' },
      { id: 2, email_id: 2, title: 'Livraison prévue', date: '2026-07-18', time: '', source: 'Amazon.fr', date_utc: '2026-07-13' },
    ]
    const entry = groupUpcomingEvents(evs, now)[0].senders[0].events[0]
    expect(entry.email_id).toBe(2) // newest email wins…
    expect(entry.time).toBe('13:00') // …but the known time is kept
  })

  it('puts events with unresolvable dates in a trailing date:null group', () => {
    const evs = [
      { id: 1, email_id: 1, title: 'Réunion', date: 'prochainement', time: '', source: 'Alice', date_utc: '2026-07-12' },
      { id: 2, email_id: 2, title: 'Train', date: '2026-07-18', time: '', source: 'SNCF', date_utc: '2026-07-12' },
    ]
    const groups = groupUpcomingEvents(evs, now)
    expect(groups.map((g) => g.key)).toEqual(['2026-07-18', 'no-date'])
    expect(groups[1].date).toBeNull()
    expect(groups[1].senders[0].events[0].title).toBe('Réunion')
  })

  it('drops past events like upcomingEvents does', () => {
    const evs = [{ id: 1, email_id: 1, title: 'Livraison', date: '2026-07-10', time: '', source: 'Amazon.fr', date_utc: '2026-07-08' }]
    expect(groupUpcomingEvents(evs, now)).toEqual([])
  })
})

describe('eventGroupLabel', () => {
  const now = new Date('2026-07-14T15:00:00')
  it('labels today and tomorrow', () => {
    expect(eventGroupLabel(new Date(2026, 6, 14), 'dmy', now)).toBe('today · 14/07/2026')
    expect(eventGroupLabel(new Date(2026, 6, 15), 'dmy', now)).toBe('tomorrow · 15/07/2026')
  })
  it('uses the weekday for later days', () => {
    const d = new Date(2026, 6, 18)
    const weekday = d.toLocaleDateString([], { weekday: 'short' })
    expect(eventGroupLabel(d, 'dmy', now)).toBe(`${weekday} · 18/07/2026`)
  })
  it('handles the undated group', () => {
    expect(eventGroupLabel(null, 'dmy', now)).toBe('no date')
  })
})
