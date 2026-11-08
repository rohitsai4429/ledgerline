import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowRight, BadgeCheck, BookOpenCheck, LockKeyhole } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { authApi, type GoogleStartResponse, type OtpChallenge } from '../api/auth'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Alert, Button, FieldError, ProductDisclosure } from '../components/ui'

const loginSchema = z.object({
  email: z.email('Enter a valid email address'),
  password: z.string().min(1, 'Enter your password'),
})

const registerSchema = z.object({
  email: z.email('Enter a valid email address'),
  password: z.string().min(12, 'Use at least 12 characters').max(128, 'Password must be 128 characters or fewer'),
  confirmPassword: z.string(),
}).refine((value) => value.password === value.confirmPassword, {
  path: ['confirmPassword'],
  message: 'Passwords do not match',
})

type LoginValues = z.infer<typeof loginSchema>
type RegisterValues = z.infer<typeof registerSchema>

interface GoogleCredentialResponse {
  credential: string
}

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (options: {
            client_id: string
            callback: (response: GoogleCredentialResponse) => void
          }) => void
          renderButton: (element: HTMLElement, options: { theme: string; size: string; width: number }) => void
        }
      }
    }
  }
}

function isOtpChallenge(response: GoogleStartResponse): response is OtpChallenge {
  return response.status === 'OTP_REQUIRED'
}

function AuthFrame({ children, mode }: { children: React.ReactNode; mode: 'login' | 'register' }) {
  return (
    <main className="auth-page">
      <section className="auth-aside">
        <div className="brand-lockup auth-brand">
          <div className="brand-symbol"><span /></div>
          <div><span className="brand-name">ledgerline</span><span className="brand-caption">FINANCIAL OPERATIONS</span></div>
        </div>
        <div className="auth-story">
          <p className="auth-overline"><span /> TRUST, RECONCILED</p>
          <h1>Every movement.<br /><em>Accounted for.</em></h1>
          <p className="auth-story-copy">
            A clearer view of your money, grounded in a ledger designed for accuracy and accountability.
          </p>
          <div className="auth-proof">
            <div className="proof-icon"><BookOpenCheck size={18} /></div>
            <div><strong>Internal ledger platform</strong><span>Reliable movement with balanced accounting records.</span></div>
          </div>
        </div>
        <div className="auth-footer-copy">LEDGERLINE FINANCIAL SERVICES <span>·</span> SECURE ACCESS</div>
      </section>
      <section className="auth-main">
        <div className="auth-mobile-brand">
          <div className="brand-symbol"><span /></div><span className="brand-name">ledgerline</span>
        </div>
        <div className="auth-card">
          <div className="auth-card-icon">{mode === 'login' ? <LockKeyhole size={20} /> : <BadgeCheck size={20} />}</div>
          <p className="eyebrow">{mode === 'login' ? 'WELCOME BACK' : 'GET STARTED'}</p>
          <h2>{mode === 'login' ? 'Sign in to LedgerLine' : 'Create your account'}</h2>
          <p className="auth-subtitle">
            {mode === 'login'
              ? 'Access your accounts and recent activity.'
              : 'Registration creates an account-holder profile.'}
          </p>
          {children}
          <div className="auth-switch">
            {mode === 'login' ? (
              <>New to LedgerLine? <Link to="/register">Create an account <ArrowRight size={14} /></Link></>
            ) : (
              <>Already registered? <Link to="/login">Sign in <ArrowRight size={14} /></Link></>
            )}
          </div>
          <div className="auth-security"><LockKeyhole size={13} /> API requests use short-lived bearer authentication.</div>
          <ProductDisclosure compact />
        </div>
      </section>
    </main>
  )
}

function GoogleSignInButton({
  onCredential,
  disabled,
}: {
  onCredential: (credential: string) => void
  disabled: boolean
}) {
  const buttonRef = useRef<HTMLDivElement>(null)
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID

  useEffect(() => {
    if (!clientId || !buttonRef.current) return
    let active = true
    const renderGoogleButton = () => {
      if (!active || !buttonRef.current || !window.google) return
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (response) => {
          if (response.credential) onCredential(response.credential)
        },
      })
      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: 'outline',
        size: 'large',
        width: Math.max(220, Math.floor(buttonRef.current.clientWidth)),
      })
    }

    const existingScript = document.querySelector<HTMLScriptElement>(
      'script[src="https://accounts.google.com/gsi/client"]',
    )
    if (window.google) {
      renderGoogleButton()
    } else if (existingScript) {
      existingScript.addEventListener('load', renderGoogleButton, { once: true })
    } else {
      const script = document.createElement('script')
      script.src = 'https://accounts.google.com/gsi/client'
      script.async = true
      script.defer = true
      script.addEventListener('load', renderGoogleButton, { once: true })
      document.head.appendChild(script)
    }
    return () => {
      active = false
    }
  }, [clientId, onCredential])

  if (!clientId) {
    return <p className="auth-subtitle">Google sign-in is not configured in this environment.</p>
  }
  return (
    <div
      ref={buttonRef}
      aria-label="Google sign-in"
      aria-disabled={disabled}
      style={disabled ? { opacity: 0.6, pointerEvents: 'none' } : undefined}
    />
  )
}

