import { useState, useEffect, useCallback } from 'react';
import { Database, Trash2, Calendar, ShieldAlert, Loader2, ArrowRight, Layers, Terminal, CheckSquare, Square } from 'lucide-react';
import { api } from '../services/api';
import { DatabaseUpload } from '../components/DatabaseUpload';

export const Dashboard = ({ userRole, onSelectDatabase }) => {
  const [databases, setDatabases] = useState([]);
  const [selectedDbIds, setSelectedDbIds] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg]   = useState('');

  const fetchDatabases = useCallback(async () => {
    setIsLoading(true);
    setErrorMsg('');
    try {
      const data = await api.get('/database/list');
      setDatabases(data);
      // Auto-select all by default if non-empty
      if (data.length > 0) {
        setSelectedDbIds(data.map(d => d.id));
      }
    } catch (err) {
      setErrorMsg(err.message || 'Failed to load databases.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { fetchDatabases(); }, [fetchDatabases]);

  const handleDelete = async (id, name) => {
    if (!window.confirm(`Delete "${name}"? This action cannot be undone.`)) return;
    const previousDatabases = databases;
    setDatabases((prev) => prev.filter((db) => db.id !== id));
    setSelectedDbIds((prev) => prev.filter(dbId => dbId !== id));

    try {
      await api.delete(`/database/${id}`);
    } catch (err) {
      setDatabases(previousDatabases);
      alert(err.message || 'Failed to delete database.');
    }
  };

  const toggleSelectAll = () => {
    if (selectedDbIds.length === databases.length) {
      setSelectedDbIds([]);
    } else {
      setSelectedDbIds(databases.map(d => d.id));
    }
  };

  const toggleSelectOne = (id) => {
    setSelectedDbIds(prev =>
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  const handleQuerySelected = () => {
    if (selectedDbIds.length === 0) return;
    onSelectDatabase(selectedDbIds);
  };

  const isUploader = userRole === 'admin' || userRole === 'analyst';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }} className="animate-fade-in">

      {/* Page Header */}
      <div>
        <h1 className="page-title">Database Registry</h1>
        <p className="page-subtitle">Manage data sources and vector search indexes. Select multiple files to query cross-table JOINs at once.</p>
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
              gap: 12,
              flexWrap: 'wrap',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <p style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Your databases
                </p>
                <span className="badge badge-neutral">
                  {databases.length} {databases.length === 1 ? 'source' : 'sources'}
                </span>
              </div>

              {databases.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <button
                    onClick={toggleSelectAll}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--text-muted)',
                      fontSize: '0.78rem',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                      fontWeight: 500,
                    }}
                  >
                    {selectedDbIds.length === databases.length ? <CheckSquare size={13} /> : <Square size={13} />}
                    {selectedDbIds.length === databases.length ? 'Deselect all' : 'Select all'}
                  </button>

                  <button
                    onClick={handleQuerySelected}
                    disabled={selectedDbIds.length === 0}
                    className="btn-primary"
                    style={{ height: 32, padding: '0 14px', fontSize: '0.78rem', gap: 6 }}
                  >
                    <Terminal size={13} />
                    Query Selected ({selectedDbIds.length})
                  </button>
                </div>
              )}
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
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {databases.map((db, idx) => {
                  const isChecked = selectedDbIds.includes(db.id);
                  return (
                    <div
                      key={db.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 12,
                        padding: '12px 10px',
                        borderRadius: 6,
                        background: isChecked ? 'rgba(var(--accent-rgb, 99, 102, 241), 0.05)' : 'transparent',
                        borderTop: idx === 0 ? '1px solid var(--border-subtle)' : '1px solid var(--border-subtle)',
                        transition: 'background 0.12s',
                      }}
                      className="group"
                    >
                      {/* Checkbox + Info */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0, flex: 1 }}>
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => toggleSelectOne(db.id)}
                          style={{ accentColor: 'var(--accent)', cursor: 'pointer', width: 15, height: 15 }}
                        />

                        <div style={{ minWidth: 0, flex: 1 }}>
                          <p style={{
                            fontSize: '0.875rem',
                            fontWeight: isChecked ? 600 : 500,
                            color: 'var(--text-primary)',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            marginBottom: 4,
                            cursor: 'pointer',
                          }} title={db.name} onClick={() => toggleSelectOne(db.id)}>
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
                      </div>

                      {/* Right: actions */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                        <button
                          onClick={() => handleDelete(db.id, db.name)}
                          title={`Delete ${db.name}`}
                          style={{
                            background: 'rgba(239, 68, 68, 0.1)',
                            border: '1px solid rgba(239, 68, 68, 0.25)',
                            cursor: 'pointer',
                            color: '#ef4444',
                            padding: '4px 8px',
                            borderRadius: 4,
                            display: 'flex',
                            alignItems: 'center',
                            gap: 4,
                            fontSize: '0.75rem',
                            fontWeight: 500,
                            transition: 'all 0.15s ease',
                          }}
                          onMouseEnter={e => {
                            e.currentTarget.style.background = '#ef4444';
                            e.currentTarget.style.color = '#ffffff';
                          }}
                          onMouseLeave={e => {
                            e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)';
                            e.currentTarget.style.color = '#ef4444';
                          }}
                        >
                          <Trash2 size={13} />
                          Delete
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
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
