/**
 * Tests for lib/utils.ts — Utility functions
 */
import { describe, it, expect } from 'vitest'
import { cn } from '../lib/utils'

describe('cn (classname merger)', () => {
    it('merges class names', () => {
        expect(cn('foo', 'bar')).toBe('foo bar')
    })

    it('handles conditional classes', () => {
        expect(cn('base', false && 'hidden', 'end')).toBe('base end')
    })

    it('deduplicates tailwind classes', () => {
        expect(cn('px-2', 'px-4')).toBe('px-4')
    })

    it('handles empty input', () => {
        expect(cn()).toBe('')
    })

    it('handles undefined/null', () => {
        expect(cn('a', undefined, null, 'b')).toBe('a b')
    })
})
