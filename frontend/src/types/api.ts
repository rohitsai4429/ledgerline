export type UserRole = 'ADMIN' | 'ACCOUNT_HOLDER' | 'AUDITOR'
export type UserStatus = 'ACTIVE' | 'DISABLED'
export type AccountStatus = 'ACTIVE' | 'FROZEN' | 'CLOSED'
export type TransactionType = 'DEPOSIT' | 'WITHDRAWAL' | 'TRANSFER' | 'REVERSAL'
export type EntryType = 'DEBIT' | 'CREDIT'

export interface User {
  id: string
  email: string
  role: UserRole
  status: UserStatus
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
}

export interface Account {
  id: string
  account_number: string
  owner_user_id: string
  balance_paise: string
  status: AccountStatus
  ledger_account_id: string
  created_at: string
  updated_at: string
}

export interface Transaction {
  id: string
  transaction_type: TransactionType
  status: 'POSTING' | 'POSTED'
  amount_paise: string
  currency: string
  source_account_id: string | null
  destination_account_id: string | null
  related_transaction_id: string | null
  created_at: string
}

export interface StatementEntry {
  transaction_id: string
  transaction_type: TransactionType
  related_transaction_id: string | null
  created_at: string
  entry_type: EntryType
  amount_paise: string
  balance_after_paise: string
}

export interface AccountStatement {
  account_id: string
  currency: 'INR'
  opening_balance_paise: string
  closing_balance_paise: string
  entries: StatementEntry[]
}

export interface AuditEvent {
  id: string
  actor_user_id: string | null
  journal_transaction_id: string | null
  event_type: string
  outcome: 'SUCCEEDED' | 'REJECTED'
  details: Record<string, unknown>
  created_at: string
}

export interface ApiErrorBody {
  detail?: string | Array<{ msg?: string }>
}
