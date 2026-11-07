import { request } from './client'
import type { AccountStatement } from '../types/api'

export const statementsApi = {
  get: (accountId: string, start?: string, end?: string) => {
    const params = new URLSearchParams()
    if (start) params.set('start', start)
    if (end) params.set('end', end)
    const query = params.size > 0 ? `?${params.toString()}` : ''
    return request<AccountStatement>(`/api/v1/accounts/${accountId}/statement${query}`)
  },
}
