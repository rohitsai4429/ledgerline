import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { accountsApi } from '../api/accounts'
import { ApiError } from '../api/client'
import { transactionsApi } from '../api/transactions'
import { useAuth } from '../auth/AuthContext'
import type { Account, Transaction } from '../types/api'
import { MoneyActionPage } from './MoneyActionPage'

vi.mock('../api/accounts', () => ({
  accountsApi: { list: vi.fn(), lookupRecipient: vi.fn() },
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

const recipient: Account = {
  ...account,
  id: '39fb2c4a-0d2b-4c7e-8590-6c8c625329a4',
  account_number: 'LL0000000002',
}

const transfer: Transaction = {
  ...transaction,
  id: '6a583454-2708-4f70-ae89-f619e24cd710',
  transaction_type: 'TRANSFER',
  amount_paise: '1250',
  source_account_id: account.id,
  destination_account_id: recipient.id,
}

function renderAction(action: 'DEPOSIT' | 'TRANSFER' = 'DEPOSIT') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MoneyActionPage action={action} />
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
    startGoogleSignIn: vi.fn(),
    verifyOtp: vi.fn(),
    signOut: vi.fn(),
  })
  vi.mocked(accountsApi.list).mockResolvedValue([account])
  vi.mocked(accountsApi.lookupRecipient).mockResolvedValue({
    destination_account_id: recipient.id,
    masked_account_number: '********0002',
    status: 'ACTIVE',
  })
  vi.mocked(transactionsApi.deposit).mockResolvedValue(transaction)
  vi.mocked(transactionsApi.transfer).mockResolvedValue(transfer)
})

describe('money movement form', () => {
  it('submits paise using an idempotency key and shows the API result', async () => {
    renderAction()
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

  it('verifies an account number and posts the resolved customer account id', async () => {
    renderAction('TRANSFER')
    await screen.findByRole('option', { name: /LL0000000001/ })
    fireEvent.change(screen.getByLabelText('From account'), { target: { value: account.id } })
    fireEvent.change(screen.getByLabelText('Recipient account number'), { target: { value: recipient.account_number } })
    fireEvent.click(screen.getByRole('button', { name: 'Verify recipient' }))

    expect(await screen.findByText(/Recipient verified · \*{8}0002/)).toBeInTheDocument()
    expect(vi.mocked(accountsApi.lookupRecipient).mock.calls[0][0]).toEqual({
      account_number: recipient.account_number,
    })
    fireEvent.change(screen.getByLabelText(/^Amount/), { target: { value: '12.50' } })
    fireEvent.click(screen.getByRole('button', { name: /review internal transaction/i }))

    expect(await screen.findByRole('dialog', { name: 'Internal transfer' })).toBeInTheDocument()
    expect(screen.getByText('********0002')).toBeInTheDocument()
    expect(screen.queryByText(recipient.id)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /confirm internal transfer/i }))

    await waitFor(() => expect(transactionsApi.transfer).toHaveBeenCalledWith(
      {
        source_account_id: account.id,
        destination_account_id: recipient.id,
        amount_paise: 1250,
      },
      expect.any(String),
    ))
    expect(await screen.findByText('Transfer completed successfully.')).toBeInTheDocument()
  })

  it('shows an invalid recipient error and prevents review', async () => {
    vi.mocked(accountsApi.lookupRecipient).mockRejectedValue(
      new ApiError('Recipient account not found or unavailable', 404),
    )
    renderAction('TRANSFER')
    await screen.findByRole('option', { name: /LL0000000001/ })
    fireEvent.change(screen.getByLabelText('Recipient account number'), { target: { value: recipient.account_number } })
    fireEvent.click(screen.getByRole('button', { name: 'Verify recipient' }))

    expect(await screen.findByText('Recipient account not found or unavailable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /review internal transaction/i })).toBeDisabled()
  })

  it('clears recipient verification as soon as the account number changes', async () => {
    renderAction('TRANSFER')
    await screen.findByRole('option', { name: /LL0000000001/ })
    const recipientInput = screen.getByLabelText('Recipient account number')
    fireEvent.change(recipientInput, { target: { value: recipient.account_number } })
    fireEvent.click(screen.getByRole('button', { name: 'Verify recipient' }))
    expect(await screen.findByText(/Recipient verified · \*{8}0002/)).toBeInTheDocument()

    fireEvent.change(recipientInput, { target: { value: 'LL0000000003' } })

    expect(screen.queryByText(/Recipient verified/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /review internal transaction/i })).toBeDisabled()
  })

  it('reuses the same idempotency key after an uncertain transfer failure and shows refreshed balances', async () => {
    vi.mocked(accountsApi.list)
      .mockResolvedValueOnce([account])
      .mockResolvedValue([{
        ...account,
        balance_paise: '23750',
      }])
    vi.mocked(transactionsApi.transfer)
      .mockRejectedValueOnce(new Error('network unavailable'))
      .mockResolvedValueOnce(transfer)
    renderAction('TRANSFER')
    await screen.findByRole('option', { name: /LL0000000001/ })
    fireEvent.change(screen.getByLabelText('From account'), { target: { value: account.id } })
    fireEvent.change(screen.getByLabelText('Recipient account number'), { target: { value: recipient.account_number } })
    fireEvent.click(screen.getByRole('button', { name: 'Verify recipient' }))
    await screen.findByText(/Recipient verified · \*{8}0002/)
    fireEvent.change(screen.getByLabelText(/^Amount/), { target: { value: '12.50' } })
    fireEvent.click(screen.getByRole('button', { name: /review internal transaction/i }))
    fireEvent.click(await screen.findByRole('button', { name: /confirm internal transfer/i }))
    expect(await screen.findByText('network unavailable')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /confirm internal transfer/i }))

    await waitFor(() => expect(transactionsApi.transfer).toHaveBeenCalledTimes(2))
    const calls = vi.mocked(transactionsApi.transfer).mock.calls
    expect(calls[0][0]).toEqual({
      source_account_id: account.id,
      destination_account_id: recipient.id,
      amount_paise: 1250,
    })
    expect(calls[1][0]).toEqual(calls[0][0])
    expect(calls[1][1]).toBe(calls[0][1])
    expect(await screen.findByText('Transfer completed successfully.')).toBeInTheDocument()
    expect(await screen.findByText('₹237.50')).toBeInTheDocument()
    expect(sessionStorage.length).toBe(0)
  })
})
