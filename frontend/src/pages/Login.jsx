import { useState } from 'react';
import { api, setTokens } from '../services/api';
import { Mail, Lock, AlertCircle, Terminal } from 'lucide-react';

/*
  Why: Old login had:
    - Two floating glow orbs behind the form (animated blurs)
    - "Welcome Back" in gradient glow-text
    - glass-card with backdrop-blur on the form container
    - UPPERCASE tracking-wider labels on every input
    - A gradient indigo→purple button with a box-shadow glow

  Fix:
    - Plain dark background, no decorative noise behind auth forms
    - Brand mark in the top of the card — simple wordmark + icon
    - Clean form with standard labels (not uppercase)
    - Flat solid indigo button
    - Error state as a simple bordered row, not a rose "alert card"
*/
export const Login = ({ onLoginSuccess, onNavigateToRegister }) => {
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setIsLoading(true);

    try {
      const response = await api.post('/auth/login', { email, password });

      setTokens(response.access_token, response.refresh_token);

      const tokenPayload = JSON.parse(atob(response.access_token.split('.')[1]));
      const role = tokenPayload.role || 'viewer';

      localStorage.setItem('user_role', role);
      localStorage.setItem('user_email', email);

      onLoginSuccess(role, email);
    } catch (err) {
      setErrorMsg(err.message || 'Login failed. Please check your credentials.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--bg-base)',
        padding: '24px 16px',
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 380,
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-default)',
          borderRadius: 10,
          padding: '36px 32px 32px',
        }}
      >
        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 14 }}>
            <Terminal size={14} style={{ color: 'var(--accent)' }} />
            <span style={{
              fontSize: '0.75rem',
              fontWeight: 600,
              letterSpacing: '0.02em',
              color: 'var(--text-muted)',
            }}>
              QueryMind
            </span>
          </div>
          <h1 style={{
            fontSize: '1.25rem',
            fontWeight: 700,
            letterSpacing: '-0.025em',
            color: 'var(--text-primary)',
            marginBottom: 5,
          }}>
            Sign in
          </h1>
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
            Natural language queries over your databases.
          </p>
        </div>

        {errorMsg && (
          <div
            className="animate-fade-in"
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 8,
              padding: '10px 12px',
              marginBottom: 16,
              background: 'var(--color-danger-muted)',
              border: '1px solid rgba(239,68,68,0.2)',
              borderRadius: 6,
              fontSize: '0.8125rem',
              color: 'var(--color-danger)',
            }}
          >
            <AlertCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
            <p>{errorMsg}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <label style={{ fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-secondary)' }}>
              Email
            </label>
            <div style={{ position: 'relative' }}>
              <Mail
                size={14}
                style={{
                  position: 'absolute',
                  left: 11,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--text-muted)',
                  pointerEvents: 'none',
                }}
              />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="input-field"
                style={{ paddingLeft: 34 }}
                disabled={isLoading}
                autoComplete="email"
              />
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <label style={{ fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-secondary)' }}>
              Password
            </label>
            <div style={{ position: 'relative' }}>
              <Lock
                size={14}
                style={{
                  position: 'absolute',
                  left: 11,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--text-muted)',
                  pointerEvents: 'none',
                }}
              />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="input-field"
                style={{ paddingLeft: 34 }}
                disabled={isLoading}
                autoComplete="current-password"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="btn-primary"
            style={{ width: '100%', height: 38, marginTop: 4, fontSize: '0.875rem' }}
          >
            {isLoading ? (
              <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{
                  width: 14,
                  height: 14,
                  border: '2px solid rgba(255,255,255,0.3)',
                  borderTopColor: 'white',
                  borderRadius: '50%',
                  animation: 'spin 0.7s linear infinite',
                  flexShrink: 0,
                }} />
                Signing in…
              </span>
            ) : 'Sign in'}
          </button>
        </form>

        <p style={{
          marginTop: 20,
          fontSize: '0.8rem',
          color: 'var(--text-muted)',
          textAlign: 'center',
        }}>
          No account?{' '}
          <button
            onClick={onNavigateToRegister}
            disabled={isLoading}
            style={{
              color: 'var(--accent)',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: 'inherit',
              padding: 0,
            }}
          >
            Register
          </button>
        </p>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
};
