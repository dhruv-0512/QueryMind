import { useState } from 'react';
import { api } from '../services/api';
import { Mail, Lock, AlertCircle, CheckCircle, Terminal } from 'lucide-react';

export const Register = ({ onNavigateToLogin }) => {
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [role,     setRole]     = useState('viewer');
  const [statusMsg, setStatusMsg] = useState({ type: '', text: '' });
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatusMsg({ type: '', text: '' });

    if (password.length < 8) {
      setStatusMsg({ type: 'error', text: 'Password must be at least 8 characters.' });
      return;
    }

    setIsLoading(true);

    try {
      await api.post('/auth/register', { email, password, role });
      setStatusMsg({
        type: 'success',
        text: 'Account created. Redirecting to sign in…',
      });
      setTimeout(() => onNavigateToLogin(), 2000);
    } catch (err) {
      setStatusMsg({
        type: 'error',
        text: err.message || 'Registration failed. Please try again.',
      });
    } finally {
      setIsLoading(false);
    }
  };

  const inputIconStyle = {
    position: 'absolute',
    left: 11,
    top: '50%',
    transform: 'translateY(-50%)',
    color: 'var(--text-muted)',
    pointerEvents: 'none',
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
            Create account
          </h1>
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
            Register to start querying databases with natural language.
          </p>
        </div>

        {statusMsg.type && (
          <div
            className="animate-fade-in"
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 8,
              padding: '10px 12px',
              marginBottom: 16,
              background: statusMsg.type === 'success' ? 'var(--color-success-muted)' : 'var(--color-danger-muted)',
              border: `1px solid ${statusMsg.type === 'success' ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}`,
              borderRadius: 6,
              fontSize: '0.8125rem',
              color: statusMsg.type === 'success' ? 'var(--color-success)' : 'var(--color-danger)',
            }}
          >
            {statusMsg.type === 'success'
              ? <CheckCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
              : <AlertCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
            }
            <p>{statusMsg.text}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <label style={{ fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-secondary)' }}>
              Email
            </label>
            <div style={{ position: 'relative' }}>
              <Mail size={14} style={inputIconStyle} />
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
              <Lock size={14} style={inputIconStyle} />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Min. 8 characters"
                className="input-field"
                style={{ paddingLeft: 34 }}
                disabled={isLoading}
                autoComplete="new-password"
              />
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <label style={{ fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-secondary)' }}>
              Role
            </label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="input-field"
              style={{ appearance: 'none', cursor: 'pointer' }}
              disabled={isLoading}
            >
              <option value="viewer">Viewer — Read-only access</option>
              <option value="analyst">Analyst — Upload &amp; query databases</option>
              <option value="admin">Admin — Full system access</option>
            </select>
          </div>

          <button
            type="submit"
            disabled={isLoading || statusMsg.type === 'success'}
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
                Creating account…
              </span>
            ) : 'Create account'}
          </button>
        </form>

        <p style={{
          marginTop: 20,
          fontSize: '0.8rem',
          color: 'var(--text-muted)',
          textAlign: 'center',
        }}>
          Already have an account?{' '}
          <button
            onClick={onNavigateToLogin}
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
            Sign in
          </button>
        </p>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
};
