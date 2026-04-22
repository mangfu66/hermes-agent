import { describe, expect, it } from 'vitest'

import { initialEnterGuardStep } from '../components/modelPicker.js'

describe('initialEnterGuardStep', () => {
  it('swallows the enter that opened the picker', () => {
    expect(initialEnterGuardStep(true, '', { return: true })).toEqual({
      consume: true,
      swallowNextEnter: false
    })
  })

  it('clears the guard on real navigation so the next enter works', () => {
    expect(initialEnterGuardStep(true, '', { downArrow: true })).toEqual({
      consume: false,
      swallowNextEnter: false
    })
    expect(initialEnterGuardStep(true, '1', {})).toEqual({
      consume: false,
      swallowNextEnter: false
    })
  })

  it('does nothing once the guard is cleared', () => {
    expect(initialEnterGuardStep(false, '', { return: true })).toEqual({
      consume: false,
      swallowNextEnter: false
    })
  })
})
