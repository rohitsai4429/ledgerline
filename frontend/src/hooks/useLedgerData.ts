import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { accountsApi } from '../api/accounts'
import { adminApi } from '../api/admin'
import { auditApi, type AuditQuery } from '../api/audit'
import { statementsApi } from '../api/statements'
import { transactionsApi, type TransactionQuery } from '../api/transactions'
import type { AccountStatus } from '../types/api'

export const ledgerKeys = {
  accounts: ['accounts'] as const,
  transactions: (query: TransactionQuery = {}) => ['transactions', query] as const,
  audit: (query: AuditQuery = {}) => ['audit', query] as const,
  statement: (accountId: string) => ['statement', accountId] as const,
}

export function useAccounts() {
  return useQuery({
    queryKey: ledgerKeys.accounts,
    queryFn: accountsApi.list,
  })
}

export function useAccount(accountId: string) {
  return useQuery({
    queryKey: ['account', accountId],
    queryFn: () => accountsApi.get(accountId),
    enabled: Boolean(accountId),
  })
}

export function useTransactions(query: TransactionQuery = {}) {
  return useQuery({
    queryKey: ledgerKeys.transactions(query),
    queryFn: () => transactionsApi.list(query),
  })
}

export function useAuditEvents(query: AuditQuery = {}, enabled = true) {
  return useQuery({
    queryKey: ledgerKeys.audit(query),
    queryFn: () => auditApi.list(query),
    enabled,
  })
}

export function useStatement(accountId: string, start?: string, end?: string) {
  return useQuery({
    queryKey: [...ledgerKeys.statement(accountId), start, end],
    queryFn: () => statementsApi.get(accountId, start, end),
    enabled: Boolean(accountId),
  })
}

export function useCreateAccount() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: accountsApi.create,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ledgerKeys.accounts })
      void queryClient.invalidateQueries({ queryKey: ['account'] })
    },
  })
}

export function useUpdateAccountStatus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ accountId, status }: { accountId: string; status: AccountStatus }) =>
      adminApi.setAccountStatus(accountId, status),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ledgerKeys.accounts })
      void queryClient.invalidateQueries({ queryKey: ['account'] })
    },
  })
}

export function useInvalidateLedger() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    void queryClient.invalidateQueries({ queryKey: ['transactions'] })
    void queryClient.invalidateQueries({ queryKey: ['statement'] })
    void queryClient.invalidateQueries({ queryKey: ['audit'] })
  }
}
