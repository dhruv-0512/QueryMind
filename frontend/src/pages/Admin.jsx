import { useState, useEffect } from 'react';
import { Shield, Users, ScrollText, BarChart3, Clock, HelpCircle, HardDrive, RefreshCw } from 'lucide-react';
import { api } from '../services/api';

export const Admin = () => {
  const [users, setUsers] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [stats, setStats] = useState(null);
  
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');
  const [activeSubTab, setActiveSubTab] = useState('users');

  useEffect(() => {
    const fetchAdminData = async () => {
      setIsLoading(true);
      setErrorMsg('');
      try {
        const [usersData, logsData, statsData] = await Promise.all([
          api.get('/admin/users'),
          api.get('/admin/audit-logs'),
          api.get('/admin/stats')
        ]);
        setUsers(usersData);
        setAuditLogs(logsData);
        setStats(statsData);
      } catch (err) {
        setErrorMsg(err.message || 'Failed to retrieve admin control dashboard logs.');
      } finally {
        setIsLoading(false);
      }
    };
    fetchAdminData();
  }, []);

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-3xl font-bold glow-text flex items-center gap-2">
          <Shield size={28} className="text-indigo-400" />
          Admin Dashboard
        </h1>
        <p className="text-slate-400 text-sm mt-1">
          Monitor users, view system events, and track query pipeline execution metrics.
        </p>
      </div>

      {errorMsg && (
        <div className="p-4 bg-rose-950/20 border border-rose-900/30 text-rose-400 rounded-xl text-sm">
          {errorMsg}
        </div>
      )}

      {isLoading ? (
        <div className="flex flex-col items-center justify-center p-20 space-y-4">
          <RefreshCw className="w-10 h-10 text-indigo-400 animate-spin" />
          <p className="text-slate-400 text-xs">Assembling administrative reports...</p>
        </div>
      ) : (
        <div className="space-y-8">
          {/* Stats Widgets */}
          {stats && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="p-5 bg-slate-900/30 border border-slate-800 rounded-2xl space-y-2">
                <div className="flex justify-between items-center text-indigo-400">
                  <span className="text-xs uppercase font-bold text-slate-500">Total Queries</span>
                  <HelpCircle size={18} />
                </div>
                <p className="text-2xl font-bold text-slate-200">{stats.total_queries}</p>
              </div>

              <div className="p-5 bg-slate-900/30 border border-slate-800 rounded-2xl space-y-2">
                <div className="flex justify-between items-center text-purple-400">
                  <span className="text-xs uppercase font-bold text-slate-500">Cache Hits</span>
                  <HardDrive size={18} />
                </div>
                <p className="text-2xl font-bold text-slate-200">{stats.cache_hits}</p>
              </div>

              <div className="p-5 bg-slate-900/30 border border-slate-800 rounded-2xl space-y-2">
                <div className="flex justify-between items-center text-emerald-400">
                  <span className="text-xs uppercase font-bold text-slate-500">Cache Hit Rate</span>
                  <BarChart3 size={18} />
                </div>
                <p className="text-2xl font-bold text-slate-200">{Math.round(stats.cache_hit_rate * 100)}%</p>
              </div>

              <div className="p-5 bg-slate-900/30 border border-slate-800 rounded-2xl space-y-2">
                <div className="flex justify-between items-center text-amber-400">
                  <span className="text-xs uppercase font-bold text-slate-500">Avg Latency</span>
                  <Clock size={18} />
                </div>
                <p className="text-2xl font-bold text-slate-200">{stats.avg_latency_seconds.toFixed(3)}s</p>
              </div>
            </div>
          )}

          {/* Sub Navigation */}
          <div className="glass-card p-6 space-y-6">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex bg-slate-950 p-0.5 border border-slate-850 rounded-lg text-xs">
                <button
                  onClick={() => setActiveSubTab('users')}
                  className={`flex items-center gap-1.5 px-4 py-2 rounded-md font-semibold transition ${activeSubTab === 'users' ? 'bg-indigo-500/20 text-indigo-400' : 'text-slate-500 hover:text-slate-300'}`}
                >
                  <Users size={14} />
                  User Registry ({users.length})
                </button>
                <button
                  onClick={() => setActiveSubTab('logs')}
                  className={`flex items-center gap-1.5 px-4 py-2 rounded-md font-semibold transition ${activeSubTab === 'logs' ? 'bg-indigo-500/20 text-indigo-400' : 'text-slate-500 hover:text-slate-300'}`}
                >
                  <ScrollText size={14} />
                  System Audit Logs ({auditLogs.length})
                </button>
              </div>
            </div>

            {/* Sub Tab: Users */}
            {activeSubTab === 'users' ? (
              <div className="overflow-x-auto border border-slate-800 rounded-xl bg-slate-950/80">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 bg-slate-900/30">
                      <th className="p-4 font-semibold text-slate-300">User ID</th>
                      <th className="p-4 font-semibold text-slate-300">Email Address</th>
                      <th className="p-4 font-semibold text-slate-300">Role Pill</th>
                      <th className="p-4 font-semibold text-slate-300">Registration Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id} className="border-b border-slate-900 hover:bg-slate-900/10">
                        <td className="p-4 text-xs font-mono text-slate-500">{u.id}</td>
                        <td className="p-4 text-slate-300 font-semibold">{u.email}</td>
                        <td className="p-4">
                          <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase ${
                            u.role === 'admin' 
                              ? 'text-indigo-400 bg-indigo-500/10 border border-indigo-500/20' 
                              : u.role === 'analyst' 
                                ? 'text-purple-400 bg-purple-500/10 border border-purple-500/20' 
                                : 'text-slate-400 bg-slate-500/10 border border-slate-500/20'
                          }`}>
                            {u.role}
                          </span>
                        </td>
                        <td className="p-4 text-xs text-slate-400">{new Date(u.created_at).toLocaleDateString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              /* Sub Tab: Audit Logs */
              <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
                {auditLogs.map((log) => (
                  <div key={log.id} className="p-4 bg-slate-900/20 hover:bg-slate-900/30 border border-slate-900 hover:border-slate-850 rounded-xl space-y-2 transition-all">
                    <div className="flex justify-between items-start gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                          {log.event_type}
                        </span>
                        <span className="text-xs text-slate-500">
                          User ID: {log.user_id ? <span className="font-mono text-slate-400">{log.user_id}</span> : 'System'}
                        </span>
                      </div>
                      <span className="text-[10px] text-slate-500 font-mono">
                        {new Date(log.created_at).toLocaleString()}
                      </span>
                    </div>
                    {/* Log Payload Details */}
                    <pre className="p-3 bg-black/40 text-[10px] font-mono text-slate-400 rounded-lg overflow-x-auto max-h-28">
                      {JSON.stringify(log.payload, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
