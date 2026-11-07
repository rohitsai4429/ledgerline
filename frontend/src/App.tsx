import { lazy, Suspense } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthProvider'
import { RequireAuth, RequireRole } from './auth/RoleGate'
import { AppShell } from './components/AppShell'
import { Loading } from './components/ui'

const LoginPage = lazy(() => import('./pages/AuthPages').then((module) => ({ default: module.LoginPage })))
const RegisterPage = lazy(() => import('./pages/AuthPages').then((module) => ({ default: module.RegisterPage })))
const AdminAccountsPage = lazy(() => import('./pages/AdminPages').then((module) => ({ default: module.AdminAccountsPage })))
const AuditPage = lazy(() => import('./pages/AuditPage').then((module) => ({ default: module.AuditPage })))
const AccountsPage = lazy(() => import('./pages/AccountsPage').then((module) => ({ default: module.AccountsPage })))
const DashboardPage = lazy(() => import('./pages/DashboardPage').then((module) => ({ default: module.DashboardPage })))
const MoneyActionPage = lazy(() => import('./pages/MoneyActionPage').then((module) => ({ default: module.MoneyActionPage })))
const StatementsPage = lazy(() => import('./pages/StatementsPage').then((module) => ({ default: module.StatementsPage })))
const TransactionsPage = lazy(() => import('./pages/TransactionsPage').then((module) => ({ default: module.TransactionsPage })))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 20_000, retry: 1, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
})

const holders = ['ACCOUNT_HOLDER'] as const
const admin = ['ADMIN'] as const
const oversight = ['ADMIN', 'AUDITOR'] as const
const allRoles = ['ADMIN', 'ACCOUNT_HOLDER', 'AUDITOR'] as const

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Suspense fallback={<Loading label="Loading LedgerLine" />}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route element={<RequireAuth />}>
                <Route element={<AppShell />}>
                  <Route path="/dashboard" element={<DashboardPage />} />
                  <Route element={<RequireRole roles={[...holders]} />}>
                    <Route path="/accounts" element={<AccountsPage />} />
                    <Route path="/deposit" element={<MoneyActionPage action="DEPOSIT" />} />
                    <Route path="/withdraw" element={<MoneyActionPage action="WITHDRAWAL" />} />
                    <Route path="/transfer" element={<MoneyActionPage action="TRANSFER" />} />
                  </Route>
                  <Route element={<RequireRole roles={[...allRoles]} />}>
                    <Route path="/transactions" element={<TransactionsPage />} />
                    <Route path="/statements" element={<StatementsPage />} />
                    <Route path="/statements/:accountId" element={<StatementsPage />} />
                  </Route>
                  <Route element={<RequireRole roles={[...admin]} />}>
                    <Route path="/admin/accounts" element={<AdminAccountsPage />} />
                  </Route>
                  <Route element={<RequireRole roles={[...oversight]} />}>
                    <Route path="/audit" element={<AuditPage />} />
                  </Route>
                </Route>
              </Route>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
