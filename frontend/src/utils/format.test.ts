import { describe, expect, it } from 'vitest'
import { formatPaise, toPaise, transactionLabel } from './format'

describe('financial amount formatting', () => {
  it('formats integer paise without losing large integer precision', () => {
    expect(formatPaise('9007199254740993')).toBe('₹9,00,71,99,25,47,409.93')
    expect(formatPaise('-125')).toBe('−₹1.25')
  })

  it('converts rupees to safe integer paise', () => {
    expect(toPaise('12.3')).toBe(1230)
    expect(() => toPaise('90071992547409.93')).toThrow('supported precision')
  })

  it('labels transactions as internal LedgerLine operations', () => {
    expect(transactionLabel('DEPOSIT')).toBe('Internal deposit')
    expect(transactionLabel('WITHDRAWAL')).toBe('Internal withdrawal')
    expect(transactionLabel('TRANSFER')).toBe('Internal transfer')
  })
})
