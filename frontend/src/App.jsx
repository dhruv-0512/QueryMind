import { useState, useEffect, useCallback, useMemo, Suspense, lazy } from 'react';
import { Database, History, Shield, LogOut, Terminal, User, Menu, X } from 'lucide-react';
import { clearTokens, getTokens } from './services/api';

const Login         = lazy(() => import('./pages/Login').then(m => ({ default: m.Login })));
const Register      = lazy(() => import('./pages/Register').then(m => ({ default: m.Register })));
const Dashboard     = lazy(() => import('./pages/Dashboard').then(m => ({ default: m.Dashboard })));
const QueryWorkspace = lazy(() => import('./pages/QueryWorkspace').then(m => ({ default: m.QueryWorkspace })));
const QueryHistory  = lazy(() => import('./pages/QueryHistory').then(m => ({ default: m.QueryHistory })));
const Admin         = lazy(() => import('./pages/Admin').then(m => ({ default: m.Admin })));

/* 
  Why: Old fallback had a large indigo spinner that visually "announced" itself.
  Fix: Minimal inline indicator — barely visible, doesn't fight for attention.
*/
const PageFallback = () => (
  <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--bg-base)' }}>
    <div
      style={{
        width: 20,
        height: 20,
        border: '2px solid var(--border-strong)',
        borderTopColor: 'var(--accent)',
        borderRadius: '50%',
        animation: 'spin 0.7s linear infinite',
      }}
    />
    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
  </div>
);

