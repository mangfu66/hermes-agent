import type { Msg } from '../types.js'

export const LARGE_PASTE = { chars: 8000, lines: 80 }
export const LONG_MSG = 300
export const MAX_HISTORY = 300
export const THINKING_COT_MAX = 160
export const WHEEL_SCROLL_STEP = 3

export const capHistory = (items: Msg[]): Msg[] => {
  if (items.length <= MAX_HISTORY) {
    return items
  }

  return items[0]?.kind === 'intro' ? [items[0]!, ...items.slice(-(MAX_HISTORY - 1))] : items.slice(-MAX_HISTORY)
}
