import type { ButtonHTMLAttributes, PropsWithChildren, ReactNode } from 'react'
import { AlertCircle, CheckCircle2, Info } from 'lucide-react'

export function Button({
  variant = 'primary',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'quiet' | 'danger' }) {
  return <button className={`button button-${variant} ${className}`} {...props} />
}

export function Card({ children, className = '' }: PropsWithChildren<{ className?: string }>) {
  return <section className={`card ${className}`}>{children}</section>
}

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="page-header">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {action && <div className="page-header-action">{action}</div>}
    </div>
  )
}

export function Alert({
  children,
  tone = 'error',
}: PropsWithChildren<{ tone?: 'error' | 'success' | 'info' }>) {
  const Icon = tone === 'success' ? CheckCircle2 : AlertCircle
  return (
    <div className={`alert alert-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon size={17} aria-hidden="true" />
      <span>{children}</span>
    </div>
  )
}

export function Loading({ label = 'Loading data' }: { label?: string }) {
  return (
    <div className="loading-state" role="status" aria-label={label}>
      <div className="skeleton-stack" aria-hidden="true">
        <span className="skeleton-line skeleton-line-wide" />
        <span className="skeleton-line" />
        <span className="skeleton-line skeleton-line-short" />
      </div>
      <span className="sr-only">{label}</span>
    </div>
  )
}

export function ProductDisclosure({ compact = false }: { compact?: boolean }) {
  return (
    <p className={`product-disclosure ${compact ? 'product-disclosure-compact' : ''}`}>
      <Info size={14} aria-hidden="true" />
      <span>
        LedgerLine is a demonstration financial ledger. Transactions update internal account records and do not move real money through banks or payment providers.
      </span>
    </p>
  )
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description: string
  action?: ReactNode
}) {
  return (
    <div className="empty-state">
      <div className="empty-mark">L</div>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  )
}

export function FieldError({ children }: PropsWithChildren) {
  return children ? <span className="field-error">{children}</span> : null
}

export function Metric({
  label,
  value,
  detail,
}: {
  label: string
  value: string
  detail?: string
}) {
  return (
    <Card className="metric-card">
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
      {detail && <p className="metric-detail">{detail}</p>}
    </Card>
  )
}

export function StatusPill({ status }: { status: string }) {
  return <span className={`status-pill status-${status.toLowerCase()}`}>{status}</span>
}
