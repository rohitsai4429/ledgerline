import { useState } from 'react'
import { Plus, RefreshCw } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { AccountTable } from '../components/AccountTable'
import { Alert, Button, Card, Loading, PageHeader } from '../components/ui'
import { useAccounts, useCreateAccount } from '../hooks/useLedgerData'
import { ApiError } from '../api/client'

export function AccountsPage() {
  const { user } = useAuth()
  const accounts = useAccounts()
  const createAccount = useCreateAccount()
  const [createdAccount, setCreatedAccount] = useState('')

  async function create() {
    setCreatedAccount('')
    try {
      const account = await createAccount.mutateAsync()
      setCreatedAccount(account.account_number)
    } catch {
      // Mutation error is rendered below with its message.
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="YOUR MONEY, ORGANIZED"
        title="My accounts"
        description="Review account status and internal LedgerLine balances."
        action={
          <Button onClick={create} disabled={createAccount.isPending}>
            {createAccount.isPending ? <RefreshCw className="spin" size={16} /> : <Plus size={17} />}
            Open account
          </Button>
        }
      />
      {createdAccount && <Alert tone="success">Account {createdAccount} was created with the API’s initial balance.</Alert>}
      {createAccount.isError && <Alert>{createAccount.error instanceof ApiError ? createAccount.error.message : 'Account creation failed.'}</Alert>}
      {accounts.isLoading ? <Loading label="Loading your accounts" /> : accounts.isError ? (
        <Alert>Accounts could not be loaded. Please retry the request.</Alert>
      ) : (
        <Card className="table-card">
          <div className="section-heading">
            <div><h2>Account portfolio</h2><p>{accounts.data?.length ?? 0} accounts returned</p></div>
          </div>
          {user && <AccountTable accounts={accounts.data ?? []} user={user} />}
        </Card>
      )}
      <div className="notice-strip"><span className="notice-mark">i</span><p>Balances are internal ledger values returned by the service. They are not bank or payment-provider balances; only posted financial transactions change them.</p></div>
    </>
  )
}
