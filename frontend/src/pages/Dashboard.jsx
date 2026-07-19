import { useState, useEffect, useCallback } from 'react';
import { Database, Trash2, Calendar, DatabaseZap, ShieldAlert, Loader2, ArrowRight, Layers, FileType } from 'lucide-react';
import { api } from '../services/api';
import { DatabaseUpload } from '../components/DatabaseUpload';

/*
  Why: Old Dashboard had:
    - "Database Registry" as glow-text gradient heading
    - glass-card containers on every section (glassmorphism)
    - Section headers with colored icons (indigo) reading like flashy widgets
    - DB cards as identical rounded-2xl tiles with border-hover effects
    - "Enter Query Workspace" as a full-width indigo ghost button inside each card

  Fix:
    - Clean page header with plain text, no gradient
    - Left panel ("Register") as a simple surface-raised block, no decorative header icon
    - DB list renders as a clean table-style list with left metadata and a right action
    - Action button is compact (icon only + label), right-aligned, not full-width
    - Hover on each row: subtle bg lift only
*/
export const Dashboard = ({ userRole, onSelectDatabase }) => {
  const [databases, setDatabases] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg]   = useState('');

  const fetchDatabases = useCallback(async () => {
    setIsLoading(true);
    setErrorMsg('');
    try {
      const data = await api.get('/database/list');
      setDatabases(data);
    } catch (err) {
      setErrorMsg(err.message || 'Failed to load databases.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { fetchDatabases(); }, [fetchDatabases]);

  const handleDelete = async (id, name) => {
    if (!window.confirm(`Delete "${name}" and all associated vector indexes?`)) return;
    try {
      await api.delete(`/database/${id}`);
      setDatabases((prev) => prev.filter((db) => db.id !== id));
    } catch (err) {
      alert(err.message || 'Failed to delete database.');
    }
  };

  const isUploader = userRole === 'admin' || userRole === 'analyst';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }} className="animate-fade-in">

      {/* Page Header */}
      <div>
        <h1 className="page-title">Database Registry</h1>
        <p className="page-subtitle">Manage data sources and vector search indexes.</p>
      </div>

      <div
        style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 24 }}
        className="lg:grid-cols-3-1"
      >
        <div style={{ display: 'grid', gap: 24 }} className="lg:grid lg:grid-cols-[280px_1fr] items-start">

          {/* ── Left: Upload Panel ── */}
          <div className="surface" style={{ padding: '20px 22px' }}>
            <div style={{ marginBottom: 14 }}>
              <p style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                Register database
              </p>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
                Upload a CSV, XLSX, or JSON file. We'll infer types, load into PostgreSQL, and index for natural language queries.
              </p>
            </div>

            {isUploader ? (
              <DatabaseUpload onUploadSuccess={fetchDatabases} />
            ) : (
              <div
                style={{
                  display: 'flex',
                  gap: 10,
                  padding: '10px 12px',
                  background: 'var(--color-warning-muted)',
                  border: '1px solid rgba(245,158,11,0.2)',
                  borderRadius: 6,
                  fontSize: '0.8rem',
                  color: 'var(--color-warning)',
                  lineHeight: 1.5,
                }}
              >
                <ShieldAlert size={15} style={{ flexShrink: 0, marginTop: 2 }} />
                <p>Only <strong>analyst</strong> or <strong>admin</strong> roles can upload databases.</p>
              </div>
            )}
          </div>

          {/* ── Right: Database List ── */}
          <div className="surface" style={{ padding: '20px 22px' }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 16,
            }}>
              <p style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                Your databases
              </p>
              <span className="badge badge-neutral">
                {databases.length} {databases.length === 1 ? 'source' : 'sources'}
              </span>
            </div>

            {errorMsg && (
              <div
                style={{
                  padding: '10px 12px',
                  marginBottom: 12,
                  background: 'var(--color-danger-muted)',
                  border: '1px solid rgba(239,68,68,0.2)',
                  borderRadius: 6,
                  fontSize: '0.8125rem',
                  color: 'var(--color-danger)',
                }}
              >
                {errorMsg}
              </div>
            )}

            {isLoading ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '40px 0' }}>
                <Loader2 size={22} style={{ color: 'var(--accent)', animation: 'spin 0.8s linear infinite' }} />
                <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
              </div>
            ) : databases.length === 0 ? (
              /*
                Why: Old empty state used a large dashed border box with huge padding.
                Fix: Compact inline empty state — just a muted message. No theatrics.
              */
              <div
                style={{
                  padding: '32px 0',
                  textAlign: 'center',
                  borderTop: '1px solid var(--border-subtle)',
                }}
              >
                <Database size={24} style={{ color: 'var(--text-disabled)', margin: '0 auto 8px' }} />
                <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginBottom: 4 }}>
                  No databases registered yet
                </p>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-disabled)' }}>
                  {isUploader
                    ? 'Upload a data file to get started.'
                    : 'Ask your administrator to register a database.'}
                </p>
              </div>
            ) : (
              /*
                Why: Old layout used a 2-col grid of identical rounded cards — every
                card the same visual weight, the same border, the same hover glow.
                This creates visual monotony that screams "template."

                Fix: A vertical list where each row has:
                  - DB name (primary, left)
                  - Metadata inline below (format badge, row count, date)
                  - "Open" action compact on the right
                  - Delete icon revealed on row hover (already had this — keep it)

                This reads like a real product's data table, not a portfolio card grid.
              */
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {databases.map((db, idx) => (
                  <div
                    key={db.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 12,
                      padding: '12px 0',
                      borderTop: idx === 0 ? '1px solid var(--border-subtle)' : '1px solid var(--border-subtle)',
                      transition: 'background 0.12s',
                    }}
                    className="group"
                  >
                    {/* Left: info */}
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <p style={{
                        fontSize: '0.875rem',
                        fontWeight: 500,
                        color: 'var(--text-primary)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        marginBottom: 4,
                      }} title={db.name}>
                        {db.name}
                      </p>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                        <span className="badge badge-accent">
                          {db.file_format.toUpperCase()}
                        </span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          <Layers size={11} />
                          {db.row_count.toLocaleString()} rows
                        </span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          <Calendar size={11} />
                          {new Date(db.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>

                    {/* Right: actions */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                      <button
                        onClick={() => handleDelete(db.id, db.name)}
                        title="Delete database"
                        style={{
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          color: 'var(--text-disabled)',
                          padding: 4,
                          borderRadius: 4,
                          lineHeight: 0,
                          transition: 'color 0.15s',
                          opacity: 0,
                        }}
                        className="group-hover:opacity-100"
                        onMouseEnter={e => e.currentTarget.style.color = 'var(--color-danger)'}
                        onMouseLeave={e => e.currentTarget.style.color = 'var(--text-disabled)'}
                      >
                        <Trash2 size={14} />
                      </button>

                      <button
                        onClick={() => onSelectDatabase(db.id, db.name)}
                        className="btn-secondary"
                        style={{ height: 30, padding: '0 10px', fontSize: '0.75rem', gap: 5 }}
                      >
                        Open
                        <ArrowRight size={12} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
