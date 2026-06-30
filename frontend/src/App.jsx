import { useState, useEffect, useCallback, useMemo, Suspense, lazy } from 'react';
import { Database, History, Shield, LogOut, Terminal, User, Menu, X } from 'lucide-react';
import { clearTokens, getTokens } from './services/api';

const Login = lazy(() => import('./pages/Login').then(m => ({ default: m.Login })));
const Register = lazy(() => import('./pages/Register').then(m => ({ default: m.Register })));
const Dashboard = lazy(() => import('./pages/Dashboard').then(m => ({ default: m.Dashboard })));
const QueryWorkspace = lazy(() => import('./pages/QueryWorkspace').then(m => ({ default: m.QueryWorkspace })));
const QueryHistory = lazy(() => import('./pages/QueryHistory').then(m => ({ default: m.QueryHistory })));
const Admin = lazy(() => import('./pages/Admin').then(m => ({ default: m.Admin })));

const App = () => {
  const [currentPage, setCurrentPage] = useState('login');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [userRole, setUserRole] = useState('viewer');
  const [userEmail, setUserEmail] = useState('');
  
  // Navigation states
  const [selectedDbId, setSelectedDbId] = useState(null);
  const [selectedDbName, setSelectedDbName] = useState(null);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    const { accessToken } = getTokens();
    const role = localStorage.getItem('user_role');
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

  const navigateToLogin = useCallback(() => setCurrentPage('login'), []);
  const navigateToRegister = useCallback(() => setCurrentPage('register'), []);

  const navItems = useMemo(() => {
    const items = [
      { id: 'dashboard', label: 'Databases', icon: <Database size={18} /> },
      { id: 'workspace', label: 'Query Workspace', icon: <Terminal size={18} /> },
      { id: 'history', label: 'Query History', icon: <History size={18} /> },
    ];
    if (userRole === 'admin') {
      items.push({ id: 'admin', label: 'Admin Panel', icon: <Shield size={18} /> });
    }
    return items;
  }, [userRole]);

  const fallback = (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0b10]">
      <div className="w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  if (!isAuthenticated) {
    return (
      <Suspense fallback={fallback}>
        {currentPage === 'register' ? (
          <Register onNavigateToLogin={navigateToLogin} />
        ) : (
          <Login onLoginSuccess={handleLoginSuccess} onNavigateToRegister={navigateToRegister} />
        )}
      </Suspense>
    );
  }

  return (
    <div className="min-h-screen flex flex-col md:flex-row relative">
      <div className="glow-orb-1"></div>
      <div className="glow-orb-2"></div>

      <header className="md:hidden bg-slate-950/80 backdrop-blur-md border-b border-slate-900 px-4 py-3 flex items-center justify-between z-50">
        <div className="flex items-center gap-2">
          <Terminal className="text-indigo-400" size={20} />
          <span className="font-bold text-sm tracking-tight text-white">QueryMind</span>
        </div>
        <button onClick={() => setIsMobileMenuOpen(v => !v)} className="text-slate-400 p-1 hover:text-white">
          {isMobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </header>

      <aside
        className={`w-64 border-r border-slate-900 bg-slate-950/90 backdrop-blur-lg flex flex-col justify-between shrink-0 z-40 fixed md:static inset-y-0 left-0 transform ${
          isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
        } md:translate-x-0 transition-transform duration-200 ease-in-out pt-14 md:pt-0`}
      >
        <div className="px-6 py-6 space-y-8">
          <div className="hidden md:flex items-center gap-3">
            <div className="p-2 bg-indigo-500/10 text-indigo-400 rounded-xl border border-indigo-500/20">
              <Terminal size={22} className="animate-pulse" />
            </div>
            <div>
              <h2 className="font-bold text-lg leading-none text-white tracking-tight">QueryMind</h2>
              <span className="text-[10px] font-semibold text-slate-500 tracking-widest uppercase">Platform</span>
            </div>
          </div>

          <nav className="space-y-1">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => {
                  setCurrentPage(item.id);
                  setIsMobileMenuOpen(false);
                }}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold transition ${
                  currentPage === item.id
                    ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/10'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/40'
                }`}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </nav>
        </div>

        <div className="p-4 border-t border-slate-900 space-y-3 bg-slate-950/50">
          <div className="flex items-center gap-3 p-2 rounded-xl bg-slate-900/20">
            <div className="w-9 h-9 bg-slate-800 rounded-lg flex items-center justify-center text-slate-300">
              <User size={16} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold text-slate-300 truncate" title={userEmail}>
                {userEmail}
              </p>
              <span className={`inline-block text-[9px] font-bold px-1.5 py-0.5 rounded uppercase mt-0.5 ${
                userRole === 'admin'
                  ? 'text-indigo-400 bg-indigo-500/10'
                  : userRole === 'analyst'
                    ? 'text-purple-400 bg-purple-500/10'
                    : 'text-slate-500 bg-slate-500/10'
              }`}>
                {userRole}
              </span>
            </div>
          </div>

          <button
            onClick={handleLogout}
            className="w-full flex items-center justify-center gap-2 py-2.5 bg-rose-500/5 hover:bg-rose-500/10 text-rose-400 border border-rose-500/10 hover:border-rose-500/20 rounded-xl text-xs font-semibold transition"
          >
            <LogOut size={14} />
            Sign Out
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto px-4 md:px-8 py-8 md:py-10 max-w-7xl mx-auto w-full md:pl-8 pt-20 md:pt-10">
        <Suspense fallback={fallback}>
          {currentPage === 'dashboard' && <Dashboard userRole={userRole} onSelectDatabase={handleSelectDatabase} />}
          {currentPage === 'workspace' && <QueryWorkspace selectedDbId={selectedDbId} selectedDbName={selectedDbName} />}
          {currentPage === 'history' && <QueryHistory />}
          {currentPage === 'admin' && userRole === 'admin' && <Admin />}
          {currentPage === 'admin' && userRole !== 'admin' && <Dashboard userRole={userRole} onSelectDatabase={handleSelectDatabase} />}
        </Suspense>
      </main>
    </div>
  );
};

export default App;
