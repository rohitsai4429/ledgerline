import { ArrowUpRight, Eye, FileText } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Account, AccountStatus, User } from '../types/api'
import { formatDate, formatPaise } from '../utils/format'
import { EmptyState, StatusPill } from './ui'

const availableStatuses: AccountStatus[] = ['ACTIVE', 'FROZEN', 'CLOSED']

export function AccountTable({
  accounts,
  user,
  onStatusChange,
  onViewDetails,
  updatingAccountId,
}: {
  accounts: Account[]
  user: User
  onStatusChange?: (account: Account, status: AccountStatus) => void
  onViewDetails?: (account: Account) => void
  updatingAccountId?: string
}) {
  if (accounts.length === 0) {
    return <EmptyState title="No accounts to show" description="Accounts returned by LedgerLine will appear here." />
  }
  return (
    <div className="table-scroll">
      <table className="data-table account-table">
        <thead>
          <tr>
            <th>Account</th>
            {user.role !== 'ACCOUNT_HOLDER' && <th>Owner</th>}
            <th>Status</th>
            <th>Opened</th>
            <th className="align-right">Ledger balance</th>
            {onViewDetails && <th>Details</th>}
            {onStatusChange && <th>Manage</th>}
            {!onStatusChange && <th><span className="sr-only">View statement</span></th>}
          </tr>
        </thead>
        <tbody>
          {accounts.map((account) => (
            <tr key={account.id}>
              <td>
                <div className="account-cell">
                  <span className="account-mark"><FileText size={17} /></span>
                  <span>
                    <strong>{account.account_number}</strong>
                    <small>Customer account</small>
                  </span>
                </div>
              </td>
              {user.role !== 'ACCOUNT_HOLDER' && (
                <td className="muted-cell">{account.owner_user_id.slice(0, 8)}…</td>
              )}
              <td><StatusPill status={account.status} /></td>
              <td className="date-cell">{formatDate(account.created_at)}</td>
              <td className="align-right amount-cell">{formatPaise(account.balance_paise)}</td>
              {onViewDetails && (
                <td>
                  <button className="text-action account-detail-action" onClick={() => onViewDetails(account)}>
                    <Eye size={14} /> View
                  </button>
                </td>
              )}
              {onStatusChange ? (
                <td>
                  <select
                    className="status-select"
                    aria-label={`Set status for ${account.account_number}`}
                    value={account.status}
                    disabled={updatingAccountId === account.id}
                    onChange={(event) => onStatusChange(account, event.target.value as AccountStatus)}
                  >
                    {(account.status === 'CLOSED' ? ['CLOSED'] : availableStatuses).map((status) => (
                      <option key={status} value={status}>{status}</option>
                    ))}
                  </select>
                </td>
              ) : (
                <td className="action-cell">
                  <StatementLink accountId={account.id} />
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function StatementLink({ accountId }: { accountId: string }) {
  return (
    <Link className="icon-link" to={`/statements/${accountId}`} aria-label="View account statement">
      <ArrowUpRight size={16} />
    </Link>
  )
}
