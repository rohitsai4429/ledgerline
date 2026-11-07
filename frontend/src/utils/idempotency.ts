import { ApiError } from '../api/client'

interface PendingOperation {
  key: string
  payload: string
}

function slotKey(userId: string, operation: string): string {
  return `ledgerline.pending.${userId}.${operation}`
}

export async function executeIdempotently<T>(
  userId: string,
  operation: string,
  payload: unknown,
  send: (key: string) => Promise<T>,
): Promise<T> {
  const storageKey = slotKey(userId, operation)
  const serializedPayload = JSON.stringify(payload)
  let pending: PendingOperation | null = null
  const stored = sessionStorage.getItem(storageKey)
  if (stored) {
    try {
      pending = JSON.parse(stored) as PendingOperation
    } catch {
      sessionStorage.removeItem(storageKey)
    }
  }

  if (pending && pending.payload !== serializedPayload) {
    throw new Error(
      'A previous request has an unknown outcome. Retry it with the same details before starting another.',
    )
  }

  const key = pending?.key ?? crypto.randomUUID()
  if (!pending) {
    sessionStorage.setItem(storageKey, JSON.stringify({ key, payload: serializedPayload }))
  }

  try {
    const result = await send(key)
    sessionStorage.removeItem(storageKey)
    return result
  } catch (error) {
    if (error instanceof ApiError && error.status > 0 && error.status < 500) {
      sessionStorage.removeItem(storageKey)
    }
    throw error
  }
}
