import React, { useState } from 'react';
import { api } from '../services/api';
import { Mail, Lock, UserPlus, AlertCircle, CheckCircle, ShieldAlert } from 'lucide-react';

interface RegisterProps {
  onNavigateToLogin: () => void;
}

export const Register: React.FC<RegisterProps> = ({ onNavigateToLogin }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<'admin' | 'analyst' | 'viewer'>('viewer');
  const [statusMsg, setStatusMsg] = useState<{ type: 'error' | 'success' | ''; text: string }>({ type: '', text: '' });
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatusMsg({ type: '', text: '' });
    
    if (password.length < 8) {
      setStatusMsg({ type: 'error', text: 'Password must be at least 8 characters long.' });
      return;
    }

    setIsLoading(true);

    try {
      await api.post('/auth/register', { email, password, role });
      setStatusMsg({
        type: 'success',
        text: 'Account created successfully! Redirecting you to login...'
      });
      setTimeout(() => {
        onNavigateToLogin();
      }, 2000);
    } catch (err: any) {
      setStatusMsg({
        type: 'error',
        text: err.message || 'Registration failed. Please check your credentials.'
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center relative px-4">
      {/* Background glow effects */}
      <div className="glow-orb-1"></div>
      <div className="glow-orb-2"></div>

      <div className="w-full max-w-md glass-card p-8 space-y-6">
        <div className="text-center space-y-2">
          <h2 className="text-3xl font-bold tracking-tight glow-text">Create Account</h2>
          <p className="text-slate-400 text-sm">Register to begin querying databases with natural language</p>
        </div>

        {statusMsg.type && (
          <div 
            className={`flex gap-2.5 p-4 border rounded-xl text-sm animate-fade-in ${
              statusMsg.type === 'success' 
                ? 'bg-emerald-950/20 border-emerald-900/30 text-emerald-400' 
                : 'bg-rose-950/20 border-rose-900/30 text-rose-400'
            }`}
          >
            {statusMsg.type === 'success' 
              ? <CheckCircle size={18} className="shrink-0 mt-0.5" /> 
              : <AlertCircle size={18} className="shrink-0 mt-0.5" />}
            <p>{statusMsg.text}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Email Address</label>
            <div className="relative">
              <Mail size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="input-field pl-11"
                disabled={isLoading}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Password</label>
            <div className="relative">
              <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Min. 8 characters"
                className="input-field pl-11"
                disabled={isLoading}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Account Role</label>
            <div className="relative">
              <ShieldAlert size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as any)}
                className="input-field pl-11 appearance-none bg-slate-950 outline-none"
                disabled={isLoading}
              >
                <option value="viewer">Viewer (Read-only results visualizer)</option>
                <option value="analyst">Analyst (Upload, execute, and query databases)</option>
                <option value="admin">Administrator (Full audit control)</option>
              </select>
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading || statusMsg.type === 'success'}
            className="w-full btn-primary py-3.5 mt-2"
          >
            {isLoading ? (
              <span className="flex items-center gap-2">
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                Creating account...
              </span>
            ) : (
              <>
                <UserPlus size={18} />
                Register
              </>
            )}
          </button>
        </form>

        <div className="text-center pt-2">
          <p className="text-xs text-slate-400">
            Already have an account?{' '}
            <button
              onClick={onNavigateToLogin}
              className="text-indigo-400 font-semibold hover:underline"
              disabled={isLoading}
            >
              Sign In
            </button>
          </p>
        </div>
      </div>
    </div>
  );
};
