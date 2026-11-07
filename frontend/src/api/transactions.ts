import { request } from './client'
import type { Transaction } from '../types/api'

export interface DepositPayload {
  account_id: string
  amount_paise: number
}

export interface WithdrawalPayload extends DepositPayload {}

export interface TransferPayload {
  source_account_id: string
  destination_account_id: string
  amount_paise: number
}

export interface TransactionQuery {
  account_id?: string
  limit?: number
  offset?: number
}

function idempotencyHeaders(key: string): HeadersInit {
  return { 'Idempotency-Key': key }
}

export const transactionsApi = {
  deposit: (payload: DepositPayload, key: string) =>
    request<Transaction>('/api/v1/transactions/deposits', {
      method: 'POST',
      headers: idempotencyHeaders(key),
      body: JSON.stringify(payload),
    }),
  withdraw: (payload: WithdrawalPayload, key: string) =>
    request<Transaction>('/api/v1/transactions/withdrawals', {
      method: 'POST',
      headers: idempotencyHeaders(key),
      body: JSON.stringify(payload),
    }),
  transfer: (payload: TransferPayload, key: string) =>
    request<Transaction>('/api/v1/transactions/transfers', {
      method: 'POST',
      headers: idempotencyHeaders(key),
      body: JSON.stringify(payload),
    }),
  reverse: (transactionId: string, key: string) =>
    request<Transaction>(`/api/v1/transactions/${transactionId}/reverse`, {
      method: 'POST',
      headers: idempotencyHeaders(key),
      body: JSON.stringify({}),
    }),
  list: (query: TransactionQuery = {}) => {
    const params = new URLSearchParams()
    if (query.account_id) params.set('account_id', query.account_id)
    params.set('limit', String(query.limit ?? 100))
    params.set('offset', String(query.offset ?? 0))
    return request<Transaction[]>(`/api/v1/transactions?${params.toString()}`)
  },
}
