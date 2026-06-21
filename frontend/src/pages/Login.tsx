import React, { useState } from 'react';
import { api, setTokens } from '../services/api';
import { Mail, Lock, LogIn, AlertCircle } from 'lucide-react';

interface LoginProps {
  onLoginSuccess: (role: string, email: string) => void;
  onNavigateToRegister: () => void;
}

export const Login: React.FC<LoginProps> = ({ onLoginSuccess, onNavigateToRegister }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg('');
    setIsLoading(true);

    try {
      const response = await api.post('/auth/login', { email, password });
      
      // Store token credentials
      setTokens(response.access_token, response.refresh_token);
      
      // Decode JWT token directly on client (rough decode is safe for client role display)
      const tokenPayload = JSON.parse(atob(response.access_token.split('.')[1]));
      const role = tokenPayload.role || 'viewer';
      
      localStorage.setItem('user_role', role);
      localStorage.setItem('user_email', email);

      onLoginSuccess(role, email);
    } catch (err: any) {
      setErrorMsg(err.message || 'Login failed. Please check your credentials.');
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
          <h2 className="text-3xl font-bold tracking-tight glow-text">Welcome Back</h2>
          <p className="text-slate-400 text-sm">Sign in to your Natural Language Query platform</p>
        </div>

        {errorMsg && (
          <div className="flex gap-2.5 p-4 bg-rose-950/20 border border-rose-900/30 text-rose-400 text-sm rounded-xl animate-fade-in">
            <AlertCircle size={18} className="shrink-0 mt-0.5" />
            <p>{errorMsg}</p>
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
                placeholder="••••••••"
                className="input-field pl-11"
                disabled={isLoading}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full btn-primary py-3.5 mt-2"
          >
            {isLoading ? (
              <span className="flex items-center gap-2">
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                Signing in...
              </span>
            ) : (
              <>
                <LogIn size={18} />
                Sign In
              </>
            )}
          </button>
        </form>

        <div className="text-center pt-2">
          <p className="text-xs text-slate-400">
            Don't have an account?{' '}
            <button
              onClick={onNavigateToRegister}
              className="text-indigo-400 font-semibold hover:underline"
              disabled={isLoading}
            >
              Register here
            </button>
          </p>
        </div>
      </div>
    </div>
  );
};
