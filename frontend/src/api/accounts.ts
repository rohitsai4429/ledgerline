import { request } from './client'
import type { Account, AccountStatus } from '../types/api'

export const accountsApi = {
  list: () => request<Account[]>('/api/v1/accounts'),
  get: (accountId: string) => request<Account>(`/api/v1/accounts/${accountId}`),
  create: () =>
    request<Account>('/api/v1/accounts', {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  setStatus: (accountId: string, status: AccountStatus) =>
    request<Account>(`/api/v1/accounts/${accountId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
}
