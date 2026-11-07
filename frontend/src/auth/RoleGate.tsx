import { Navigate, Outlet, useLocation } from 'react-router-dom'
import type { UserRole } from '../types/api'
import { useAuth } from './AuthContext'

export function RequireAuth() {
  const { user } = useAuth()
  const location = useLocation()
  return user ? <Outlet /> : <Navigate to="/login" replace state={{ from: location }} />
}

export function RequireRole({ roles }: { roles: UserRole[] }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (!roles.includes(user.role)) return <Navigate to="/dashboard" replace />
  return <Outlet />
}
