import { beforeEach, describe, expect, it, vi } from 'vitest'
import { executeIdempotently } from './idempotency'

beforeEach(() => {
  sessionStorage.clear()
  vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'stable-operation-key') })
})

describe('financial request idempotency', () => {
  it('reuses the same key and payload after an ambiguous failure', async () => {
    const send = vi.fn()
      .mockRejectedValueOnce(new Error('network unavailable'))
      .mockResolvedValueOnce({ id: 'transaction-1' })
    const payload = { account_id: 'account-1', amount_paise: 1250 }

    await expect(executeIdempotently('user-1', 'deposit', payload, send)).rejects.toThrow('network unavailable')
    await expect(executeIdempotently('user-1', 'deposit', payload, send)).resolves.toEqual({ id: 'transaction-1' })

    expect(send.mock.calls).toEqual([['stable-operation-key'], ['stable-operation-key']])
    expect(sessionStorage.length).toBe(0)
  })

  it('does not send a different payload while an earlier outcome is unknown', async () => {
    const send = vi.fn().mockRejectedValue(new Error('network unavailable'))
    await expect(executeIdempotently('user-1', 'deposit', { amount_paise: 100 }, send)).rejects.toThrow()

    await expect(
      executeIdempotently('user-1', 'deposit', { amount_paise: 200 }, send),
    ).rejects.toThrow('same details')
    expect(send).toHaveBeenCalledTimes(1)
  })
})