const App = () => {
  const [currentPage, setCurrentPage]     = useState('login');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [userRole, setUserRole]           = useState('viewer');
  const [userEmail, setUserEmail]         = useState('');

  const [selectedDbId, setSelectedDbId]     = useState(null);
  const [selectedDbName, setSelectedDbName] = useState(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    const { accessToken } = getTokens();
    const role  = localStorage.getItem('user_role');
    const email = localStorage.getItem('user_email');

    if (accessToken && role && email) {
      setIsAuthenticated(true);
      setUserRole(role);
      setUserEmail(email);
      setCurrentPage('dashboard');
    } else {
      clearTokens();
      setIsAuthenticated(false);
      setCurrentPage('login');
    }

    const handleAuthFailure = () => {
      clearTokens();
      setIsAuthenticated(false);
      setCurrentPage('login');
    };

    window.addEventListener('auth_failed', handleAuthFailure);
    return () => window.removeEventListener('auth_failed', handleAuthFailure);
  }, []);

  const handleLoginSuccess = useCallback((role, email) => {
    setIsAuthenticated(true);
    setUserRole(role);
    setUserEmail(email);
    setCurrentPage('dashboard');
  }, []);

  const handleLogout = useCallback(() => {
    clearTokens();
    setIsAuthenticated(false);
    setUserRole('viewer');
    setUserEmail('');
    setSelectedDbId(null);
    setSelectedDbName(null);
    setCurrentPage('login');
  }, []);

  const handleSelectDatabase = useCallback((id, name) => {
    setSelectedDbId(id);
    setSelectedDbName(name);
    setCurrentPage('workspace');
  }, []);

  const navigateToLogin    = useCallback(() => setCurrentPage('login'), []);
  const navigateToRegister = useCallback(() => setCurrentPage('register'), []);

  const navItems = useMemo(() => {
    const items = [
      { id: 'dashboard',  label: 'Databases',       icon: <Database size={16} /> },
      { id: 'workspace',  label: 'Query Workspace',  icon: <Terminal size={16} /> },
      { id: 'history',    label: 'Query History',    icon: <History size={16} /> },
    ];
    if (userRole === 'admin') {
      items.push({ id: 'admin', label: 'Admin Panel', icon: <Shield size={16} /> });
    }
    return items;
  }, [userRole]);

  const roleBadgeColor = {
    admin:   { color: '#6366f1' },
    analyst: { color: '#71717a' },
    viewer:  { color: '#71717a' },
  }[userRole] ?? { color: '#71717a' };

  if (!isAuthenticated) {
    return (
      <Suspense fallback={<PageFallback />}>
        {currentPage === 'register'
          ? <Register onNavigateToLogin={navigateToLogin} />
          : <Login onLoginSuccess={handleLoginSuccess} onNavigateToRegister={navigateToRegister} />
        }
      </Suspense>
    );
  }

  /*
    Why (sidebar): Old sidebar had:
      - animate-pulse on the Terminal logo icon
      - rounded-xl nav buttons with an indigo bg highlight on active
      - glassmorphism backdrop-blur + bg-slate-950/90
      - "Platform" label in tracking-widest uppercase under the logo
      - User card with rounded-xl bg-slate-900/20 padding
      - Logout button styled as a rose danger ghost

    Fix: Clean sidebar using border-right separation. Nav items use a simple
    left-border active indicator (like VS Code, Linear's sidebar). No color 
    fills. User info is just text. Logout is a plain icon-text row.
  */
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-base)' }}
         className="md:flex-row">

      {/* ── Mobile Top Bar ── */}
      <header
        className="md:hidden flex items-center justify-between px-4 py-3 z-50"
        style={{
          background: 'var(--bg-surface)',
          borderBottom: '1px solid var(--border-subtle)',
          position: 'sticky',
          top: 0,
        }}
      >
        <div className="flex items-center gap-2">
          <Terminal size={17} style={{ color: 'var(--accent)' }} />
          <span style={{ fontWeight: 700, fontSize: '0.9rem', letterSpacing: '-0.01em', color: 'var(--text-primary)' }}>
            QueryMind
          </span>
        </div>
        <button
          onClick={() => setIsMobileMenuOpen(v => !v)}
          style={{ color: 'var(--text-muted)', padding: 4, lineHeight: 0 }}
          aria-label="Toggle menu"
        >
          {isMobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </header>

      {/* ── Sidebar ── */}
      <aside
        style={{
          width: 224,
          background: 'var(--bg-surface)',
          borderRight: '1px solid var(--border-subtle)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          flexShrink: 0,
          zIndex: 40,
          position: 'fixed',
          top: 0,
          bottom: 0,
          left: 0,
          paddingTop: '0',
          transform: isMobileMenuOpen ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform 0.2s ease',
        }}
        className="md:static md:translate-x-0 md:pt-0"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
          {/* Logo */}
          <div
            className="hidden md:flex items-center gap-2.5 px-5 py-5"
            style={{ borderBottom: '1px solid var(--border-subtle)' }}
          >
            <Terminal size={17} style={{ color: 'var(--accent)' }} />
            <span style={{
              fontWeight: 700,
              fontSize: '0.9rem',
              letterSpacing: '-0.015em',
              color: 'var(--text-primary)',
            }}>
              QueryMind
            </span>
          </div>

          {/* Nav */}
          <nav style={{ padding: '8px 0', display: 'flex', flexDirection: 'column' }}>
            {navItems.map((item) => {
              const isActive = currentPage === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    setCurrentPage(item.id);
                    setIsMobileMenuOpen(false);
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 9,
                    padding: '7px 20px',
                    fontSize: '0.8125rem',
                    fontWeight: isActive ? 600 : 400,
                    color: isActive ? 'var(--text-primary)' : 'var(--text-muted)',
                    background: isActive ? 'var(--bg-raised)' : 'transparent',
                    border: 'none',
                    borderLeft: isActive ? '2px solid var(--accent)' : '2px solid transparent',
                    cursor: 'pointer',
                    textAlign: 'left',
                    width: '100%',
                    transition: 'color 0.15s, background 0.15s',
                    outline: 'none',
                  }}
                  onMouseEnter={e => {
                    if (!isActive) {
                      e.currentTarget.style.color = 'var(--text-secondary)';
                      e.currentTarget.style.background = 'var(--bg-raised)';
                    }
                  }}
                  onMouseLeave={e => {
                    if (!isActive) {
                      e.currentTarget.style.color = 'var(--text-muted)';
                      e.currentTarget.style.background = 'transparent';
                    }
                  }}
                >
                  {item.icon}
                  {item.label}
                </button>
              );
            })}
          </nav>
        </div>

        {/* User footer */}
        <div style={{ padding: '12px 20px 16px', borderTop: '1px solid var(--border-subtle)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 10 }}>
            <div style={{
              width: 28,
              height: 28,
              background: 'var(--bg-overlay)',
              border: '1px solid var(--border-default)',
              borderRadius: 6,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}>
              <User size={14} style={{ color: 'var(--text-muted)' }} />
            </div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <p style={{
                fontSize: '0.75rem',
                fontWeight: 500,
                color: 'var(--text-secondary)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }} title={userEmail}>
                {userEmail}
              </p>
              <p style={{
                fontSize: '0.65rem',
                fontWeight: 600,
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
                color: roleBadgeColor.color,
                marginTop: 1,
              }}>
                {userRole}
              </p>
            </div>
          </div>

          <button
            onClick={handleLogout}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 7,
              fontSize: '0.8rem',
              color: 'var(--text-muted)',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: '4px 0',
              transition: 'color 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--color-danger)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}
          >
            <LogOut size={13} />
            Sign out
          </button>
        </div>
      </aside>

      {/* ── Main ── */}
      <main
        className="flex-1 overflow-y-auto"
        style={{
          paddingLeft: 0,
          paddingTop: 0,
          marginLeft: 0,
        }}
      >
        {/* Offset for fixed sidebar on desktop */}
        <div
          className="md:pl-56"
          style={{ minHeight: '100vh', paddingTop: '2px' }}
        >
          <div style={{ maxWidth: 1100, margin: '0 auto', padding: '40px 36px' }}
               className="px-4 py-8 md:px-9 md:py-10">
            <Suspense fallback={null}>
              {currentPage === 'dashboard'  && <Dashboard userRole={userRole} onSelectDatabase={handleSelectDatabase} />}
              {currentPage === 'workspace'  && <QueryWorkspace selectedDbId={selectedDbId} selectedDbName={selectedDbName} />}
              {currentPage === 'history'    && <QueryHistory />}
              {currentPage === 'admin'      && userRole === 'admin' && <Admin />}
              {currentPage === 'admin'      && userRole !== 'admin' && <Dashboard userRole={userRole} onSelectDatabase={handleSelectDatabase} />}
            </Suspense>
          </div>
        </div>
      </main>
    </div>
  );
};

export default App;
