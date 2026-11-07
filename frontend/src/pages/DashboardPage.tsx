import { useMemo } from 'react'
import {
  ArrowDownLeft,
  ArrowLeftRight,
  ArrowRight,
  ArrowUpRight,
  ShieldCheck,
  WalletCards,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { TransactionTable } from '../components/TransactionTable'
import { Alert, Card, EmptyState, Loading, Metric, PageHeader, ProductDisclosure } from '../components/ui'
import { useAccounts, useAuditEvents, useTransactions } from '../hooks/useLedgerData'
import { formatPaise } from '../utils/format'

const todayLabel = new Intl.DateTimeFormat('en-IN', {
  weekday: 'long',
  month: 'long',
  day: 'numeric',
}).format(new Date()).toUpperCase()

function DailyMovement({ transactions }: { transactions: NonNullable<ReturnType<typeof useTransactions>['data']> }) {
  const data = useMemo(() => {
    const groups = new Map<string, bigint>()
    for (const transaction of transactions) {
      const day = new Intl.DateTimeFormat('en-IN', {
        day: '2-digit',
        month: 'short',
        year: '2-digit',
      }).format(
        new Date(transaction.created_at),
      )
      groups.set(day, (groups.get(day) ?? 0n) + BigInt(transaction.amount_paise))
    }
    const totals = [...groups.entries()].reverse()
    if (totals.some(([, amount]) => amount > BigInt(Number.MAX_SAFE_INTEGER))) {
      return { values: [], safelyRepresentable: false }
    }
    return {
      values: totals.map(([day, amount]) => ({ day, amount: Number(amount) })),
      safelyRepresentable: true,
    }
  }, [transactions])

  return (
    <div className="chart-wrap" aria-label="Daily posted transaction amounts based on returned records">
      {data.values.length === 0 ? (
        !data.safelyRepresentable ? (
          <div className="chart-empty">
            Chart omitted because the returned total exceeds safe chart precision. Transaction details remain exact below.
          </div>
        ) : (
        <EmptyState title="Activity will appear here" description="No transactions were returned for this view." />
        )
      ) : (
        <>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.values} margin={{ top: 12, right: 12, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="movementFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#0f9d78" stopOpacity={0.19} />
                  <stop offset="100%" stopColor="#0f9d78" stopOpacity={0.015} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#edf0f2" strokeDasharray="3 5" vertical={false} />
              <XAxis dataKey="day" axisLine={false} tickLine={false} tick={{ fill: '#8a94a3', fontSize: 11 }} />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#8a94a3', fontSize: 11 }}
                tickFormatter={(value: number) => formatPaise(Math.round(value)).replace(/\.00$/, '')}
              />
              <Tooltip
                formatter={(value) => [formatPaise(Math.round(Number(value))), 'Posted amount']}
                contentStyle={{ borderRadius: 12, border: '1px solid #e8ebee', boxShadow: '0 12px 30px #17202d12' }}
              />
              <Area
                type="monotone"
                dataKey="amount"
                stroke="#0f9d78"
                strokeWidth={2.2}
                fill="url(#movementFill)"
                activeDot={{ r: 4, strokeWidth: 0 }}
              />
            </AreaChart>
          </ResponsiveContainer>
          <p className="chart-footnote">Amounts are derived from transaction records returned by LedgerLine.</p>
        </>
      )}
    </div>
  )
}

export function DashboardPage() {
  const { user } = useAuth()
  const accountsQuery = useAccounts()
  const transactionsQuery = useTransactions({ limit: 100, offset: 0 })
  const auditQuery = useAuditEvents({ limit: 5, offset: 0 }, user?.role === 'AUDITOR')
  const accounts = accountsQuery.data ?? []
  const transactions = transactionsQuery.data ?? []
  const totalPaise = accounts.reduce((sum, account) => sum + BigInt(account.balance_paise), 0n)
  const activeCount = accounts.filter((account) => account.status === 'ACTIVE').length
  const isFailure = accountsQuery.isError || transactionsQuery.isError

  if (accountsQuery.isLoading || transactionsQuery.isLoading) return <Loading label="Loading verified account data" />
  if (isFailure) return <DataFailure />

  const roleHeading = user?.role === 'ADMIN'
    ? 'Operations overview'
    : user?.role === 'AUDITOR'
      ? 'Ledger oversight'
      : 'Your financial overview'

  return (
    <>
      <PageHeader
        eyebrow={todayLabel}
        title={roleHeading}
        description={
          user?.role === 'AUDITOR'
            ? 'A read-only view of internal account balances and posted ledger activity.'
            : 'A clear view of your internal accounts and posted ledger activity.'
        }
        action={user?.role === 'ACCOUNT_HOLDER' ? <Link className="button button-primary" to="/deposit"><ArrowDownLeft size={16} /> New deposit</Link> : undefined}
      />
      <ProductDisclosure compact />

      <div className="metric-grid">
        <Metric
          label={user?.role === 'ACCOUNT_HOLDER' ? 'Total account balance' : 'Total customer balances'}
          value={formatPaise(totalPaise)}
          detail={`${accounts.length} account${accounts.length === 1 ? '' : 's'} returned by LedgerLine`}
        />
        <Metric label="Active accounts" value={String(activeCount)} detail={`${accounts.length - activeCount} not active`} />
        <Metric label="Posted activity" value={String(transactions.length)} detail="Transactions in the current result set" />
      </div>

      <div className="dashboard-grid">
        <Card className="chart-card">
          <div className="section-heading">
            <div><h2>Internal ledger activity</h2><p>Amounts by date in the transaction records returned by LedgerLine</p></div>
            <span className="chart-legend"><i /> Total amount</span>
          </div>
          <DailyMovement transactions={transactions} />
        </Card>
        <Card className="quick-actions-card">
          <div className="section-heading"><div><h2>Quick access</h2><p>Available workspace actions</p></div></div>
          <div className="quick-action-list">
            {user?.role === 'ACCOUNT_HOLDER' ? (
              <>
                <QuickAction to="/deposit" icon={<ArrowDownLeft size={18} />} title="Deposit funds" text="Add funds to your account" />
                <QuickAction to="/withdraw" icon={<ArrowUpRight size={18} />} title="Withdraw" text="Move funds from your account" />
                <QuickAction to="/transfer" icon={<ArrowLeftRight size={18} />} title="Transfer money" text="Send to another account" />
              </>
            ) : (
              <>
                {user?.role === 'ADMIN' && <QuickAction to="/admin/accounts" icon={<WalletCards size={18} />} title="Manage accounts" text="Review status and account balances" />}
                <QuickAction to="/transactions" icon={<ArrowLeftRight size={18} />} title="Monitor transactions" text="Browse posted journal activity" />
                <QuickAction to="/audit" icon={<ShieldCheck size={18} />} title="Audit events" text="Review operation outcomes" />
              </>
            )}
          </div>
          <div className="ledger-note"><ShieldCheck size={16} /><span>Balances and activity come from the authenticated LedgerLine API.</span></div>
        </Card>
      </div>

      <Card className="table-card">
        <div className="section-heading section-heading-action">
          <div><h2>Recent transactions</h2><p>Latest activity returned by the transaction history API</p></div>
          <Link className="inline-link" to="/transactions">View all <ArrowRight size={15} /></Link>
        </div>
        <TransactionTable transactions={transactions.slice(0, 6)} accounts={accounts} />
      </Card>

      {user?.role === 'AUDITOR' && (
        <Card className="table-card">
          <div className="section-heading"><div><h2>Recent audit events</h2><p>Operational outcomes returned by the audit API</p></div></div>
          {auditQuery.isLoading ? <Loading /> : auditQuery.isError ? <Alert>Audit events could not be loaded.</Alert> : (
            <div className="audit-preview">
              {(auditQuery.data ?? []).length === 0
                ? <EmptyState title="No audit events returned" description="Audit activity will appear when recorded by LedgerLine." />
                : (auditQuery.data ?? []).map((event) => (
                  <div className="audit-row" key={event.id}>
                    <span className={`audit-dot audit-${event.outcome.toLowerCase()}`} />
                    <div><strong>{event.event_type.replaceAll('_', ' ')}</strong><small>{event.actor_user_id?.slice(0, 8) ?? 'Unauthenticated'} · {new Date(event.created_at).toLocaleString('en-IN')}</small></div>
                    <span className="audit-result">{event.outcome}</span>
                  </div>
                ))}
            </div>
          )}
        </Card>
      )}
    </>
  )
}

function QuickAction({ to, icon, title, text }: { to: string; icon: React.ReactNode; title: string; text: string }) {
  return (
    <Link className="quick-action" to={to}>
      <span className="quick-action-icon">{icon}</span>
      <span className="quick-action-copy"><strong>{title}</strong><small>{text}</small></span>
      <ArrowRight size={16} />
    </Link>
  )
}

function DataFailure() {
  return (
    <div className="page-stack">
      <PageHeader title="LedgerLine overview" description="Account data could not be loaded from the API." />
      <Alert>We couldn’t retrieve your current account or transaction data. Please check your connection and retry.</Alert>
    </div>
  )
}
