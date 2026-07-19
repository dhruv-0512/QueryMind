import { useState, useEffect, useMemo } from 'react';
import { Calendar, ShieldCheck, Clock, Terminal, AlertTriangle, AlertOctagon, CheckCircle2, Search } from 'lucide-react';
import { api } from '../services/api';

/*
  Why: Old QueryHistory had:
    - "Query History" in glow-text gradient heading
    - Each history entry wrapped in glass-card with backdrop-blur, border-hover
    - Status badges as rounded-full pills with colored bg (emerald/rose/amber)
    - "Executed Statement" label in tracking-wider uppercase
    - Stats row icons (Calendar, Clock, ShieldCheck) added visual noise

  Fix:
    - Plain heading
    - History entries as a clean list — thin border-top separators, no cards
    - Status as a compact square badge (badge classes)
    - SQL block with subtle bg, no decorative label
    - Stats as comma-separated inline text, no icons
*/

export const QueryHistory = () => {
  const [history,    setHistory]    = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [isLoading,  setIsLoading]  = useState(true);
  const [errorMsg,   setErrorMsg]   = useState('');

  useEffect(() => {
    const fetchHistory = async () => {
      setIsLoading(true);
      setErrorMsg('');
      try {
        const data = await api.get('/query/history');
        setHistory(data);
      } catch (err) {
        setErrorMsg(err.message || 'Failed to retrieve query history.');
      } finally {
        setIsLoading(false);
      }
    };
    fetchHistory();
  }, []);

  const filteredHistory = useMemo(() =>
    history.filter((item) =>
      item.question.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (item.sql && item.sql.toLowerCase().includes(searchTerm.toLowerCase()))
    ),
    [history, searchTerm]
  );

  const StatusBadge = ({ status }) => {
    if (status === 'success')  return <span className="badge badge-success"><CheckCircle2 size={10} />Success</span>;
    if (status === 'rejected') return <span className="badge badge-danger"><AlertOctagon size={10} />Rejected</span>;
    if (status === 'failed')   return <span className="badge badge-warning"><AlertTriangle size={10} />Failed</span>;
    return null;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }} className="animate-fade-in">

      {/* Header row */}
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }} className="md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="page-title">Query History</h1>
          <p className="page-subtitle">Past natural language queries and execution logs.</p>
        </div>

        {/* Search */}
        <div style={{ position: 'relative', flexShrink: 0 }}>
          <Search
            size={13}
            style={{
              position: 'absolute',
              left: 10,
              top: '50%',
              transform: 'translateY(-50%)',
              color: 'var(--text-muted)',
              pointerEvents: 'none',
            }}
          />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search questions or SQL…"
            className="input-field"
            style={{ paddingLeft: 30, width: 260 }}
          />
        </div>
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
          Loading history…
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      ) : filteredHistory.length === 0 ? (
        <div style={{ padding: '48px 0', textAlign: 'center' }}>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            {searchTerm ? 'No matches for your search.' : 'No queries recorded yet.'}
          </p>
          {!searchTerm && (
            <p style={{ fontSize: '0.8rem', color: 'var(--text-disabled)', marginTop: 4 }}>
              Run a query in the workspace to see it here.
            </p>
          )}
        </div>
      ) : (
        /*
          Why: Old layout rendered each history entry as a glass-card with 24px padding,
          border-hover on indigo, and multiple distinct sections inside each card 
          (separator, SQL block, error box, stats row with icons). The repeated card
          pattern made the entire history list look like a "list of AI components."

          Fix: Clean list — each entry is a plain row separated by a thin border.
          The question is the primary text. SQL is shown in a compact code block.
          Status badge is small, metadata is one quiet line below.
        */
        <div className="surface" style={{ overflow: 'hidden' }}>
          {filteredHistory.map((item, idx) => (
            <div
              key={item.id}
              style={{
                padding: '16px 20px',
                borderBottom: idx < filteredHistory.length - 1 ? '1px solid var(--border-subtle)' : 'none',
              }}
            >
              {/* Question + status */}
              <div style={{
                display: 'flex',
                alignItems: 'flex-start',
                justifyContent: 'space-between',
                gap: 12,
                marginBottom: 10,
              }}>
                <p style={{
                  fontSize: '0.875rem',
                  fontWeight: 500,
                  color: 'var(--text-primary)',
                  lineHeight: 1.5,
                  maxWidth: '75%',
                }}>
                  {item.question}
                </p>
                <StatusBadge status={item.status} />
              </div>

              {/* SQL block */}
              {item.sql && (
                <pre
                  className="code-block"
                  style={{ marginBottom: 10, maxHeight: 120, overflowY: 'auto', fontSize: '0.75rem' }}
                >
                  <code style={{ color: '#a5b4fc' }}>{item.sql}</code>
                </pre>
              )}

              {/* Error */}
              {item.error_message && (
                <div style={{
                  padding: '8px 12px',
                  marginBottom: 10,
                  background: 'var(--color-danger-muted)',
                  border: '1px solid rgba(239,68,68,0.18)',
                  borderRadius: 5,
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.75rem',
                  color: 'var(--color-danger)',
                  lineHeight: 1.5,
                }}>
                  {item.error_message}
                </div>
              )}

              {/* Meta row */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 16,
                fontSize: '0.75rem',
                color: 'var(--text-muted)',
              }}>
                <span>{new Date(item.created_at).toLocaleString()}</span>
                {item.status === 'success' && (
                  <>
                    <span>{item.execution_time.toFixed(3)}s</span>
                    <span>{Math.round(item.confidence * 100)}% confidence</span>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
