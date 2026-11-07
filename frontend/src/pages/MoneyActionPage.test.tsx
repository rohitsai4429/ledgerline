import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { accountsApi } from '../api/accounts'
import { transactionsApi } from '../api/transactions'
import { useAuth } from '../auth/AuthContext'
import type { Account, Transaction } from '../types/api'
import { MoneyActionPage } from './MoneyActionPage'

vi.mock('../api/accounts', () => ({
  accountsApi: { list: vi.fn() },
}))
vi.mock('../api/transactions', () => ({
  transactionsApi: {
    deposit: vi.fn(),
    withdraw: vi.fn(),
    transfer: vi.fn(),
    reverse: vi.fn(),
    list: vi.fn(),
  },
}))
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

const transaction: Transaction = {
  id: '77ea3707-6d3e-4e8a-b860-32267e876e57',
  transaction_type: 'DEPOSIT',
  status: 'POSTED',
  amount_paise: '1250',
  currency: 'INR',
  source_account_id: null,
  destination_account_id: account.id,
  related_transaction_id: null,
  created_at: '2026-01-01T00:00:00Z',
}

function renderDeposit() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MoneyActionPage action="DEPOSIT" />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  sessionStorage.clear()
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
    signOut: vi.fn(),
  })
  vi.mocked(accountsApi.list).mockResolvedValue([account])
  vi.mocked(transactionsApi.deposit).mockResolvedValue(transaction)
})

describe('money movement form', () => {
  it('submits paise using an idempotency key and shows the API result', async () => {
    renderDeposit()
    await screen.findByRole('option', { name: /LL0000000001/ })
    fireEvent.change(screen.getByLabelText('Account'), { target: { value: account.id } })
    fireEvent.change(screen.getByLabelText(/^Amount/), { target: { value: '12.50' } })
    fireEvent.click(screen.getByRole('button', { name: /review internal transaction/i }))

    expect(await screen.findByRole('dialog', { name: 'Internal deposit' })).toBeInTheDocument()
    expect(transactionsApi.deposit).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /confirm internal deposit/i }))

    await waitFor(() => expect(transactionsApi.deposit).toHaveBeenCalledWith(
      { account_id: account.id, amount_paise: 1250 },
      expect.any(String),
    ))
    expect(await screen.findByText(/Internal deposit posted/)).toBeInTheDocument()
    expect(sessionStorage.length).toBe(0)
  })
})
