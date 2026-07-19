import { useState, useEffect } from 'react';
import { Shield, Users, ScrollText, BarChart3, Clock, HelpCircle, HardDrive } from 'lucide-react';
import { api } from '../services/api';

/*
  Why: Old Admin had:
    - "Admin Dashboard" with Shield icon inline in gradient glow-text
    - 4 stat "widgets" — each a rounded-2xl card with a colored icon + uppercase label
    - A glass-card wrapping the tab + content area
    - Tab bar with bg-slate-950 container and bg-indigo-500/20 active pill
    - Audit logs as individual rounded-xl cards with expand animations

  Fix:
    - Clean heading, Shield icon removed from the h1 (it's already in the nav)
    - Stats as a single horizontal status-bar strip (same pattern as QueryWorkspace)
    - Tab bar as underline-style tabs
    - Table and audit logs inside a surface card with no extra nesting
*/
export const Admin = () => {
  const [users,     setUsers]     = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [stats,     setStats]     = useState(null);

  const [isLoading,     setIsLoading]     = useState(true);
  const [errorMsg,      setErrorMsg]      = useState('');
  const [activeSubTab,  setActiveSubTab]  = useState('users');

  useEffect(() => {
    const fetchAdminData = async () => {
      setIsLoading(true);
      setErrorMsg('');
      try {
        const [usersData, logsData, statsData] = await Promise.all([
          api.get('/admin/users'),
          api.get('/admin/audit-logs'),
          api.get('/admin/stats'),
        ]);
        setUsers(usersData);
        setAuditLogs(logsData);
        setStats(statsData);
      } catch (err) {
        setErrorMsg(err.message || 'Failed to load admin data.');
      } finally {
        setIsLoading(false);
      }
    };
    fetchAdminData();
  }, []);

  const roleBadge = (role) => {
    if (role === 'admin')   return <span className="badge badge-accent">admin</span>;
    if (role === 'analyst') return <span className="badge badge-neutral">analyst</span>;
    return <span className="badge badge-neutral">viewer</span>;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }} className="animate-fade-in">

      {/* Header */}
      <div>
        <h1 className="page-title">Admin Dashboard</h1>
        <p className="page-subtitle">Monitor users, system events, and query pipeline metrics.</p>
      </div>

      {errorMsg && (
        <div style={{
          padding: '10px 14px',
          background: 'var(--color-danger-muted)',
          border: '1px solid rgba(239,68,68,0.2)',
          borderRadius: 6,
          fontSize: '0.8125rem',
          color: 'var(--color-danger)',
        }}>
          {errorMsg}
        </div>
      )}

      {isLoading ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '40px 0', color: 'var(--text-muted)', fontSize: '0.8125rem' }}>
          <span style={{
            width: 15,
            height: 15,
            border: '2px solid var(--border-strong)',
            borderTopColor: 'var(--accent)',
            borderRadius: '50%',
            animation: 'spin 0.7s linear infinite',
            flexShrink: 0,
          }} />
          Loading admin data…
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

          {/*
            Why: Old stats were 4 individual cards each with:
              - A colored icon (indigo/purple/emerald/amber)
              - An "UPPERCASE" font-bold label
              - A text-2xl number
            This is a classic AI "dashboard widget" antipattern.

            Fix: Horizontal status bar — same compact pattern used in QueryWorkspace
            for consistency. Numbers are the focus, labels are quiet.
          */}
          {stats && (
            <div className="status-bar">
              <div className="status-item">
                <span className="status-item-label">Total Queries</span>
                <span className="status-item-value">{stats.total_queries.toLocaleString()}</span>
              </div>
              <div style={{ width: 1, background: 'var(--border-subtle)', alignSelf: 'stretch' }} />
              <div className="status-item">
                <span className="status-item-label">Cache Hits</span>
                <span className="status-item-value">{stats.cache_hits.toLocaleString()}</span>
              </div>
              <div style={{ width: 1, background: 'var(--border-subtle)', alignSelf: 'stretch' }} />
              <div className="status-item">
                <span className="status-item-label">Cache Hit Rate</span>
                <span className="status-item-value">{Math.round(stats.cache_hit_rate * 100)}%</span>
              </div>
              <div style={{ width: 1, background: 'var(--border-subtle)', alignSelf: 'stretch' }} />
              <div className="status-item">
                <span className="status-item-label">Avg Latency</span>
                <span className="status-item-value">{stats.avg_latency_seconds.toFixed(3)}s</span>
              </div>
            </div>
          )}

          {/* Tab + Content */}
          <div className="surface">
            {/*
              Why: Old tab bar used bg-slate-950 dark box with bg-indigo-500/20 pill.
              Fix: Clean underline tabs flush to the surface border.
            */}
            <div style={{
              display: 'flex',
              gap: 0,
              padding: '0 20px',
              borderBottom: '1px solid var(--border-subtle)',
            }}>
              {[
                { id: 'users', label: `Users (${users.length})` },
                { id: 'logs',  label: `Audit Logs (${auditLogs.length})` },
              ].map((tab) => {
                const isActive = activeSubTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveSubTab(tab.id)}
                    style={{
                      padding: '12px 16px',
                      fontSize: '0.8125rem',
                      fontWeight: isActive ? 600 : 400,
                      color: isActive ? 'var(--text-primary)' : 'var(--text-muted)',
                      background: 'none',
                      border: 'none',
                      borderBottom: isActive ? '2px solid var(--accent)' : '2px solid transparent',
                      cursor: 'pointer',
                      transition: 'color 0.15s',
                      marginBottom: -1,
                    }}
                  >
                    {tab.label}
                  </button>
                );
              })}
            </div>

            {/* Users Table */}
            {activeSubTab === 'users' ? (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-raised)' }}>
                      {['User ID', 'Email', 'Role', 'Registered'].map((h) => (
                        <th
                          key={h}
                          style={{
                            padding: '10px 20px',
                            fontWeight: 600,
                            color: 'var(--text-muted)',
                            fontSize: '0.75rem',
                            letterSpacing: '0.02em',
                            textAlign: 'left',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u, idx) => (
                      <tr
                        key={u.id}
                        style={{
                          borderBottom: idx < users.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                        }}
                      >
                        <td style={{
                          padding: '12px 20px',
                          fontFamily: 'var(--font-mono)',
                          fontSize: '0.72rem',
                          color: 'var(--text-muted)',
                        }}>
                          {u.id}
                        </td>
                        <td style={{ padding: '12px 20px', fontWeight: 500, color: 'var(--text-primary)' }}>
                          {u.email}
                        </td>
                        <td style={{ padding: '12px 20px' }}>
                          {roleBadge(u.role)}
                        </td>
                        <td style={{ padding: '12px 20px', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          {new Date(u.created_at).toLocaleDateString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              /*
                Why: Old audit log entries were individual rounded-xl cards with 
                JSON.stringify payload in a code block — each card had its own border,
                padding, hover, and an event_type pill. Heavy repetition.

                Fix: List in a surface — each log as a thin-bordered row.
                Event type as a badge. Payload in a compact code block.
              */
              <div style={{ maxHeight: 520, overflowY: 'auto' }}>
                {auditLogs.map((log, idx) => (
                  <div
                    key={log.id}
                    style={{
                      padding: '14px 20px',
                      borderBottom: idx < auditLogs.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                    }}
                  >
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 12,
                      marginBottom: 8,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span className="badge badge-accent">{log.event_type}</span>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          {log.user_id
                            ? <><code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', fontSize: '0.72rem' }}>{log.user_id}</code></>
                            : 'System'
                          }
                        </span>
                      </div>
                      <span style={{
                        fontSize: '0.72rem',
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--text-muted)',
                        flexShrink: 0,
                      }}>
                        {new Date(log.created_at).toLocaleString()}
                      </span>
                    </div>
                    <pre
                      className="code-block"
                      style={{ fontSize: '0.72rem', maxHeight: 100, overflowX: 'auto' }}
                    >
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
