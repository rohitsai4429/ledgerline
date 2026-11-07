import { useEffect, useRef, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowDownLeft, ArrowLeftRight, ArrowUpRight, CircleCheck, Info } from 'lucide-react'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import { transactionsApi } from '../api/transactions'
import { useAuth } from '../auth/AuthContext'
import { Alert, Button, Card, FieldError, Loading, PageHeader, ProductDisclosure } from '../components/ui'
import { useAccounts, useInvalidateLedger } from '../hooks/useLedgerData'
import type { Account, TransactionType } from '../types/api'
import { formatPaise, transactionLabel } from '../utils/format'
import { executeIdempotently } from '../utils/idempotency'

type Action = 'DEPOSIT' | 'WITHDRAWAL' | 'TRANSFER'

const amountSchema = z.string()
  .trim()
  .regex(/^\d{1,16}(\.\d{1,2})?$/, 'Enter a positive amount with up to two decimal places')
  .transform((value) => Number(value))
  .refine((value) => Number.isFinite(value) && value > 0, 'Amount must be greater than zero')
  .refine((value) => Number.isSafeInteger(value * 100), 'Amount exceeds the supported precision')
  .transform((value) => Math.round(value * 100))

function createActionSchema(action: Action) {
  return z.object({
    account_id: z.string().uuid('Choose an account'),
    amount: amountSchema,
    destination_account_id: z.string().optional(),
  }).superRefine((values, context) => {
    if (action === 'TRANSFER') {
    const parsed = z.string().uuid().safeParse(values.destination_account_id)
    if (!parsed.success) {
      context.addIssue({
        code: 'custom',
        path: ['destination_account_id'],
        message: 'Enter a valid recipient account ID',
      })
    }
    }
  })
}

const actionCopy: Record<Action, { title: string; description: string; icon: typeof ArrowDownLeft; eyebrow: string }> = {
  DEPOSIT: {
    title: 'Make a deposit',
    description: 'Record an internal deposit against an active LedgerLine account.',
    icon: ArrowDownLeft,
    eyebrow: 'ADD FUNDS',
  },
  WITHDRAWAL: {
    title: 'Withdraw funds',
    description: 'Record an internal withdrawal from an active account with sufficient ledger balance.',
    icon: ArrowUpRight,
    eyebrow: 'MOVE OUT',
  },
  TRANSFER: {
    title: 'Transfer money',
    description: 'Move ledger balance from an account you own to another active LedgerLine account.',
    icon: ArrowLeftRight,
    eyebrow: 'ACCOUNT TO ACCOUNT',
  },
}

function selectableAccounts(accounts: Account[]) {
  return accounts.filter((account) => account.status === 'ACTIVE')
}

