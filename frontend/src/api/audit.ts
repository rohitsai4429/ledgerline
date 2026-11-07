import { request } from './client'
import type { AuditEvent } from '../types/api'

export interface AuditQuery {
  actor_user_id?: string
  start?: string
  limit?: number
  offset?: number
}

export const auditApi = {
  list: (query: AuditQuery = {}) => {
    const params = new URLSearchParams()
    if (query.actor_user_id) params.set('actor_user_id', query.actor_user_id)
    if (query.start) params.set('start', query.start)
    params.set('limit', String(query.limit ?? 100))
    params.set('offset', String(query.offset ?? 0))
    return request<AuditEvent[]>(`/api/v1/audit-events?${params.toString()}`)
  },
}