function OtpPanel({
  challenge,
  onBack,
  onVerified,
}: {
  challenge: OtpChallenge
  onBack: () => void
  onVerified: () => void
}) {
  const { busy, verifyOtp } = useAuth()
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [secondsToResend, setSecondsToResend] = useState(challenge.resend_after_seconds)
  const [secondsToExpiry, setSecondsToExpiry] = useState(challenge.expires_in_seconds)
  const [resending, setResending] = useState(false)

  useEffect(() => {
    const timer = window.setInterval(() => {
      setSecondsToResend((seconds) => Math.max(0, seconds - 1))
      setSecondsToExpiry((seconds) => Math.max(0, seconds - 1))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [challenge.challenge_id])

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    try {
      await verifyOtp(challenge.challenge_id, code)
      onVerified()
    } catch (verificationError) {
      setError(verificationError instanceof ApiError
        ? verificationError.message
        : 'Verification could not be completed.')
    }
  }

  async function resend() {
    setError('')
    setResending(true)
    try {
      const response = await authApi.resendOtp(challenge.challenge_id)
      setSecondsToResend(response.retry_after_seconds)
      setSecondsToExpiry(300)
      setCode('')
    } catch (resendError) {
      setError(resendError instanceof ApiError ? resendError.message : 'A new code could not be sent.')
    } finally {
      setResending(false)
    }
  }

  return (
    <form className="auth-form" onSubmit={submit}>
      <Alert tone="info">{challenge.message}</Alert>
      {error && <Alert>{error}</Alert>}
      {secondsToExpiry === 0 && <Alert>The verification code has expired. Request a new code to continue.</Alert>}
      <label className="form-field">
        <span>Email verification code</span>
        <input
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]{8}"
          maxLength={8}
          value={code}
          onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 8))}
          placeholder="8-digit code"
          aria-label="Email verification code"
        />
      </label>
      <Button type="submit" className="auth-submit" disabled={busy || code.length !== 8 || secondsToExpiry === 0}>
        {busy ? 'Verifying…' : 'Verify and continue'} <ArrowRight size={16} />
      </Button>
      <Button
        type="button"
        variant="secondary"
        disabled={resending || secondsToResend > 0}
        onClick={resend}
      >
        {resending ? 'Sending…' : secondsToResend > 0 ? `Resend code in ${secondsToResend}s` : 'Resend code'}
      </Button>
      <Button type="button" variant="quiet" onClick={onBack}>Back to sign in</Button>
    </form>
  )
}

export function LoginPage() {
  const { user, signIn, startGoogleSignIn, busy } = useAuth()
  const navigate = useNavigate()
  const [serverError, setServerError] = useState('')
  const [challenge, setChallenge] = useState<OtpChallenge | null>(null)
  const [googleCredential, setGoogleCredential] = useState('')
  const [linkConfirmation, setLinkConfirmation] = useState(false)
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) })

  const handleGoogleCredential = useCallback(async (credential: string) => {
    setServerError('')
    setGoogleCredential(credential)
    try {
      const response = await startGoogleSignIn(credential)
      if (isOtpChallenge(response)) setChallenge(response)
      else setLinkConfirmation(true)
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : 'Google sign-in could not be completed.')
    }
  }, [startGoogleSignIn])

  if (user) return <Navigate to="/dashboard" replace />

  async function submit(values: LoginValues) {
    setServerError('')
    try {
      setChallenge(await signIn(values))
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : 'Sign in could not be completed.')
    }
  }

  async function confirmGoogleLink() {
    setServerError('')
    try {
      const response = await startGoogleSignIn(googleCredential, true)
      if (isOtpChallenge(response)) setChallenge(response)
      else setLinkConfirmation(true)
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : 'Google account linking could not be completed.')
    }
  }

  return (
    <AuthFrame mode="login">
      {challenge ? (
        <OtpPanel
          challenge={challenge}
          onBack={() => { setChallenge(null); setLinkConfirmation(false) }}
          onVerified={() => navigate('/dashboard', { replace: true })}
        />
      ) : (
        <>
          <form className="auth-form" onSubmit={handleSubmit(submit)} noValidate>
            {serverError && <Alert>{serverError}</Alert>}
            {linkConfirmation && (
              <>
                <Alert tone="info">This Google email matches an existing account. Confirm linking, then verify the emailed code.</Alert>
                <Button type="button" className="auth-submit" disabled={busy} onClick={confirmGoogleLink}>
                  Confirm account linking
                </Button>
              </>
            )}
            <label className="form-field">
              <span>Email address</span>
              <input type="email" autoComplete="email" placeholder="you@company.com" {...register('email')} />
              <FieldError>{errors.email?.message}</FieldError>
            </label>
            <label className="form-field">
              <span>Password</span>
              <input type="password" autoComplete="current-password" placeholder="Enter your password" {...register('password')} />
              <FieldError>{errors.password?.message}</FieldError>
            </label>
            <Button type="submit" className="auth-submit" disabled={busy}>
              {busy ? 'Signing in…' : 'Sign in securely'} <ArrowRight size={16} />
            </Button>
          </form>
          <GoogleSignInButton onCredential={handleGoogleCredential} disabled={busy} />
        </>
      )}
    </AuthFrame>
  )
}

