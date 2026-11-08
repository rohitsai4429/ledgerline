import { render, screen } from '@testing-library/react'
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { useAuth } from './AuthContext'
import { RequireRole } from './RoleGate'

vi.mock('./AuthContext', () => ({ useAuth: vi.fn() }))

const user = {
  id: 'user-id',
  email: 'user@example.com',
  role: 'AUDITOR' as const,
  status: 'ACTIVE' as const,
  created_at: '2026-01-01T00:00:00Z',
}

function renderAdminRoute() {
  return render(
    <MemoryRouter initialEntries={['/admin']}>
      <Routes>
        <Route path="/dashboard" element={<p>Overview</p>} />
        <Route element={<RequireRole roles={['ADMIN']} />}>
          <Route path="/admin" element={<Outlet />}>
            <Route index element={<p>Administrator controls</p>} />
          </Route>
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('role gates', () => {
  it('redirects an auditor away from administrator controls', () => {
    vi.mocked(useAuth).mockReturnValue({
      user,
      busy: false,
      signIn: vi.fn(),
      startGoogleSignIn: vi.fn(),
      verifyOtp: vi.fn(),
      signOut: vi.fn(),
    })
    renderAdminRoute()

    expect(screen.getByText('Overview')).toBeInTheDocument()
    expect(screen.queryByText('Administrator controls')).not.toBeInTheDocument()
  })
})
