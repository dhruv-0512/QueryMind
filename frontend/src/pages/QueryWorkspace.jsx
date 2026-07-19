import { useState, useEffect, useRef } from 'react';
import { Send, AlertCircle, Database, Table, BarChart2 } from 'lucide-react';
import { api } from '../services/api';
import { SQLViewer } from '../components/SQLViewer';
import { ResultsTable } from '../components/ResultsTable';
import { ChartView } from '../components/ChartView';
import { useQueryHistory } from '../hooks/useQueryHistory';

export const QueryWorkspace = ({ selectedDbId }) => {
  const [databases,   setDatabases]   = useState([]);
  const [activeDbId,  setActiveDbId]  = useState('');
  const [question,    setQuestion]    = useState('');
  const [isLoading,   setIsLoading]   = useState(false);
  const [errorMsg,    setErrorMsg]    = useState('');
  const [queryResult, setQueryResult] = useState(null);
  const [activeTab,   setActiveTab]   = useState('table');

  const textareaRef = useRef(null);
  const { push, navigate, getCount } = useQueryHistory();

  useEffect(() => {
    const fetchDatabases = async () => {
      try {
        const data = await api.get('/database/list');
        setDatabases(data);
        if (selectedDbId) {
          setActiveDbId(selectedDbId);
        } else if (data.length > 0) {
          setActiveDbId(data[0].id);
        }
      } catch (err) {
        console.error('Failed to retrieve databases:', err);
      }
    };
    fetchDatabases();
  }, [selectedDbId]);

  const handleQuery = async (e) => {
    e.preventDefault();
    if (!activeDbId) { setErrorMsg('Please select a database to query.'); return; }
    if (!question.trim()) return;

    // Save to history, then clear the textarea (terminal behaviour — prompt empties after run)
    push(question);
    setQuestion('');

    setIsLoading(true);
    setErrorMsg('');
    setQueryResult(null);

    try {
      const response = await api.post('/query', { db_id: activeDbId, question: question.trim() });
      setQueryResult(response);
    } catch (err) {
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

            {/* Database select */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              <label style={{ fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-secondary)' }}>
                Data source
              </label>
              <div style={{ position: 'relative' }}>
                <Database
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
                <select
                  value={activeDbId}
                  onChange={(e) => setActiveDbId(e.target.value)}
                  className="input-field"
                  style={{ paddingLeft: 30, appearance: 'none', cursor: 'pointer' }}
                  disabled={isLoading}
                >
                  {databases.length === 0 && (
                    <option value="">No databases registered</option>
                  )}
                  {databases.map((db) => (
                    <option key={db.id} value={db.id}>{db.name}</option>
                  ))}
                </select>
              </div>
            </div>

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
                disabled={isLoading || databases.length === 0}
                required
              />
            </div>

            <button
              type="submit"
              disabled={isLoading || databases.length === 0}
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
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '14px 16px',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 6,
                fontSize: '0.8125rem',
                color: 'var(--text-muted)',
              }}
            >
              <span style={{
                width: 14,
                height: 14,
                border: '2px solid var(--border-strong)',
                borderTopColor: 'var(--accent)',
                borderRadius: '50%',
                animation: 'spin 0.7s linear infinite',
                flexShrink: 0,
              }} />
              Generating SQL and executing query…
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
              <div className="status-bar">
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
              </div>

              {/* SQL Viewer */}
              <div className="surface" style={{ padding: '18px 20px' }}>
                <SQLViewer
                  sql={queryResult.sql}
                  explanation={queryResult.explanation}
                  confidence={queryResult.confidence}
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
