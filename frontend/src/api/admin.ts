import { request } from './client'
import type { Account, AccountStatus, Transaction } from '../types/api'

export const adminApi = {
  setAccountStatus: (accountId: string, status: AccountStatus) =>
    request<Account>(`/api/v1/accounts/${accountId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  reverseTransaction: (transactionId: string, key: string) =>
    request<Transaction>(`/api/v1/transactions/${transactionId}/reverse`, {
      method: 'POST',
      headers: { 'Idempotency-Key': key },
      body: JSON.stringify({}),
    }),
}
