import { useMemo, useState } from 'react'
import { AlertTriangle, Search, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import { AccountTable } from '../components/AccountTable'
import { Alert, Button, Card, EmptyState, Loading, PageHeader, StatusPill } from '../components/ui'
import { useAccount, useAccounts, useUpdateAccountStatus } from '../hooks/useLedgerData'
import type { Account, AccountStatus } from '../types/api'
import { formatDate, formatPaise } from '../utils/format'

export function AdminAccountsPage() {
  const { user } = useAuth()
  const accounts = useAccounts()
  const statusChange = useUpdateAccountStatus()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<AccountStatus | 'ALL'>('ALL')
  const [selectedAccountId, setSelectedAccountId] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const selectedAccount = useAccount(selectedAccountId)
  const filteredAccounts = useMemo(() => {
    const query = search.trim().toLowerCase()
    return (accounts.data ?? []).filter((account) => {
      const matchesQuery = !query || [
        account.account_number,
        account.id,
        account.owner_user_id,
      ].some((value) => value.toLowerCase().includes(query))
      return matchesQuery && (statusFilter === 'ALL' || account.status === statusFilter)
    })
  }, [accounts.data, search, statusFilter])

  async function changeStatus(account: Account, status: AccountStatus) {
    if (status === account.status) return
    const action = status === 'CLOSED' ? 'close' : status === 'FROZEN' ? 'freeze' : 'activate'
    const irreversible = status === 'CLOSED' ? ' Closed accounts cannot be reopened.' : ''
    if (!window.confirm(`Confirm ${action} for account ${account.account_number}?${irreversible}`)) {
      return
    }
    setError('')
    setMessage('')
    try {
      const updated = await statusChange.mutateAsync({ accountId: account.id, status })
      setMessage(`${updated.account_number} is now ${updated.status.toLowerCase()}.`)
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : 'Account status could not be updated.')
    }
  }

  return (
    <>
      <PageHeader eyebrow="OPERATIONS CONTROL" title="Account management" description="Review account records and update permitted account statuses." />
      {message && <Alert tone="success">{message}</Alert>}
      {error && <Alert>{error}</Alert>}
      {accounts.isLoading ? <Loading label="Loading customer accounts" /> : accounts.isError ? (
        <Alert>{accounts.error instanceof ApiError ? accounts.error.message : 'Customer accounts could not be loaded.'}</Alert>
      ) : (
        <Card className="table-card">
          <div className="section-heading">
            <div><h2>Customer accounts</h2><p>{filteredAccounts.length} of {accounts.data?.length ?? 0} API accounts</p></div>
            <span className="admin-key"><ShieldCheck size={15} /> ADMIN CONTROLS</span>
          </div>
          <div className="table-toolbar account-search-toolbar">
            <label className="filter-field">
              <span>Search account number, account ID, or owner ID</span>
              <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search customer accounts" />
            </label>
            <label className="filter-field">
              <span>Filter by status</span>
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as AccountStatus | 'ALL')}>
                <option value="ALL">All statuses</option>
                <option value="ACTIVE">Active</option>
                <option value="FROZEN">Frozen</option>
                <option value="CLOSED">Closed</option>
              </select>
            </label>
            <Search size={16} aria-hidden="true" />
          </div>
          {user && filteredAccounts.length > 0 && (
            <AccountTable
              accounts={filteredAccounts}
              user={user}
              onStatusChange={changeStatus}
              onViewDetails={(account) => setSelectedAccountId(account.id)}
              updatingAccountId={statusChange.isPending ? statusChange.variables?.accountId : undefined}
            />
          )}
          {filteredAccounts.length === 0 && (
            <EmptyState
              title={(accounts.data?.length ?? 0) === 0 ? 'No customer accounts' : 'No matching accounts'}
              description={(accounts.data?.length ?? 0) === 0 ? 'Customer accounts will appear here when returned by the API.' : 'Change the search or status filter to see other accounts.'}
            />
          )}
        </Card>
      )}
      {selectedAccountId && (
        <Card className="account-details-card">
          <div className="section-heading">
            <div><h2>Account details</h2><p>Account information returned by the detail API.</p></div>
            <Button variant="quiet" onClick={() => setSelectedAccountId('')}>Close details</Button>
          </div>
          {selectedAccount.isLoading ? <Loading label="Loading account details" /> : selectedAccount.isError ? (
            <Alert>{selectedAccount.error instanceof ApiError ? selectedAccount.error.message : 'Account details could not be loaded.'}</Alert>
          ) : selectedAccount.data ? (
            <dl className="account-detail-grid">
              <div><dt>Account number</dt><dd>{selectedAccount.data.account_number}</dd></div>
              <div><dt>Account ID</dt><dd className="mono">{selectedAccount.data.id}</dd></div>
              <div><dt>Owner user ID</dt><dd className="mono">{selectedAccount.data.owner_user_id}</dd></div>
              <div><dt>Ledger account ID</dt><dd className="mono">{selectedAccount.data.ledger_account_id}</dd></div>
              <div><dt>Status</dt><dd><StatusPill status={selectedAccount.data.status} /></dd></div>
              <div><dt>Internal ledger balance</dt><dd>{formatPaise(selectedAccount.data.balance_paise)}</dd></div>
              <div><dt>Opened</dt><dd>{formatDate(selectedAccount.data.created_at)}</dd></div>
              <div><dt>Last updated</dt><dd>{formatDate(selectedAccount.data.updated_at)}</dd></div>
              <div className="account-detail-link"><dt>Statement</dt><dd><Link className="inline-link" to={`/statements/${selectedAccount.data.id}`}>View account statement</Link></dd></div>
            </dl>
          ) : null}
        </Card>
      )}
      <div className="notice-strip"><span className="notice-mark"><AlertTriangle size={15} /></span><p>Closing is irreversible. Balances are never directly editable; account status changes must be authorized by the backend.</p></div>
    </>
  )
}