export function MoneyActionPage({ action }: { action: Action }) {
  const { user } = useAuth()
  const accountQuery = useAccounts()
  const invalidate = useInvalidateLedger()
  const { title, description, icon: Icon, eyebrow } = actionCopy[action]
  const schema = createActionSchema(action)
  const [result, setResult] = useState<{ id: string; type: TransactionType } | null>(null)
  const [requestError, setRequestError] = useState('')
  const [pendingValues, setPendingValues] = useState<z.output<typeof schema> | null>(null)
  const [isPosting, setIsPosting] = useState(false)
  const confirmationRef = useRef<HTMLElement | null>(null)
  const form = useForm<z.input<typeof schema>, unknown, z.output<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { account_id: '', amount: '', destination_account_id: '' },
  })
  const accounts = selectableAccounts(accountQuery.data ?? [])
  const selectedAccountId = useWatch({ control: form.control, name: 'account_id' })

  useEffect(() => {
    if (!pendingValues) return
    confirmationRef.current?.focus()

    function handleConfirmationKeys(event: KeyboardEvent) {
      if (event.key === 'Escape' && !isPosting) {
        setPendingValues(null)
        return
      }
      if (event.key !== 'Tab') return
      const dialog = confirmationRef.current
      if (!dialog) return
      const buttons = Array.from(dialog.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'))
      if (buttons.length === 0) return
      const first = buttons[0]
      const last = buttons[buttons.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', handleConfirmationKeys)
    return () => window.removeEventListener('keydown', handleConfirmationKeys)
  }, [pendingValues, isPosting])

  function submit(values: z.output<typeof schema>) {
    setRequestError('')
    setResult(null)
    setPendingValues(values)
  }

  async function confirmTransaction() {
    if (!user || !pendingValues) return
    setIsPosting(true)
    setRequestError('')
    const values = pendingValues
    const amountPaise = values.amount
    const payload = action === 'TRANSFER'
      ? {
          source_account_id: values.account_id,
          destination_account_id: values.destination_account_id ?? '',
          amount_paise: amountPaise,
        }
      : { account_id: values.account_id, amount_paise: amountPaise }

    try {
      const transaction = await executeIdempotently(
        user.id,
        action.toLowerCase(),
        payload,
        (key) => {
          if (action === 'DEPOSIT') {
            return transactionsApi.deposit(
              { account_id: values.account_id, amount_paise: amountPaise },
              key,
            )
          }
          if (action === 'WITHDRAWAL') {
            return transactionsApi.withdraw(
              { account_id: values.account_id, amount_paise: amountPaise },
              key,
            )
          }
          return transactionsApi.transfer(
            {
              source_account_id: values.account_id,
              destination_account_id: values.destination_account_id ?? '',
              amount_paise: amountPaise,
            },
            key,
          )
        },
      )
      invalidate()
      setResult({ id: transaction.id, type: transaction.transaction_type })
      setPendingValues(null)
      form.reset({ account_id: '', amount: '', destination_account_id: '' })
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : 'The transaction could not be completed.')
    } finally {
      setIsPosting(false)
    }
  }

  const pendingAccount = pendingValues
    ? accountQuery.data?.find((account) => account.id === pendingValues.account_id)
    : undefined

  return (
    <>
      <PageHeader eyebrow={eyebrow} title={title} description={description} />
      <ProductDisclosure compact />
      <div className="transaction-form-layout">
        <Card className="form-card">
          <form className="transaction-form" onSubmit={form.handleSubmit(submit)} noValidate>
            {requestError && !pendingValues && <Alert>{requestError}</Alert>}
            {result && (
              <Alert tone="success">
                {transactionLabel(result.type)} posted. Reference <strong className="mono">{result.id}</strong>
              </Alert>
            )}
            {action === 'TRANSFER' ? (
              <>
                <label className="form-field">
                  <span>From account</span>
                  <select {...form.register('account_id')}>
                    <option value="">Select an account</option>
                    {accounts.map((account) => <option key={account.id} value={account.id}>{account.account_number} · {formatPaise(account.balance_paise)}</option>)}
                  </select>
                  <FieldError>{form.formState.errors.account_id?.message}</FieldError>
                </label>
                <label className="form-field">
                  <span>Recipient account ID</span>
                  <input placeholder="Paste the recipient's account UUID" {...form.register('destination_account_id')} />
                  <small>Use the account ID provided by the recipient. The API does not provide account-number lookup.</small>
                  <FieldError>{form.formState.errors.destination_account_id?.message}</FieldError>
                </label>
              </>
            ) : (
              <label className="form-field">
                <span>Account</span>
                <select {...form.register('account_id')}>
                  <option value="">Select an active account</option>
                  {accounts.map((account) => <option key={account.id} value={account.id}>{account.account_number} · {formatPaise(account.balance_paise)}</option>)}
                </select>
                <FieldError>{form.formState.errors.account_id?.message}</FieldError>
              </label>
            )}
            <label className="form-field">
              <span>Amount <small>INR</small></span>
              <div className="amount-input">
                <span>₹</span>
                <input inputMode="decimal" placeholder="0.00" autoComplete="off" {...form.register('amount')} />
                <small>INR</small>
              </div>
              <FieldError>{form.formState.errors.amount?.message}</FieldError>
              <small>Amounts are converted to integer paise before submission.</small>
            </label>
            <div className="transaction-summary">
              <span><Info size={15} /> Final authorization and balance checks happen on the server.</span>
              {action === 'WITHDRAWAL' && selectedAccountId && (
                <strong>Current API balance: {formatPaise(accountQuery.data?.find((account) => account.id === selectedAccountId)?.balance_paise ?? 0)}</strong>
              )}
            </div>
            <Button className="form-submit" type="submit" disabled={form.formState.isSubmitting || isPosting || accountQuery.isLoading || accounts.length === 0}>
              Review internal transaction
            </Button>
            {accounts.length === 0 && !accountQuery.isLoading && (
              <Alert tone="info">No active account is available for this operation.</Alert>
            )}
          </form>
        </Card>
        <aside className="side-info-card">
          <div className="side-info-icon"><Icon size={20} /></div>
          <h3>How this posts</h3>
          <p>This records an internal ledger operation. LedgerLine posts balanced accounting entries; no external payment is initiated.</p>
          <div className="side-info-divider" />
          <div className="side-info-line"><CircleCheck size={16} /><span>Unique request key used for safe retries</span></div>
          <div className="side-info-line"><CircleCheck size={16} /><span>Account status and available funds checked server-side</span></div>
          <div className="side-info-line"><CircleCheck size={16} /><span>Posted entries cannot be edited; corrections use reversals</span></div>
          <div className="side-info-foot">Only API-confirmed outcomes are displayed.</div>
        </aside>
      </div>
      {accountQuery.isError && <Alert>Accounts could not be loaded. Refresh and retry before submitting.</Alert>}
      {accountQuery.isLoading && <Loading label="Loading accounts" />}
      {pendingValues && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget && !isPosting) setPendingValues(null)
        }}>
          <section ref={confirmationRef} tabIndex={-1} className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="internal-transaction-title">
            <div className="confirm-icon"><Icon size={20} /></div>
            <p className="eyebrow">CONFIRM INTERNAL OPERATION</p>
            <h2 id="internal-transaction-title">{transactionLabel(action)}</h2>
            <p>Confirm this change to LedgerLine’s internal accounting records. This does not move real money through banks or payment providers.</p>
            <div className="reverse-summary">
              <span>Account</span><strong>{pendingAccount?.account_number ?? pendingValues.account_id}</strong>
              {action === 'TRANSFER' && (
                <>
                  <span>Recipient account ID</span><strong className="mono">{pendingValues.destination_account_id}</strong>
                </>
              )}
              <span>Internal ledger amount</span><strong>{formatPaise(pendingValues.amount)}</strong>
            </div>
            {requestError && <Alert>{requestError}</Alert>}
            <ProductDisclosure compact />
            <div className="dialog-actions">
              <Button variant="secondary" onClick={() => setPendingValues(null)} disabled={isPosting}>Back</Button>
              <Button onClick={confirmTransaction} disabled={isPosting}>
                {isPosting ? 'Posting internally…' : `Confirm ${transactionLabel(action).toLowerCase()}`}
              </Button>
            </div>
          </section>
        </div>
      )}
    </>
  )
}
