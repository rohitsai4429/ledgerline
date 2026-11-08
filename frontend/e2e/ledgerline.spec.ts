import { randomBytes } from 'node:crypto'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

interface E2EState {
  schema: string
  suffix: string
  password: string
  adminEmail: string
  auditorEmail: string
}

interface UserProfile {
  id: string
  email: string
  role: 'ACCOUNT_HOLDER' | 'ADMIN' | 'AUDITOR'
}

interface AccountRecord {
  id: string
  account_number: string
  owner_user_id: string
  balance_paise: number | string
  status: string
}

interface TransactionRecord {
  id: string
  transaction_type: string
  related_transaction_id: string | null
}

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const statePath = path.join(frontendRoot, '.playwright-state.json')
const state = JSON.parse(readFileSync(statePath, 'utf8')) as E2EState
const apiBase = 'http://127.0.0.1:18000/api/v1'
const testPassword = state.password

function customerEmail(customer: 'a' | 'b'): string {
  return `customer-${customer}-${state.suffix}@example.com`
}

async function registerCustomer(page: Page, email: string): Promise<UserProfile> {
  await page.goto('/register')
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel(/^Password\b/).fill(testPassword)
  await page.getByLabel('Confirm password').fill(testPassword)
  const responsePromise = page.waitForResponse(
    (response) => response.url().endsWith('/api/v1/auth/register')
      && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Create account' }).click()
  const response = await responsePromise
  expect(response.status()).toBe(201)
  await expect(page.getByText('Account created. You can now sign in.')).toBeVisible()
  return response.json() as Promise<UserProfile>
}

async function signIn(
  page: Page,
  email: string,
): Promise<{ token: string; user: UserProfile }> {
  await page.goto('/login')
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel('Password').fill(testPassword)
  const loginResponsePromise = page.waitForResponse(
    (response) => response.url().endsWith('/api/v1/auth/login')
      && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Sign in securely' }).click()
  const loginResponse = await loginResponsePromise
  expect(loginResponse.status()).toBe(200)
  const tokenData = await loginResponse.json() as { access_token: string }
  await expect(page.getByRole('banner').getByRole('button')).toContainText(email)
  const profileResponse = await page.context().request.get(`${apiBase}/auth/me`, {
    headers: { Authorization: `Bearer ${tokenData.access_token}` },
  })
  expect(profileResponse.status()).toBe(200)
  return { token: tokenData.access_token, user: await profileResponse.json() as UserProfile }
}

async function createAccount(
  page: Page,
  userId: string,
): Promise<AccountRecord> {
  await page.getByRole('link', { name: 'My accounts', exact: true }).click()
  const responsePromise = page.waitForResponse(
    (response) => response.url().endsWith('/api/v1/accounts')
      && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Open account' }).click()
  const response = await responsePromise
  expect(response.status()).toBe(201)
  const account = await response.json() as AccountRecord
  expect(account.owner_user_id).toBe(userId)
  await expect(page.getByText(`Account ${account.account_number} was created with the API’s initial balance.`)).toBeVisible()
  return account
}

async function postInternalAction(
  page: Page,
  action: 'deposit' | 'withdraw' | 'transfer',
  accountId: string,
  amount: string,
  destinationAccountId?: string,
): Promise<{ transaction: TransactionRecord; key: string }> {
  const navLabel = action === 'withdraw' ? 'Withdraw' : action === 'transfer' ? 'Transfer' : 'Deposit'
  await page.getByRole('link', { name: navLabel, exact: true }).click()
  if (action === 'transfer') {
    await page.getByLabel('From account').selectOption(accountId)
    await page.getByLabel('Recipient account ID').fill(destinationAccountId ?? '')
  } else {
    await page.getByLabel('Account').selectOption(accountId)
  }
  await page.getByLabel('Amount').fill(amount)
  await page.getByRole('button', { name: 'Review internal transaction' }).click()
  const dialog = page.getByRole('dialog')
  const confirmName = action === 'deposit'
    ? 'Confirm internal deposit'
    : action === 'withdraw'
      ? 'Confirm internal withdrawal'
      : 'Confirm internal transfer'
  const requestPromise = page.waitForRequest(
    (request) => request.url().endsWith(`/api/v1/transactions/${action === 'deposit' ? 'deposits' : action === 'withdraw' ? 'withdrawals' : 'transfers'}`)
      && request.method() === 'POST',
  )
  const responsePromise = page.waitForResponse(
    (response) => response.url().endsWith(`/api/v1/transactions/${action === 'deposit' ? 'deposits' : action === 'withdraw' ? 'withdrawals' : 'transfers'}`)
      && response.request().method() === 'POST',
  )
  await dialog.getByRole('button', { name: confirmName }).click()
  const [request, response] = await Promise.all([requestPromise, responsePromise])
  expect(response.status()).toBe(201)
  await expect(page.getByText(/posted\. Reference/)).toBeVisible()
  return {
    transaction: await response.json() as TransactionRecord,
    key: (await request.headerValue('Idempotency-Key')) ?? '',
  }
}

async function attachScreenshot(page: Page, name: string): Promise<void> {
  await test.info().attach(name, {
    body: await page.screenshot({ fullPage: true }),
    contentType: 'image/png',
  })
}

async function apiRequest(
  request: APIRequestContext,
  method: 'get' | 'post' | 'patch',
  pathSuffix: string,
  token: string,
  body?: object,
  idempotencyKey?: string,
) {
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` }
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey
  const options = { headers, ...(body ? { data: body } : {}) }
  if (method === 'get') return request.get(`${apiBase}${pathSuffix}`, options)
  if (method === 'post') return request.post(`${apiBase}${pathSuffix}`, options)
  return request.patch(`${apiBase}${pathSuffix}`, options)
}

test('real customer, administrator, auditor, and PostgreSQL ledger journey', async ({
  page,
  request,
}) => {
  const customerAEmail = customerEmail('a')
  const customerBEmail = customerEmail('b')

  const customerA = await registerCustomer(page, customerAEmail)
  expect(customerA.role).toBe('ACCOUNT_HOLDER')
  await signIn(page, customerAEmail)
  const accountA = await createAccount(page, customerA.id)
  await attachScreenshot(page, 'customer-accounts')
  await page.getByRole('button', { name: 'Sign out' }).click()

  const customerB = await registerCustomer(page, customerBEmail)
  expect(customerB.role).toBe('ACCOUNT_HOLDER')
  await signIn(page, customerBEmail)
  const accountB = await createAccount(page, customerB.id)
  await page.getByRole('button', { name: 'Sign out' }).click()

  const customerASession = await signIn(page, customerAEmail)
  const deposit = await postInternalAction(page, 'deposit', accountA.id, '100.00')
  expect(deposit.key).not.toBe('')

  const replayResponse = await apiRequest(
    request,
    'post',
    '/transactions/deposits',
    customerASession.token,
    { account_id: accountA.id, amount_paise: 10_000 },
    deposit.key,
  )
  expect(replayResponse.status()).toBe(201)
  expect((await replayResponse.json() as TransactionRecord).id).toBe(deposit.transaction.id)

  const failedWithdrawal = await apiRequest(
    request,
    'post',
    '/transactions/withdrawals',
    customerASession.token,
    { account_id: accountA.id, amount_paise: 900_000 },
    `e2e-insufficient-${randomBytes(8).toString('hex')}`,
  )
  expect(failedWithdrawal.status()).toBe(409)

  const foreignAccount = await apiRequest(
    request,
    'get',
    `/accounts/${accountB.id}`,
    customerASession.token,
  )
  expect(foreignAccount.status()).toBe(404)
  const foreignSource = await apiRequest(
    request,
    'post',
    '/transactions/transfers',
    customerASession.token,
    {
      source_account_id: accountB.id,
      destination_account_id: accountA.id,
      amount_paise: 100,
    },
    `e2e-foreign-source-${randomBytes(8).toString('hex')}`,
  )
  expect(foreignSource.status()).toBe(404)

  await postInternalAction(page, 'withdraw', accountA.id, '10.00')
  const transfer = await postInternalAction(
    page,
    'transfer',
    accountA.id,
    '25.00',
    accountB.id,
  )

  const customerAAccount = await apiRequest(
    request,
    'get',
    `/accounts/${accountA.id}`,
    customerASession.token,
  )
  expect(customerAAccount.status()).toBe(200)
  expect(String((await customerAAccount.json() as AccountRecord).balance_paise)).toBe('6500')
  const customerBStatementDenied = await apiRequest(
    request,
    'get',
    `/accounts/${accountB.id}/statement`,
    customerASession.token,
  )
  expect(customerBStatementDenied.status()).toBe(404)

  const customerBSession = await signIn(page, customerBEmail)
  await page.getByRole('link', { name: 'Statements', exact: true }).click()
  await page.getByLabel('Account').selectOption(accountB.id)
  await expect(page.getByRole('heading', { name: 'Statements' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Ledger activity' })).toBeVisible()
  await expect(page.getByText('Internal transfer', { exact: true })).toBeVisible()
  const customerBHistory = await apiRequest(
    request,
    'get',
    `/transactions?account_id=${accountB.id}`,
    customerBSession.token,
  )
  expect(customerBHistory.status()).toBe(200)
  expect((await customerBHistory.json() as TransactionRecord[]).map((item) => item.id)).toContain(transfer.transaction.id)
  await attachScreenshot(page, 'customer-statement')
  await page.getByRole('button', { name: 'Sign out' }).click()
  await signIn(page, customerAEmail)

  const historyBeforeRefresh = await apiRequest(
    request,
    'get',
    '/transactions',
    customerASession.token,
  )
  expect(historyBeforeRefresh.status()).toBe(200)
  expect((await historyBeforeRefresh.json() as TransactionRecord[])).toHaveLength(3)

  await page.getByRole('link', { name: 'Transactions', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Transactions' })).toBeVisible()
  await expect(page.getByRole('row').filter({ hasText: 'Internal deposit' })).toBeVisible()
  await expect(page.getByRole('row').filter({ hasText: 'Internal withdrawal' })).toBeVisible()
  await expect(page.getByRole('row').filter({ hasText: 'Internal transfer' })).toBeVisible()
  await page.reload()
  await expect(page).toHaveURL(/\/login$/)
  const refreshedSession = await signIn(page, customerAEmail)
  const historyAfterRefresh = await apiRequest(
    request,
    'get',
    '/transactions',
    refreshedSession.token,
  )
  expect((await historyAfterRefresh.json() as TransactionRecord[])).toHaveLength(3)
  await page.getByRole('link', { name: 'My accounts', exact: true }).click()
  await expect(page.getByText('LL', { exact: false }).first()).toBeVisible()
  await expect(page.getByText('₹65.00')).toBeVisible()
  await attachScreenshot(page, 'customer-dashboard-after-refresh')
  await page.getByRole('button', { name: 'Sign out' }).click()

  await signIn(page, state.adminEmail)
  await page.getByRole('link', { name: 'Accounts', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Account management' })).toBeVisible()
  const accountBRow = page.getByRole('row').filter({ hasText: accountB.account_number })
  await expect(accountBRow).toBeVisible()
  await accountBRow.getByRole('button', { name: 'View' }).click()
  await expect(page.getByText(customerB.id)).toBeVisible()
  await page.getByRole('button', { name: 'Close details' }).click()

  const statusResponsePromise = page.waitForResponse(
    (response) => response.url().endsWith(`/api/v1/accounts/${accountB.id}/status`)
      && response.request().method() === 'PATCH',
  )
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('combobox', { name: `Set status for ${accountB.account_number}` }).selectOption('FROZEN')
  const statusResponse = await statusResponsePromise
  expect(statusResponse.status()).toBe(200)
  await expect(page.getByText(`${accountB.account_number} is now frozen.`)).toBeVisible()

  await page.getByRole('link', { name: 'Transactions', exact: true }).click()
  await page.getByLabel('Transaction type (page)').selectOption('TRANSFER')
  await page.getByLabel('Search returned results').fill(transfer.transaction.id)
  const transferRow = page.getByRole('row').filter({ hasText: 'Internal transfer' })
  await expect(transferRow).toBeVisible()
  await expect(transferRow.getByRole('button', { name: 'Reverse' })).toBeVisible()
  await transferRow.getByRole('button', { name: 'Reverse' }).click()
  const reversalResponsePromise = page.waitForResponse(
    (response) => response.url().endsWith(`/api/v1/transactions/${transfer.transaction.id}/reverse`)
      && response.request().method() === 'POST',
  )
  await page.getByRole('dialog').getByRole('button', { name: 'Post reversal' }).click()
  const reversalResponse = await reversalResponsePromise
  expect(reversalResponse.status()).toBe(201)
  const reversal = await reversalResponse.json() as TransactionRecord
  expect(reversal.related_transaction_id).toBe(transfer.transaction.id)
  await expect(page.getByText(new RegExp(`Original ${transfer.transaction.id}.*Reversal ${reversal.id}`))).toBeVisible()

  await page.getByLabel('Transaction type (page)').selectOption('ALL')
  await page.getByLabel('Search returned results').fill('')
  const originalTransferRow = page.getByRole('row').filter({ hasText: 'Internal transfer' })
  await originalTransferRow.getByRole('button', { name: 'View Internal Transfer details' }).click()
  const detailsDialog = page.getByRole('dialog')
  await expect(detailsDialog.getByText(transfer.transaction.id)).toBeVisible()
  await expect(detailsDialog.getByText(reversal.id)).toBeVisible()
  await detailsDialog.getByRole('button', { name: 'Close transaction details' }).click()
  await page.getByRole('link', { name: 'Audit events', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Audit events' })).toBeVisible()
  await expect(page.getByText('ACCOUNT STATUS CHANGED')).toBeVisible()
  await expect(page.getByText('REVERSAL', { exact: false }).first()).toBeVisible()
  await attachScreenshot(page, 'administrator-audit')
  await page.getByRole('button', { name: 'Sign out' }).click()

  const auditorSession = await signIn(page, state.auditorEmail)
  await page.getByRole('link', { name: 'Transactions', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Transactions' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reverse' })).toHaveCount(0)
  await page.getByRole('link', { name: 'Audit events', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Audit events' })).toBeVisible()
  await expect(page.getByText('AUDIT', { exact: false }).first()).toBeVisible()
  const deniedMutations = await Promise.all([
    apiRequest(
      request,
      'post',
      '/transactions/deposits',
      auditorSession.token,
      { account_id: accountA.id, amount_paise: 100 },
      `e2e-auditor-deposit-${randomBytes(8).toString('hex')}`,
    ),
    apiRequest(
      request,
      'post',
      '/transactions/withdrawals',
      auditorSession.token,
      { account_id: accountA.id, amount_paise: 100 },
      `e2e-auditor-withdrawal-${randomBytes(8).toString('hex')}`,
    ),
    apiRequest(
      request,
      'post',
      '/transactions/transfers',
      auditorSession.token,
      {
        source_account_id: accountA.id,
        destination_account_id: accountB.id,
        amount_paise: 100,
      },
      `e2e-auditor-transfer-${randomBytes(8).toString('hex')}`,
    ),
    apiRequest(
      request,
      'patch',
      `/accounts/${accountB.id}/status`,
      auditorSession.token,
      { status: 'ACTIVE' },
    ),
    apiRequest(
      request,
      'post',
      `/transactions/${deposit.transaction.id}/reverse`,
      auditorSession.token,
      {},
      `e2e-auditor-reversal-${randomBytes(8).toString('hex')}`,
    ),
  ])
  expect(deniedMutations.map((response) => response.status())).toEqual([403, 403, 403, 403, 403])
  const finalAccountA = await apiRequest(
    request,
    'get',
    `/accounts/${accountA.id}`,
    auditorSession.token,
  )
  const finalAccountB = await apiRequest(
    request,
    'get',
    `/accounts/${accountB.id}`,
    auditorSession.token,
  )
  expect(String((await finalAccountA.json() as AccountRecord).balance_paise)).toBe('9000')
  const accountBFinal = await finalAccountB.json() as AccountRecord
  expect(String(accountBFinal.balance_paise)).toBe('0')
  expect(accountBFinal.status).toBe('FROZEN')
  await attachScreenshot(page, 'auditor-read-only')

  const python = process.env.E2E_PYTHON
    ?? path.resolve(frontendRoot, '..', 'backend', '.venv', 'Scripts', 'python.exe')
  const { execFileSync } = await import('node:child_process')
  execFileSync(
    python,
    ['scripts/e2e_db.py', 'verify', state.schema, state.suffix],
    {
      cwd: path.resolve(frontendRoot, '..', 'backend'),
      stdio: 'inherit',
    },
  )
})
