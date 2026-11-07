import type { ApiErrorBody } from '../types/api'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')
export const SESSION_EXPIRED_EVENT = 'ledgerline:session-expired'

let accessToken: string | null = null
let tokenExpiresAt = 0

export function setAccessToken(token: string | null, expiresInSeconds = 0): void {
  accessToken = token
  tokenExpiresAt = token ? Date.now() + expiresInSeconds * 1000 : 0
}

export function getAccessToken(): string | null {
  if (accessToken && Date.now() >= tokenExpiresAt) {
    setAccessToken(null)
  }
  return accessToken
}

export class ApiError extends Error {
  readonly status: number

  constructor(
    message: string,
    status: number,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers)
  const token = getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      headers,
      credentials: 'omit',
    })
  } catch {
    throw new ApiError('Unable to reach LedgerLine. Check your connection and try again.', 0)
  }

  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = (await response.json()) as ApiErrorBody
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) {
        message = body.detail.map((issue) => issue.msg).filter(Boolean).join('. ') || message
      }
    } catch {
      // Keep the HTTP status message when an error body is empty or non-JSON.
    }
    if (response.status === 401) {
      setAccessToken(null)
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
    }
    throw new ApiError(message, response.status)
  }

  if (response.status === 204) return undefined as T
  const body = await response.text()
  const exactPaise = body.replace(
    /("(?:balance_paise|amount_paise|opening_balance_paise|closing_balance_paise|balance_after_paise)"\s*:\s*)(-?\d+)(?=\s*[,}\]])/g,
    '$1"$2"',
  )
  return JSON.parse(exactPaise) as T
}

export function apiUrl(): string {
  return apiBaseUrl
}
