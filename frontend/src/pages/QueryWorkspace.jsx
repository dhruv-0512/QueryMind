import { useState, useEffect, useRef } from 'react';
import { Send, AlertCircle, Database, Table, BarChart2, Trash2, Sparkles, Zap } from 'lucide-react';
import { api } from '../services/api';
import { SQLViewer } from '../components/SQLViewer';
import { ResultsTable } from '../components/ResultsTable';
import { ChartView } from '../components/ChartView';
import { useQueryHistory } from '../hooks/useQueryHistory';
import { DetectedRelationshipsModal } from '../components/DetectedRelationshipsModal';

export const QueryWorkspace = ({ selectedDbId }) => {
  const [databases,              setDatabases]              = useState([]);
  const [activeDbIds,            setActiveDbIds]            = useState([]);
  const [confirmedRelationships, setConfirmedRelationships] = useState([]);
  const [question,               setQuestion]               = useState('');
  const [isLoading,              setIsLoading]              = useState(false);
  const [errorMsg,               setErrorMsg]               = useState('');
  const [queryResult,            setQueryResult]            = useState(null);
  const [activeTab,              setActiveTab]              = useState('table');

  const textareaRef = useRef(null);
  const { push, navigate, getCount } = useQueryHistory();

  useEffect(() => {
    const fetchDatabases = async () => {
      try {
        const data = await api.get('/database/list');
        setDatabases(data);
        if (selectedDbId) {
          if (Array.isArray(selectedDbId)) {
            setActiveDbIds(selectedDbId);
          } else {
            setActiveDbIds([selectedDbId]);
          }
        } else if (data.length > 0) {
          setActiveDbIds(data.map(d => d.id));
        }
      } catch (err) {
        console.error('Failed to retrieve databases:', err);
      }
    };
    fetchDatabases();
  }, [selectedDbId]);

  const handleDeleteDatabase = async () => {
    if (activeDbIds.length !== 1) return;
    const targetId = activeDbIds[0];
    const dbObj = databases.find(d => d.id === targetId);
    const dbName = dbObj ? dbObj.name : 'this database';
    if (!window.confirm(`Delete database "${dbName}"? This cannot be undone.`)) return;

    const previousDatabases = databases;
    const updated = databases.filter(d => d.id !== targetId);

    // Optimistic UI update
    setDatabases(updated);
    setActiveDbIds(updated.length > 0 ? [updated[0].id] : []);
    setQueryResult(null);

    try {
      await api.delete(`/database/${targetId}`);
    } catch (err) {
      setDatabases(previousDatabases);
      setActiveDbIds([targetId]);
      alert(err.message || 'Failed to delete database.');
    }
  };

  const handleQuery = async (e) => {
    e.preventDefault();
    const currentQuestion = question.trim();
    if (!currentQuestion) return;
    if (activeDbIds.length === 0) {
      setErrorMsg('Please select at least one database to query.');
      return;
    }

    push(currentQuestion);
    setQuestion('');

    setIsLoading(true);
    setErrorMsg('');
    setQueryResult(null);

    try {
      const payload = activeDbIds.length === 1
        ? { db_id: activeDbIds[0], question: currentQuestion, confirmed_relationships: confirmedRelationships }
        : { db_ids: activeDbIds, question: currentQuestion, confirmed_relationships: confirmedRelationships };
      const response = await api.post('/query', payload);
      setQueryResult(response);
    } catch (err) {
      setQuestion(currentQuestion);
      setErrorMsg(err.message || 'An error occurred during query execution.');
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Handle Up/Down arrow key navigation in the textarea.
   * Mirrors psql / mysql CLI behaviour:
   *   ↑  on first line  → older query
   *   ↓  on last line   → newer query / back to draft
   */
  const handleTextareaKeyDown = (e) => {
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;

    const textarea  = textareaRef.current;
    const direction = e.key === 'ArrowUp' ? 'up' : 'down';
    const result    = navigate(textarea, direction, question);

    if (result !== null) {
      e.preventDefault();
      setQuestion(result);

      // After React commits the new value, move cursor to end
      // Use two rAFs to ensure the DOM has fully updated first
      requestAnimationFrame(() => requestAnimationFrame(() => {
        const el = textareaRef.current;
        if (el) el.setSelectionRange(el.value.length, el.value.length);
      }));
    }
  };

  const historyCount = getCount();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }} className="animate-fade-in">

      {/* Page Header */}
      <div>
        <h1 className="page-title">Query Workspace</h1>
        <p className="page-subtitle">Ask questions in plain English — get real SQL results.</p>
      </div>

      <div style={{ display: 'grid', gap: 20 }} className="lg:grid-cols-[280px_1fr]">

        {/* ── Left: Input Panel ── */}
        <div className="surface" style={{ padding: '20px 22px', alignSelf: 'start' }}>
          <p style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 16 }}>
            Natural language query
          </p>

          <form onSubmit={handleQuery} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

            {/* Multi-select datasource list */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <label style={{ fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-secondary)' }}>
                  Data sources
                </label>
                {activeDbIds.length > 1 && (
                  <span style={{
                    fontSize: '0.7rem',
                    background: 'var(--accent)',
                    color: '#fff',
                    borderRadius: 10,
                    padding: '1px 7px',
                    fontWeight: 600,
                  }}>
                    {activeDbIds.length} selected
                  </span>
                )}
              </div>

              <div style={{
                border: '1px solid var(--border-subtle)',
                borderRadius: 6,
                overflow: 'hidden',
                maxHeight: 150,
                overflowY: 'auto',
              }}>
                {databases.length === 0 ? (
                  <div style={{ padding: '10px 12px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    No databases registered
                  </div>
                ) : (
                  databases.map((db) => {
                    const isChecked = activeDbIds.includes(db.id);
                    return (
                      <label
                        key={db.id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          padding: '7px 12px',
                          cursor: 'pointer',
                          background: isChecked ? 'rgba(var(--accent-rgb, 99, 102, 241), 0.08)' : 'transparent',
                          borderBottom: '1px solid var(--border-subtle)',
                          transition: 'background 0.1s',
                          fontSize: '0.82rem',
                          color: isChecked ? 'var(--text-primary)' : 'var(--text-secondary)',
                          fontWeight: isChecked ? 500 : 400,
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          disabled={isLoading}
                          onChange={() => {
                            setActiveDbIds(prev =>
                              prev.includes(db.id)
                                ? prev.filter(id => id !== db.id)
                                : [...prev, db.id]
                            );
                          }}
                          style={{ accentColor: 'var(--accent)', flexShrink: 0 }}
                        />
                        <Database size={11} style={{ flexShrink: 0, opacity: 0.7 }} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {db.name}
                        </span>
                      </label>
                    );
                  })
                )}
              </div>

              {activeDbIds.length > 5 && (
                <p style={{ fontSize: '0.72rem', color: 'var(--color-warning, #f59e0b)', marginTop: 2 }}>
                  ⚠ Querying more than 5 datasources at once may be slow
                </p>
              )}

              {activeDbIds.length === 1 && (
                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <button
                    type="button"
                    onClick={handleDeleteDatabase}
                    title="Delete selected database"
                    disabled={isLoading}
                    style={{
                      background: 'rgba(239, 68, 68, 0.1)',
                      border: '1px solid rgba(239, 68, 68, 0.25)',
                      color: '#ef4444',
                      padding: '3px 10px',
                      height: 28,
                      borderRadius: 6,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 5,
                      fontSize: '0.72rem',
                      fontWeight: 500,
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.background = '#ef4444'; e.currentTarget.style.color = '#ffffff'; }}
                    onMouseLeave={e => { e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)'; e.currentTarget.style.color = '#ef4444'; }}
                  >
                    <Trash2 size={11} />
                    Delete
                  </button>
                </div>
              )}
            </div>

            {/* Detected Relationships Panel (rendered when 2+ datasources are selected) */}
            <DetectedRelationshipsModal
              activeDbIds={activeDbIds}
              onConfirmRelationships={setConfirmedRelationships}
            />

            {/* Question textarea */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {/* Label row: "Question" on the left, history hint on the right */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <label style={{ fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-secondary)' }}>
                  Question
                </label>
                {historyCount > 0 && (
                  <span style={{
                    fontSize: '0.68rem',
                    color: 'var(--text-disabled)',
                    letterSpacing: '0.02em',
                    userSelect: 'none',
                  }}>
                    ↑↓ {historyCount} in history
                  </span>
                )}
              </div>

              <textarea
                ref={textareaRef}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={handleTextareaKeyDown}
                placeholder="e.g. List the top 5 customers by revenue in Q1 2025"
                rows={4}
                className="input-field"
                disabled={isLoading || activeDbIds.length === 0}
                required
              />
            </div>

            <button
              type="submit"
              disabled={isLoading || activeDbIds.length === 0}
              className="btn-primary"
              style={{ width: '100%', height: 36 }}
            >
              {isLoading ? (
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{
                    width: 13,
                    height: 13,
                    border: '2px solid rgba(255,255,255,0.3)',
                    borderTopColor: 'white',
                    borderRadius: '50%',
                    animation: 'spin 0.7s linear infinite',
                    flexShrink: 0,
                  }} />
                  Running…
                </span>
              ) : (
                <>
                  <Send size={14} />
                  Run Query
                </>
              )}
            </button>
          </form>
        </div>

        {/* ── Right: Output Panel ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {errorMsg && (
            <div
              className="animate-fade-in"
              style={{
                display: 'flex',
                gap: 10,
                padding: '12px 14px',
                background: 'var(--color-danger-muted)',
                border: '1px solid rgba(239,68,68,0.2)',
                borderRadius: 6,
                fontSize: '0.8125rem',
                color: 'var(--color-danger)',
              }}
            >
              <AlertCircle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
              <div>
                <p style={{ fontWeight: 600, marginBottom: 2 }}>Query failed</p>
                <p style={{ color: 'rgba(239,68,68,0.85)', lineHeight: 1.5 }}>{errorMsg}</p>
              </div>
            </div>
          )}

          {isLoading && (
            <div
              className="surface animate-fade-in"
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: 10,
                padding: '16px 18px',
                background: 'rgba(99, 102, 241, 0.04)',
                border: '1px solid var(--accent-border)',
                borderRadius: 8,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{
                    width: 15,
                    height: 15,
                    border: '2px solid var(--border-strong)',
                    borderTopColor: 'var(--accent)',
                    borderRadius: '50%',
                    animation: 'spin 0.7s linear infinite',
                    flexShrink: 0,
                  }} />
                  <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                    Generating SQL & Executing Query…
                  </span>
                </div>

                <span
                  className="badge badge-accent"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.68rem' }}
                >
                  <Sparkles size={11} />
                  AI / LLM Pipeline Active
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Grounding Schema</span>
                <span>➔</span>
                <span style={{ color: 'var(--text-secondary)' }}>Vector RAG Match</span>
                <span>➔</span>
                <span style={{ color: '#a5b4fc', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                  <Sparkles size={10} style={{ color: 'var(--accent)' }} />
                  LLM Model Inference
                </span>
                <span>➔</span>
                <span style={{ color: 'var(--text-muted)' }}>PostgreSQL Query</span>
              </div>
            </div>
          )}

          {!queryResult && !isLoading && !errorMsg && (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '60px 24px',
                textAlign: 'center',
              }}
            >
              <Database size={28} style={{ color: 'var(--text-disabled)', marginBottom: 10 }} />
              <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', fontWeight: 500 }}>
                No query run yet
              </p>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-disabled)', marginTop: 4, maxWidth: 260 }}>
                Submit a question to generate and execute SQL.
              </p>
            </div>
          )}

          {queryResult && !isLoading && (
            <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

              {/* Stats bar */}
              <div className="status-bar" style={{ flexWrap: 'wrap' }}>
                <div className="status-item">
                  <span className="status-item-label">Latency</span>
                  <span className="status-item-value">
                    {queryResult.execution_time.toFixed(3)}s
                  </span>
                </div>
                <div style={{ width: 1, background: 'var(--border-subtle)', alignSelf: 'stretch' }} />
                <div className="status-item">
                  <span className="status-item-label">Confidence</span>
                  <span className="status-item-value">
                    {Math.round(queryResult.confidence * 100)}%
                  </span>
                </div>
                <div style={{ width: 1, background: 'var(--border-subtle)', alignSelf: 'stretch' }} />
                <div className="status-item">
                  <span className="status-item-label">Cache</span>
                  <span
                    className="status-item-value"
                    style={{ color: queryResult.cached ? 'var(--color-success)' : 'var(--text-secondary)' }}
                  >
                    {queryResult.cached ? 'Hit' : 'Miss'}
                  </span>
                </div>
                <div style={{ width: 1, background: 'var(--border-subtle)', alignSelf: 'stretch' }} />
                <div className="status-item">
                  <span className="status-item-label">LLM Call</span>
                  <span
                    className="status-item-value"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                      color: queryResult.llm_invoked ? '#a5b4fc' : (queryResult.cached ? 'var(--color-success)' : '#38bdf8'),
                    }}
                  >
                    {queryResult.llm_invoked ? (
                      <>
                        <Sparkles size={12} style={{ color: 'var(--accent)' }} />
                        <span>Invoked ({queryResult.llm_model || 'Gemini 3.5 Flash'})</span>
                      </>
                    ) : queryResult.cached ? (
                      <>
                        <Zap size={12} style={{ color: 'var(--color-success)' }} />
                        <span>Bypassed (Cache Hit)</span>
                      </>
                    ) : queryResult.rag_mode === 'direct' ? (
                      <>
                        <Zap size={12} style={{ color: '#38bdf8' }} />
                        <span>Bypassed (Direct RAG)</span>
                      </>
                    ) : (
                      <span>Not Invoked ({queryResult.rag_mode || 'Rule Engine'})</span>
                    )}
                  </span>
                </div>
                {queryResult.datasources_used && queryResult.datasources_used.length > 1 && (
                  <>
                    <div style={{ width: 1, background: 'var(--border-subtle)', alignSelf: 'stretch' }} />
                    <div className="status-item">
                      <span className="status-item-label">Sources</span>
                      <span className="status-item-value">{queryResult.datasources_used.length}</span>
                    </div>
                  </>
                )}
              </div>

              {/* SQL Viewer */}
              <div className="surface" style={{ padding: '18px 20px' }}>
                <SQLViewer
                  sql={queryResult.sql}
                  explanation={queryResult.explanation}
                  confidence={queryResult.confidence}
                  llm_invoked={queryResult.llm_invoked}
                  llm_model={queryResult.llm_model}
                  cached={queryResult.cached}
                  rag_mode={queryResult.rag_mode}
                />
              </div>

              {/* Results */}
              <div className="surface" style={{ padding: '18px 20px' }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: 16,
                  paddingBottom: 12,
                  borderBottom: '1px solid var(--border-subtle)',
                }}>
                  <p style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                    Results
                    {queryResult.results && queryResult.results.length > 0 && (
                      <span style={{
                        marginLeft: 8,
                        fontSize: '0.75rem',
                        fontWeight: 400,
                        color: 'var(--text-muted)',
                      }}>
                        {queryResult.results.length.toLocaleString()} rows
                      </span>
                    )}
                  </p>

                  {queryResult.results && queryResult.results.length > 0 && (
                    <div style={{ display: 'flex', gap: 0 }}>
                      {[
                        { id: 'table', label: 'Table', icon: <Table size={13} /> },
                        { id: 'chart', label: 'Chart', icon: <BarChart2 size={13} /> },
                      ].map((tab) => {
                        const isActive = activeTab === tab.id;
                        return (
                          <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: 5,
                              padding: '4px 12px',
                              fontSize: '0.8rem',
                              fontWeight: isActive ? 600 : 400,
                              color: isActive ? 'var(--text-primary)' : 'var(--text-muted)',
                              background: 'none',
                              border: 'none',
                              borderBottom: isActive ? '2px solid var(--accent)' : '2px solid transparent',
                              cursor: 'pointer',
                              transition: 'color 0.15s',
                              paddingBottom: 6,
                            }}
                          >
                            {tab.icon}
                            {tab.label}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {activeTab === 'table'
                  ? <ResultsTable data={queryResult.results} />
                  : <ChartView data={queryResult.results} />
                }
              </div>
            </div>
          )}
        </div>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
};
