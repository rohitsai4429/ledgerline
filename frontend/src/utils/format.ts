import type { AccountStatus, TransactionType } from '../types/api'

const rupeeFormatter = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

export function formatPaise(paise: number | string | bigint): string {
  const amount = BigInt(paise)
  const negative = amount < 0n
  const absolute = negative ? -amount : amount
  const rupees = absolute / 100n
  const subRupees = String(absolute % 100n).padStart(2, '0')
  return `${negative ? '−' : ''}₹${rupeeFormatter.format(rupees)}.${subRupees}`
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export function transactionLabel(type: TransactionType): string {
  return {
    DEPOSIT: 'Internal deposit',
    WITHDRAWAL: 'Internal withdrawal',
    TRANSFER: 'Internal transfer',
    REVERSAL: 'Internal reversal',
  }[type]
}

export function statusLabel(status: AccountStatus): string {
  return status.charAt(0) + status.slice(1).toLowerCase()
}

export function toPaise(amount: string): number {
  const parsed = Number(amount)
  const paise = Math.round(parsed * 100)
  if (!Number.isSafeInteger(paise)) throw new Error('Amount exceeds the supported precision')
  return paise
}
