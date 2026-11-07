import { afterEach, describe, expect, it, vi } from 'vitest'
import { getAccessToken, request, SESSION_EXPIRED_EVENT, setAccessToken } from './client'

afterEach(() => {
  setAccessToken(null)
  vi.unstubAllGlobals()
})

describe('API client', () => {
  it('preserves paise values beyond JavaScript safe integer precision', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('{"amount_paise":9007199254740993,"balance_paise":9007199254740993}', {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    await expect(request<{ amount_paise: string; balance_paise: string }>('/account')).resolves.toEqual({
      amount_paise: '9007199254740993',
      balance_paise: '9007199254740993',
    })
  })

  it('attaches the in-memory bearer token and excludes cookies', async () => {
    setAccessToken('test-token', 60)
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('{"id":"user-id"}', { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await request('/profile')

    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(new Headers(options.headers).get('Authorization')).toBe('Bearer test-token')
    expect(options.credentials).toBe('omit')
  })

  it('surfaces the backend error detail and status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('{"detail":"Insufficient funds"}', { status: 409 }),
      ),
    )

    await expect(request('/transactions')).rejects.toMatchObject({
      message: 'Insufficient funds',
      status: 409,
    })
  })

  it('clears expired bearer credentials and signals the active session', async () => {
    setAccessToken('expired-token', 60)
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('{"detail":"Invalid or expired authentication credentials"}', { status: 401 }),
    )
    const onExpired = vi.fn()
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired)
    vi.stubGlobal('fetch', fetchMock)

    await expect(request('/profile')).rejects.toMatchObject({ status: 401 })

    expect(getAccessToken()).toBeNull()
    expect(onExpired).toHaveBeenCalledOnce()
    window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired)
  })
})
