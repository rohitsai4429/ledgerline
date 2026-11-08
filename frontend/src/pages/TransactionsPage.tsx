import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { AlertTriangle, ChevronLeft, ChevronRight, RotateCcw, Search, X } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { adminApi } from '../api/admin'
import { ApiError } from '../api/client'
import { TransactionTable } from '../components/TransactionTable'
import { Alert, Button, Card, EmptyState, Loading, PageHeader, ProductDisclosure, StatusPill } from '../components/ui'
import { useAccounts, useInvalidateLedger, useTransactions } from '../hooks/useLedgerData'
import type { Transaction, TransactionType } from '../types/api'
import { executeIdempotently } from '../utils/idempotency'
import { formatDate, formatPaise, transactionLabel } from '../utils/format'

const PAGE_SIZE = 25

export function TransactionsPage() {
  const { user } = useAuth()
  const [accountId, setAccountId] = useState('')
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<TransactionType | 'ALL'>('ALL')
  const [offset, setOffset] = useState(0)
  const [selectedForReversal, setSelectedForReversal] = useState<Transaction | null>(null)
  const [selectedForDetails, setSelectedForDetails] = useState<Transaction | null>(null)
  const [reversalResult, setReversalResult] = useState<{ original: string; reversal: string } | null>(null)
  const [reversalError, setReversalError] = useState('')
  const dialogRef = useRef<HTMLElement | null>(null)
  const accounts = useAccounts()
  const transactions = useTransactions({ account_id: accountId || undefined, limit: PAGE_SIZE, offset })
  const pageTransactions = transactions.data ?? []
  const filteredTransactions = pageTransactions.filter((transaction) => {
    const query = search.trim().toLowerCase()
    const matchesText = !query || [
      transaction.id,
      transaction.related_transaction_id ?? '',
      transaction.source_account_id ?? '',
      transaction.destination_account_id ?? '',
    ].some((value) => value.toLowerCase().includes(query))
    return matchesText && (typeFilter === 'ALL' || transaction.transaction_type === typeFilter)
  })
  const invalidate = useInvalidateLedger()
  const reversal = useMutation({
    mutationFn: async (transaction: Transaction) => {
      if (!user) throw new Error('Sign in again before reversing a transaction.')
      return executeIdempotently(
        user.id,
        `reverse-${transaction.id}`,
        { transaction_id: transaction.id },
        (key) => adminApi.reverseTransaction(transaction.id, key),
      )
    },
    onSuccess: (result, transaction) => {
      invalidate()
      setReversalResult({ original: transaction.id, reversal: result.id })
      setSelectedForReversal(null)
      setReversalError('')
    },
    onError: (error) => {
      setReversalError(error instanceof ApiError ? error.message : error.message)
    },
  })

  useEffect(() => {
    if (!selectedForDetails && !selectedForReversal) return
    dialogRef.current?.focus()

    function handleDialogKeys(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        if (selectedForDetails) setSelectedForDetails(null)
        else if (!reversal.isPending) setSelectedForReversal(null)
        return
      }
      if (event.key !== 'Tab') return

      const dialog = dialogRef.current
      if (!dialog) return
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(
        'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled)',
      ))
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', handleDialogKeys)
    return () => window.removeEventListener('keydown', handleDialogKeys)
  }, [selectedForDetails, selectedForReversal, reversal.isPending])

  function confirmReversal() {
    if (selectedForReversal) reversal.mutate(selectedForReversal)
  }

  return (
    <>
      <PageHeader
        eyebrow="POSTED JOURNALS"
        title="Transactions"
        description="Review internal ledger transactions returned by the transaction history API."
        action={
          user?.role === 'ADMIN'
            ? <div className="admin-key"><span className="admin-key-dot" /> Reversal permissions enabled</div>
            : undefined
        }
      />
      <ProductDisclosure compact />
      {reversalResult && (
        <Alert tone="success">
          Reversal posted. Original <strong className="mono">{reversalResult.original}</strong> · Reversal <strong className="mono">{reversalResult.reversal}</strong>
        </Alert>
      )}
      {reversalError && <Alert>{reversalError}</Alert>}
      <Card className="table-card">
        <div className="table-toolbar">
          <label className="filter-field">
            <span>Filter by account (API)</span>
            <select
              value={accountId}
              onChange={(event) => {
                setAccountId(event.target.value)
                setOffset(0)
              }}
            >
              <option value="">All visible accounts</option>
              {(accounts.data ?? []).map((account) => (
                <option key={account.id} value={account.id}>{account.account_number}</option>
              ))}
            </select>
          </label>
          <label className="filter-field transaction-search">
            <span>Search returned results</span>
            <div className="search-input-wrap">
              <Search size={15} aria-hidden="true" />
              <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Transaction or account ID" />
            </div>
          </label>
          <label className="filter-field">
            <span>Transaction type (page)</span>
            <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value as TransactionType | 'ALL')}>
              <option value="ALL">All types</option>
              <option value="DEPOSIT">Internal deposit</option>
              <option value="WITHDRAWAL">Internal withdrawal</option>
              <option value="TRANSFER">Internal transfer</option>
              <option value="REVERSAL">Internal reversal</option>
            </select>
          </label>
          <span className="table-result-note">
            {filteredTransactions.length} shown · {user?.role === 'ACCOUNT_HOLDER' ? 'your accounts' : 'all accounts'}
          </span>
        </div>
        <p className="filter-scope-note">Search and type filters apply to this API result page. Account filtering is sent to the backend; use pagination to search other pages.</p>
        {transactions.isLoading || accounts.isLoading ? <Loading label="Loading transactions" /> : transactions.isError ? (
          <Alert>{transactions.error instanceof ApiError ? transactions.error.message : 'Transaction history could not be loaded from LedgerLine.'}</Alert>
        ) : filteredTransactions.length === 0 ? (
          <EmptyState title={pageTransactions.length === 0 ? 'No transactions returned' : 'No matching transactions'} description={pageTransactions.length === 0 ? 'There is no internal transaction activity in this API result.' : 'Change the search or type filter, or browse another page.'} />
        ) : (
          <TransactionTable
            transactions={filteredTransactions}
            accounts={accounts.data ?? []}
            onReverse={user?.role === 'ADMIN' ? setSelectedForReversal : undefined}
            onViewDetails={(transaction) => setSelectedForDetails(transaction)}
          />
        )}
        <div className="pagination">
          <span>API page {Math.floor(offset / PAGE_SIZE) + 1} · {pageTransactions.length} records loaded</span>
          <div>
            <Button variant="secondary" disabled={offset === 0 || transactions.isLoading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              <ChevronLeft size={16} /> Previous
            </Button>
            <Button variant="secondary" disabled={(transactions.data?.length ?? 0) < PAGE_SIZE || transactions.isLoading} onClick={() => setOffset(offset + PAGE_SIZE)}>
              Next <ChevronRight size={16} />
            </Button>
          </div>
        </div>
      </Card>
      {selectedForDetails && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setSelectedForDetails(null)
        }}>
          <section ref={dialogRef} tabIndex={-1} className="confirm-dialog transaction-details-dialog" role="dialog" aria-modal="true" aria-labelledby="transaction-details-title">
            <div className="section-heading">
              <div><p className="eyebrow">TRANSACTION REFERENCE</p><h2 id="transaction-details-title">{transactionLabel(selectedForDetails.transaction_type)}</h2></div>
              <Button variant="quiet" aria-label="Close transaction details" onClick={() => setSelectedForDetails(null)}><X size={17} /></Button>
            </div>
            <dl className="transaction-detail-grid">
              <div><dt>Transaction ID</dt><dd className="mono">{selectedForDetails.id}</dd></div>
              <div><dt>Amount</dt><dd>{formatPaise(selectedForDetails.amount_paise)} {selectedForDetails.currency}</dd></div>
              <div><dt>Status</dt><dd><StatusPill status={selectedForDetails.status} /></dd></div>
              <div><dt>Created</dt><dd>{formatDate(selectedForDetails.created_at)}</dd></div>
              <div><dt>Source account</dt><dd>
                {selectedForDetails.source_account_id
                  ? accounts.data?.find((account) => account.id === selectedForDetails.source_account_id)?.account_number ?? 'Other LedgerLine account'
                  : 'Internal clearing account'}
              </dd></div>
              <div><dt>Destination account</dt><dd>
                {selectedForDetails.destination_account_id
                  ? accounts.data?.find((account) => account.id === selectedForDetails.destination_account_id)?.account_number ?? 'Other LedgerLine account'
                  : 'Internal clearing account'}
              </dd></div>
              <div><dt>Original reference</dt><dd className="mono">{selectedForDetails.related_transaction_id ?? '—'}</dd></div>
              <div><dt>Reversal reference</dt><dd className="mono">
                {pageTransactions.find((transaction) => transaction.related_transaction_id === selectedForDetails.id)?.id ?? '—'}
              </dd></div>
            </dl>
            <p className="page-footnote">These records describe internal LedgerLine accounting activity; no external payment was initiated.</p>
            <div className="dialog-actions"><Button variant="secondary" onClick={() => setSelectedForDetails(null)}>Close</Button></div>
          </section>
        </div>
      )}
      {selectedForReversal && (
        <div className="modal-backdrop" role="presentation">
          <section ref={dialogRef} tabIndex={-1} className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="reverse-title">
            <div className="confirm-icon"><AlertTriangle size={22} /></div>
            <h2 id="reverse-title">Confirm reversal</h2>
            <p>This will post an internal opposite journal for the selected transaction. The original entry remains unchanged; no bank or payment-provider transaction occurs.</p>
            <div className="reverse-summary">
              <span>Original reference</span><strong className="mono">{selectedForReversal.id}</strong>
              <span>Amount</span><strong>{formatPaise(selectedForReversal.amount_paise)}</strong>
            </div>
            {reversalError && <Alert>{reversalError}</Alert>}
            <div className="dialog-actions">
              <Button variant="secondary" onClick={() => setSelectedForReversal(null)} disabled={reversal.isPending}>Cancel</Button>
              <Button variant="danger" onClick={confirmReversal} disabled={reversal.isPending}>
                <RotateCcw size={16} /> {reversal.isPending ? 'Posting reversal…' : 'Post reversal'}
              </Button>
            </div>
          </section>
        </div>
      )}
    </>
  )
}
