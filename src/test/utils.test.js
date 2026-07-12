import { describe, expect, it, vi, afterEach } from 'vitest'
import {
  AVATAR_COLORS,
  avatarColor,
  eventDateShort,
  formatEmailTime,
  priorityColor,
  relativeTime,
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
  it('parses ISO dates', () => {
    expect(eventDateShort('2026-07-14')).toBe('JUL 14')
  })
  it('parses French dd/mm/yyyy as day/month (regression: was read as US mm/dd)', () => {
    expect(eventDateShort('11/07/2026')).toBe('JUL 11')
    expect(eventDateShort('01/12/2026')).toBe('DEC 1')
  })
  it('falls back to truncated raw text when unparseable', () => {
    expect(eventDateShort('vendredi soir')).toBe('VENDREDI')
  })
})
