import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { accountsApi } from '../api/accounts'
import { auditApi } from '../api/audit'
import { transactionsApi } from '../api/transactions'
import { useAuth } from '../auth/AuthContext'
import type { Account } from '../types/api'
import { DashboardPage } from './DashboardPage'

vi.mock('../api/accounts', () => ({ accountsApi: { list: vi.fn() } }))
vi.mock('../api/transactions', () => ({
  transactionsApi: {
    deposit: vi.fn(),
    withdraw: vi.fn(),
    transfer: vi.fn(),
    reverse: vi.fn(),
    list: vi.fn(),
  },
}))
vi.mock('../api/audit', () => ({ auditApi: { list: vi.fn() } }))
vi.mock('../auth/AuthContext', () => ({ useAuth: vi.fn() }))

const account: Account = {
  id: '7d7506dd-9615-4311-8c8a-73000ccda772',
  account_number: 'LL0000000001',
  owner_user_id: 'a0b8b31e-6439-4adf-9940-f9730d769c65',
  balance_paise: '25000',
  status: 'ACTIVE',
  ledger_account_id: '6a6e0302-ef7d-4c9b-a61f-cfd5097e4c15',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  vi.mocked(useAuth).mockReturnValue({
    user: {
      id: account.owner_user_id,
      email: 'holder@example.com',
      role: 'ACCOUNT_HOLDER',
      status: 'ACTIVE',
      created_at: account.created_at,
    },
    busy: false,
    signIn: vi.fn(),
    startGoogleSignIn: vi.fn(),
    verifyOtp: vi.fn(),
    signOut: vi.fn(),
  })
  vi.mocked(accountsApi.list).mockResolvedValue([account])
  vi.mocked(transactionsApi.list).mockResolvedValue([])
  vi.mocked(auditApi.list).mockResolvedValue([])
})

describe('role-aware dashboard', () => {
  it('shows only API-backed account data and avoids audit calls for holders', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <DashboardPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('Your financial overview')).toBeInTheDocument()
    expect(screen.getByText('₹250.00')).toBeInTheDocument()
    expect(screen.getByText('Activity will appear here')).toBeInTheDocument()
    expect(auditApi.list).not.toHaveBeenCalled()
  })
})
