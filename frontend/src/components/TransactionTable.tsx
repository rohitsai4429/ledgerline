import { ArrowDownLeft, ArrowLeftRight, ArrowUpRight, CornerUpLeft, Eye } from 'lucide-react'
import type { Account, Transaction } from '../types/api'
import { formatDate, formatPaise, transactionLabel } from '../utils/format'
import { EmptyState, StatusPill } from './ui'

function transactionIcon(type: Transaction['transaction_type']) {
  switch (type) {
    case 'DEPOSIT': return <ArrowDownLeft size={17} />
    case 'WITHDRAWAL': return <ArrowUpRight size={17} />
    case 'TRANSFER': return <ArrowLeftRight size={17} />
    case 'REVERSAL': return <CornerUpLeft size={17} />
  }
}

function accountReference(id: string | null, accounts: Account[]): string {
  if (!id) return 'Clearing account'
  return accounts.find((account) => account.id === id)?.account_number ?? 'Other LedgerLine account'
}

export function TransactionTable({
  transactions,
  accounts,
  onReverse,
  onViewDetails,
}: {
  transactions: Transaction[]
  accounts: Account[]
  onReverse?: (transaction: Transaction) => void
  onViewDetails?: (transaction: Transaction) => void
}) {
  if (transactions.length === 0) {
    return <EmptyState title="No activity yet" description="Posted account activity will appear here." />
  }
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>Transaction</th>
            <th>Reference</th>
            <th>Date & time</th>
            <th>Status</th>
            <th className="align-right">Amount</th>
            {(onReverse || onViewDetails) && <th><span className="sr-only">Actions</span></th>}
          </tr>
        </thead>
        <tbody>
          {transactions.map((transaction) => (
            <tr key={transaction.id}>
              <td>
                <div className="transaction-name">
                  <span className={`transaction-icon icon-${transaction.transaction_type.toLowerCase()}`}>
                    {transactionIcon(transaction.transaction_type)}
                  </span>
                  <span>
                    <strong>{transactionLabel(transaction.transaction_type)}</strong>
                    <small>{transaction.id.slice(0, 8).toUpperCase()}</small>
                  </span>
                </div>
              </td>
              <td className="muted-cell">
                {transaction.source_account_id
                  ? accountReference(transaction.source_account_id, accounts)
                  : 'Clearing'}{' '}
                <span className="reference-arrow">→</span>{' '}
                {transaction.destination_account_id
                  ? accountReference(transaction.destination_account_id, accounts)
                  : 'Clearing'}
              </td>
              <td className="date-cell">{formatDate(transaction.created_at)}</td>
              <td><StatusPill status={transaction.status} /></td>
              <td className="align-right amount-cell">{formatPaise(transaction.amount_paise)}</td>
              {(onReverse || onViewDetails) && (
                <td className="action-cell">
                  {onViewDetails && (
                    <button className="icon-link" aria-label={`View ${transactionLabel(transaction.transaction_type)} details`} onClick={() => onViewDetails(transaction)}>
                      <Eye size={16} />
                    </button>
                  )}
                  {transaction.transaction_type !== 'REVERSAL' && transaction.status === 'POSTED' && (
                    onReverse && <button className="text-action" onClick={() => onReverse(transaction)}>Reverse</button>
                  )}
                  {transaction.related_transaction_id && (
                    <span className="reversal-ref" title={`Original ${transaction.related_transaction_id}`}>
                      Original {transaction.related_transaction_id.slice(0, 8)}
                    </span>
                  )}
                  {transactions.some((related) => related.related_transaction_id === transaction.id) && (
                    <span className="reversal-ref">Reversal posted</span>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
