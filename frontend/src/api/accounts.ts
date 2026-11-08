import { request } from './client'
import type { Account, AccountStatus } from '../types/api'

export interface RecipientLookupPayload {
  account_number: string
}

export interface RecipientLookupResponse {
  destination_account_id: string
  masked_account_number: string
  status: AccountStatus
}

export const accountsApi = {
  list: () => request<Account[]>('/api/v1/accounts'),
  get: (accountId: string) => request<Account>(`/api/v1/accounts/${accountId}`),
  lookupRecipient: (payload: RecipientLookupPayload) =>
    request<RecipientLookupResponse>('/api/v1/accounts/recipient-lookup', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
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
