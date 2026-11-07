import { useState } from 'react'
import { FileDown, FileText } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Alert, Card, EmptyState, Loading, PageHeader, StatusPill } from '../components/ui'
import { useAccounts, useStatement } from '../hooks/useLedgerData'
import type { EntryType } from '../types/api'
import { formatDate, formatPaise, transactionLabel } from '../utils/format'

export function StatementsPage() {
  const { accountId: routeAccountId } = useParams()
  const { user } = useAuth()
  const accounts = useAccounts()
  const [selectedAccountId, setSelectedAccountId] = useState('')
  const accountId = routeAccountId ?? selectedAccountId
  const [dateRange, setDateRange] = useState({ start: '', end: '' })
  const [appliedRange, setAppliedRange] = useState({ start: '', end: '' })

  const statement = useStatement(
    accountId,
    appliedRange.start || undefined,
    appliedRange.end || undefined,
  )
  const selectedAccount = accounts.data?.find((account) => account.id === accountId)

  function applyDateFilter(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setAppliedRange({
      start: dateRange.start ? new Date(dateRange.start).toISOString() : '',
      end: dateRange.end ? new Date(dateRange.end).toISOString() : '',
    })
  }

  return (
    <>
      <PageHeader
        eyebrow="ACCOUNT ACTIVITY"
        title="Statements"
        description="Review internal account ledger activity and running balances from posted entries."
      />
      <Card className="statement-filter-card">
        <label className="form-field statement-account-select">
          <span>Account</span>
          <select value={accountId} onChange={(event) => setSelectedAccountId(event.target.value)}>
            <option value="">Select an account</option>
            {(accounts.data ?? []).map((account) => (
              <option key={account.id} value={account.id}>{account.account_number} · {formatPaise(account.balance_paise)}</option>
            ))}
          </select>
        </label>
        <form className="statement-date-filter" onSubmit={applyDateFilter}>
          <label className="form-field">
            <span>From</span>
            <input type="datetime-local" value={dateRange.start} onChange={(event) => setDateRange({ ...dateRange, start: event.target.value })} />
          </label>
          <label className="form-field">
            <span>Through</span>
            <input type="datetime-local" value={dateRange.end} onChange={(event) => setDateRange({ ...dateRange, end: event.target.value })} />
          </label>
          <button type="submit" className="button button-secondary">Apply dates</button>
        </form>
      </Card>

      {accounts.isLoading && <Loading label="Loading accounts" />}
      {accounts.isError && <Alert>{accounts.error instanceof ApiError ? accounts.error.message : 'Account list could not be loaded from LedgerLine.'}</Alert>}
      {user?.role === 'AUDITOR' && (
        <Alert tone="info">
          Auditor access is read-only. Statements show this account’s actual debit and credit entries; the current API does not expose a journal-wide raw-entry endpoint.
        </Alert>
      )}
      {!accountId && !accounts.isLoading && (
        <Card className="table-card"><EmptyState title="Choose an account" description="Select an account to retrieve its statement." /></Card>
      )}
      {accountId && statement.isLoading && <Loading label="Loading account statement" />}
      {accountId && statement.isError && (
        <Alert>{statement.error instanceof ApiError ? statement.error.message : user?.role === 'ACCOUNT_HOLDER' ? 'The account may not belong to your profile, or the statement could not be loaded.' : 'The statement could not be loaded.'}</Alert>
      )}
      {statement.data && selectedAccount && (
        <>
          <div className="statement-summary">
            <Card className="statement-account-card">
              <span className="account-mark"><FileText size={17} /></span>
              <div><small>ACCOUNT</small><strong>{selectedAccount.account_number}</strong></div>
              <StatusPill status={selectedAccount.status} />
            </Card>
            <Card className="statement-balance-card">
              <span>Opening balance</span><strong>{formatPaise(statement.data.opening_balance_paise)}</strong>
            </Card>
            <Card className="statement-balance-card">
              <span>Closing balance</span><strong>{formatPaise(statement.data.closing_balance_paise)}</strong>
            </Card>
          </div>
          <Card className="table-card">
            <div className="section-heading">
              <div><h2>Ledger activity</h2><p>{statement.data.entries.length} entries · {statement.data.currency}</p></div>
              <span className="statement-source"><FileDown size={15} /> Live API statement</span>
            </div>
            {statement.data.entries.length === 0 ? (
              <EmptyState title="No ledger entries in this range" description="The statement returned no activity for the selected period." />
            ) : (
              <div className="table-scroll">
                <table className="data-table statement-table">
                  <thead><tr><th>Date & time</th><th>Transaction</th><th>Transaction reference</th><th>Related reference</th><th>Entry</th><th className="align-right">Amount</th><th className="align-right">Running balance</th></tr></thead>
                  <tbody>
                    {statement.data.entries.map((entry) => (
                      <tr key={`${entry.transaction_id}-${entry.entry_type}`}>
                        <td className="date-cell">{formatDate(entry.created_at)}</td>
                        <td><strong>{transactionLabel(entry.transaction_type)}</strong></td>
                        <td className="mono muted-cell" title={entry.transaction_id}>{entry.transaction_id}</td>
                        <td className="mono muted-cell" title={entry.related_transaction_id ?? undefined}>{entry.related_transaction_id ?? '—'}</td>
                        <td><EntryTypePill type={entry.entry_type} /></td>
                        <td className={`align-right amount-cell ${entry.entry_type === 'CREDIT' ? 'positive-amount' : 'negative-amount'}`}>
                          {entry.entry_type === 'CREDIT' ? '+' : '−'}{formatPaise(entry.amount_paise)}
                        </td>
                        <td className="align-right amount-cell">{formatPaise(entry.balance_after_paise)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </>
  )
}

function EntryTypePill({ type }: { type: EntryType }) {
  return <span className={`entry-type entry-${type.toLowerCase()}`}>{type}</span>
}
