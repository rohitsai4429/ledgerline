import { useState } from 'react'
import {
  ArrowDownLeft,
  ArrowLeftRight,
  ArrowUpRight,
  BadgeCheck,
  Banknote,
  ChevronDown,
  ClipboardList,
  LayoutDashboard,
  LogOut,
  Menu,
  ReceiptText,
  ShieldCheck,
  Users,
  WalletCards,
  X,
} from 'lucide-react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ProductDisclosure } from './ui'
import type { UserRole } from '../types/api'

interface NavItem {
  label: string
  to: string
  icon: typeof LayoutDashboard
  roles: UserRole[]
}

const allRoles: UserRole[] = ['ADMIN', 'ACCOUNT_HOLDER', 'AUDITOR']
const holderOnly: UserRole[] = ['ACCOUNT_HOLDER']
const adminOnly: UserRole[] = ['ADMIN']
const oversightRoles: UserRole[] = ['ADMIN', 'AUDITOR']

const navItems: NavItem[] = [
  { label: 'Overview', to: '/dashboard', icon: LayoutDashboard, roles: allRoles },
  { label: 'My accounts', to: '/accounts', icon: WalletCards, roles: holderOnly },
  { label: 'Deposit', to: '/deposit', icon: ArrowDownLeft, roles: holderOnly },
  { label: 'Withdraw', to: '/withdraw', icon: ArrowUpRight, roles: holderOnly },
  { label: 'Transfer', to: '/transfer', icon: ArrowLeftRight, roles: holderOnly },
  { label: 'Transactions', to: '/transactions', icon: ReceiptText, roles: allRoles },
  { label: 'Statements', to: '/statements', icon: ClipboardList, roles: allRoles },
  { label: 'Accounts', to: '/admin/accounts', icon: Users, roles: adminOnly },
  { label: 'Audit events', to: '/audit', icon: ShieldCheck, roles: oversightRoles },
]

const roleTitles: Record<UserRole, string> = {
  ADMIN: 'Administrator',
  ACCOUNT_HOLDER: 'Account holder',
  AUDITOR: 'Auditor',
}

const pageTitles: Record<string, string> = {
  '/dashboard': 'Overview',
  '/accounts': 'My accounts',
  '/deposit': 'Make a deposit',
  '/withdraw': 'Withdraw funds',
  '/transfer': 'Transfer money',
  '/transactions': 'Transactions',
  '/statements': 'Statements',
  '/admin/accounts': 'Account management',
  '/audit': 'Audit events',
}

export function AppShell() {
  const { user, signOut } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  if (!user) return null

  const visibleItems = navItems.filter((item) => item.roles.includes(user.role))
  const pageTitle =
    pageTitles[location.pathname] ??
    (location.pathname.startsWith('/statements/') ? 'Account statement' : 'LedgerLine')
  const initials = user.email.slice(0, 1).toUpperCase()

  function logout() {
    signOut()
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-shell">
      {menuOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
      <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
        <div className="brand-lockup">
          <div className="brand-symbol"><span /></div>
          <div>
            <span className="brand-name">ledgerline</span>
            <span className="brand-caption">FINANCIAL OPERATIONS</span>
          </div>
          <button className="mobile-close" onClick={() => setMenuOpen(false)} aria-label="Close menu">
            <X size={19} />
          </button>
        </div>

        <div className="workspace-label">WORKSPACE</div>
        <nav className="main-nav" aria-label="Main navigation">
          {visibleItems.map(({ label, to, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => `nav-link ${isActive ? 'nav-link-active' : ''}`}
              onClick={() => setMenuOpen(false)}
            >
              <Icon size={18} strokeWidth={1.8} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="security-note">
            <div className="security-icon"><BadgeCheck size={18} /></div>
            <div>
              <strong>Ledger-backed</strong>
              <span>Posted as journal entries</span>
            </div>
          </div>
          <button className="sidebar-logout" onClick={logout}>
            <LogOut size={17} />
            <span>Sign out</span>
          </button>
          <div className="sidebar-version">LEDGERLINE · INTERNAL LEDGER</div>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <button className="mobile-menu" onClick={() => setMenuOpen(true)} aria-label="Open navigation">
            <Menu size={21} />
          </button>
          <div className="breadcrumbs">
            <span>Workspace</span>
            <span className="crumb-slash">/</span>
            <strong>{pageTitle}</strong>
          </div>
          <div className="topbar-actions">
            <div className="secure-indicator"><span className="secure-dot" /> Authenticated session</div>
            <button className="profile-button" onClick={logout} title="Sign out">
              <span className="avatar">{initials}</span>
              <span className="profile-copy">
                <strong>{user.email}</strong>
                <small>{roleTitles[user.role]}</small>
              </span>
              <ChevronDown size={16} />
            </button>
          </div>
        </header>
        <main className="main-content"><Outlet /></main>
        <footer className="app-footer">
          <ProductDisclosure compact />
          <span>Internal ledger <Banknote size={14} /></span>
        </footer>
      </div>
    </div>
  )
}