export function RegisterPage() {
  const { user } = useAuth()
  const [serverError, setServerError] = useState('')
  const [challenge, setChallenge] = useState<OtpChallenge | null>(null)
  const [googleCredential, setGoogleCredential] = useState('')
  const [googleLinkConfirmation, setGoogleLinkConfirmation] = useState(false)
  const [googleBusy, setGoogleBusy] = useState(false)
  const navigate = useNavigate()
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) })

  async function submit(values: RegisterValues) {
    setServerError('')
    try {
      setChallenge(await authApi.register({
        email: values.email,
        password: values.password,
      }))
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : 'Registration could not be completed.')
    }
  }

  const handleGoogleCredential = useCallback(async (
    credential: string,
    confirmLink = false,
  ) => {
    setServerError('')
    setGoogleCredential(credential)
    setGoogleBusy(true)
    try {
      const response = await authApi.google(credential, confirmLink)
      if (isOtpChallenge(response)) {
        setChallenge(response)
        setGoogleLinkConfirmation(false)
      } else {
        setGoogleLinkConfirmation(true)
      }
    } catch (error) {
      setServerError(error instanceof ApiError ? error.message : 'Google sign-in could not be completed.')
    } finally {
      setGoogleBusy(false)
    }
  }, [])

  if (user) return <Navigate to="/dashboard" replace />

  return (
    <AuthFrame mode="register">
      {challenge ? (
        <OtpPanel
          challenge={challenge}
          onBack={() => setChallenge(null)}
          onVerified={() => navigate('/dashboard', { replace: true })}
        />
      ) : (
        <>
          <form className="auth-form" onSubmit={handleSubmit(submit)} noValidate>
            {serverError && <Alert>{serverError}</Alert>}
            {googleLinkConfirmation && (
              <>
                <Alert tone="info">This Google email matches an existing account. Confirm linking, then verify the emailed code.</Alert>
                <Button
                  type="button"
                  className="auth-submit"
                  disabled={googleBusy}
                  onClick={() => void handleGoogleCredential(googleCredential, true)}
                >
                  Confirm account linking
                </Button>
              </>
            )}
            <label className="form-field">
              <span>Email address</span>
              <input type="email" autoComplete="email" placeholder="you@company.com" {...register('email')} />
              <FieldError>{errors.email?.message}</FieldError>
            </label>
            <label className="form-field">
              <span>Password <small>At least 12 characters</small></span>
              <input type="password" autoComplete="new-password" placeholder="Create a strong password" {...register('password')} />
              <FieldError>{errors.password?.message}</FieldError>
            </label>
            <label className="form-field">
              <span>Confirm password</span>
              <input type="password" autoComplete="new-password" placeholder="Enter it again" {...register('confirmPassword')} />
              <FieldError>{errors.confirmPassword?.message}</FieldError>
            </label>
            <Button type="submit" className="auth-submit" disabled={isSubmitting}>
              {isSubmitting ? 'Creating account…' : 'Create account'} <ArrowRight size={16} />
            </Button>
            <p className="role-notice">New registrations receive the account-holder role. Privileged roles are assigned outside public registration.</p>
          </form>
          <GoogleSignInButton
            onCredential={handleGoogleCredential}
            disabled={isSubmitting || googleBusy}
          />
        </>
      )}
    </AuthFrame>
  )
}
