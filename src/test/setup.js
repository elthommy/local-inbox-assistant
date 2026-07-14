import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// this jsdom build has no localStorage; give tests an in-memory stand-in
if (typeof window !== 'undefined' && !window.localStorage) {
  const store = new Map()
  Object.defineProperty(window, 'localStorage', {
    value: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
      clear: () => store.clear(),
    },
  })
}

afterEach(() => {
  cleanup()
})
