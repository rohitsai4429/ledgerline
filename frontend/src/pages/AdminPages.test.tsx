import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { accountsApi } from '../api/accounts'
import { useAuth } from '../auth/AuthContext'
import type { Account } from '../types/api'
import { AdminAccountsPage } from './AdminPages'

vi.mock('../api/accounts', () => ({
  accountsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn() },
}))
vi.mock('../api/admin', () => ({
  adminApi: { setAccountStatus: vi.fn(), reverseTransaction: vi.fn() },
}))
vi.mock('../auth/AuthContext', () => ({ useAuth: vi.fn() }))

const accounts: Account[] = [
  {
    id: '7d7506dd-9615-4311-8c8a-73000ccda772',
    account_number: 'LL0000000001',
    owner_user_id: 'a0b8b31e-6439-4adf-9940-f9730d769c65',
    balance_paise: '25000',
    status: 'ACTIVE',
    ledger_account_id: '6a6e0302-ef7d-4c9b-a61f-cfd5097e4c15',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: '8e8617ee-0726-4422-9d9b-84111dde8883',
    account_number: 'LL0000000002',
    owner_user_id: 'b1c9c42f-754a-5be0-a15f-08410e87d76a',
    balance_paise: '0',
    status: 'FROZEN',
    ledger_account_id: '7b7f1413-0f8e-5db0-b72d-d02f009e5d26',
    created_at: '2026-01-02T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
  },
]

function renderAdminAccounts() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AdminAccountsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.mocked(useAuth).mockReturnValue({
    user: {
      id: 'admin-id',
      email: 'admin@example.com',
      role: 'ADMIN',
      status: 'ACTIVE',
      created_at: '2026-01-01T00:00:00Z',
    },
    busy: false,
    signIn: vi.fn(),
    signOut: vi.fn(),
  })
  vi.mocked(accountsApi.list).mockResolvedValue(accounts)
  vi.mocked(accountsApi.get).mockImplementation(async (id) => {
    const account = accounts.find((item) => item.id === id)
    if (!account) throw new Error('Account not found')
    return account
  })
})

describe('administrator account management', () => {
  it('searches and filters the API account list without editing balances', async () => {
    renderAdminAccounts()
    expect(await screen.findByText('LL0000000001')).toBeInTheDocument()
    expect(screen.getByText('LL0000000002')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Search account number, account ID, or owner ID'), {
      target: { value: 'LL0000000001' },
    })
    expect(screen.getByText('LL0000000001')).toBeInTheDocument()
    expect(screen.queryByText('LL0000000002')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Filter by status'), { target: { value: 'FROZEN' } })
    expect(screen.getByText('No matching accounts')).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: /balance/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /edit balance/i })).not.toBeInTheDocument()
  })

  it('loads selected account details from the account detail API', async () => {
    renderAdminAccounts()
    await screen.findByText('LL0000000001')
    fireEvent.click(screen.getAllByRole('button', { name: /view/i })[0])

    expect(await screen.findByText('Account details')).toBeInTheDocument()
    expect(await screen.findByText(accounts[0].id)).toBeInTheDocument()
    expect(screen.getAllByText('₹250.00')).toHaveLength(2)
    expect(accountsApi.get).toHaveBeenCalledWith(accounts[0].id)
  })
})
