import { useState } from 'react'

const API = '/api'

export default function LoginPage({ onLogin }) {
  const [password, setPassword]   = useState('')
  const [error, setError]         = useState(null)
  const [loading, setLoading]     = useState(false)
  const [showPass, setShowPass]   = useState(false)

  const handleSubmit = async () => {
    if (!password.trim()) return
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      if (res.status === 401) { setError('Incorrect password.'); return }
      if (!res.ok) { setError('Something went wrong. Try again.'); return }
      const { token } = await res.json()
      localStorage.setItem('adaptiq_token', token)
      onLogin(token)
    } catch {
      setError('Could not reach the server.')
    } finally {
      setLoading(false)
    }
  }

  const handleKey = (e) => { if (e.key === 'Enter') handleSubmit() }

  return (
    <div style={styles.overlay}>
      {/* Ambient orbs */}
      <div style={{ position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0, overflow: 'hidden' }}>
        <div style={{ position: 'absolute', top: '-15%', left: '-8%', width: 700, height: 700, background: 'radial-gradient(circle, rgba(61,110,246,0.10) 0%, transparent 65%)', filter: 'blur(60px)' }} />
        <div style={{ position: 'absolute', bottom: '-20%', right: '-10%', width: 800, height: 800, background: 'radial-gradient(circle, rgba(139,92,246,0.09) 0%, transparent 65%)', filter: 'blur(60px)' }} />
      </div>

      <div style={styles.card}>
        {/* Logo */}
        <div style={styles.logo}>
          <img src="/AdaptIQ_Logo.png" alt="AdaptIQ" style={{ height: 44, width: 'auto' }} />
          <span style={styles.logoText}>
            Adapt<em style={styles.logoAccent}>IQ</em>
          </span>
        </div>

        <p style={styles.tagline}>Tailored Applications. Better Results.</p>

        <div style={styles.field}>
          <div style={styles.inputWrap}>
            <input
              type={showPass ? 'text' : 'password'}
              placeholder="Enter password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              onKeyDown={handleKey}
              style={styles.input}
              autoFocus
            />
            <button
              type="button"
              onClick={() => setShowPass(v => !v)}
              style={styles.eyeBtn}
              tabIndex={-1}
              aria-label={showPass ? 'Hide password' : 'Show password'}
            >
              {showPass ? (
                // Eye-off icon
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
                  <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
                  <line x1="1" y1="1" x2="23" y2="23"/>
                </svg>
              ) : (
                // Eye icon
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
              )}
            </button>
          </div>
        </div>

        {error && <p style={styles.error}>{error}</p>}

        <button
          onClick={handleSubmit}
          disabled={loading || !password.trim()}
          style={{ ...styles.btn, ...(loading || !password.trim() ? styles.btnDisabled : styles.btnActive) }}
        >
          {loading ? 'Signing in…' : 'Sign In →'}
        </button>
      </div>
    </div>
  )
}

const styles = {
  overlay: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--bg)',
    fontFamily: 'var(--font-body)',
    position: 'relative',
  },
  card: {
    position: 'relative',
    zIndex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 20,
    padding: '48px 40px',
    background: 'linear-gradient(145deg, #15172080 0%, var(--surface) 100%)',
    border: '1px solid var(--border)',
    borderRadius: 16,
    width: '100%',
    maxWidth: 380,
    boxShadow: '0 0 0 1px rgba(108,99,255,0.08), 0 24px 64px rgba(0,0,0,0.4)',
  },
  logo: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
  },
  logoText: {
    fontFamily: 'var(--font-display)',
    fontSize: 28,
    fontWeight: 700,
    letterSpacing: '-0.02em',
    color: 'var(--text-primary)',
    fontStyle: 'normal',
  },
  logoAccent: {
    fontStyle: 'normal',
    background: 'var(--accent-gradient)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    backgroundClip: 'text',
  },
  tagline: {
    fontSize: 13,
    color: 'var(--text-secondary)',
    letterSpacing: '0.02em',
    marginTop: -8,
  },
  field: {
    width: '100%',
    marginTop: 8,
  },
  inputWrap: {
    position: 'relative',
    width: '100%',
  },
  input: {
    width: '100%',
    padding: '12px 42px 12px 14px',
    background: 'var(--surface-raised)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-body)',
    fontSize: 15,
    outline: 'none',
    transition: 'border-color 0.2s, box-shadow 0.2s',
    boxSizing: 'border-box',
  },
  eyeBtn: {
    position: 'absolute',
    right: 12,
    top: '50%',
    transform: 'translateY(-50%)',
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    color: 'var(--text-muted)',
    padding: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  error: {
    fontSize: 13,
    color: 'var(--danger)',
    textAlign: 'center',
    marginTop: -8,
  },
  btn: {
    width: '100%',
    padding: '12px 0',
    borderRadius: 'var(--radius)',
    border: 'none',
    fontFamily: 'var(--font-body)',
    fontSize: 15,
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all 0.2s',
    letterSpacing: '0.01em',
  },
  btnActive: {
    background: 'var(--accent-gradient)',
    color: '#ffffff',
    boxShadow: '0 0 28px rgba(108,99,255,0.38), 0 4px 16px rgba(108,99,255,0.22)',
  },
  btnDisabled: {
    background: 'var(--surface-raised)',
    color: 'var(--text-muted)',
    cursor: 'not-allowed',
  },
}