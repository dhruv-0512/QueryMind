import { useState, useMemo } from 'react';
import { Copy, Check, Sparkles, Zap, Cpu } from 'lucide-react';

const SQL_KEYWORDS = new Set([
  'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'IN', 'LIKE', 'BETWEEN', 'IS', 'NULL',
  'JOIN', 'INNER', 'LEFT', 'RIGHT', 'OUTER', 'CROSS', 'ON', 'AS',
  'GROUP', 'BY', 'ORDER', 'ASC', 'DESC', 'HAVING', 'LIMIT', 'OFFSET', 'UNION', 'ALL',
  'INSERT', 'INTO', 'VALUES', 'UPDATE', 'SET', 'DELETE', 'CREATE', 'TABLE', 'DROP', 'ALTER',
  'WITH', 'DISTINCT', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'COALESCE', 'CAST', 'CASE',
  'WHEN', 'THEN', 'ELSE', 'END', 'EXISTS', 'EXCEPT', 'INTERSECT', 'OVER', 'PARTITION',
  'FETCH', 'FIRST', 'NEXT', 'ROWS', 'ONLY', 'ILIKE',
]);

function highlightSQL(sql) {
  const tokens = sql.split(/(\b\w+\b|'[^']*'|"[^"]*"|`[^`]*`|--[^\n]*|\n|.)/g);
  return tokens.map((token, i) => {
    if (!token) return null;
    if (/^--/.test(token)) return <span key={i} style={{ color: '#52525b', fontStyle: 'italic' }}>{token}</span>;
    if (/^'[^']*'$/.test(token) || /^"[^"]*"$/.test(token)) return <span key={i} style={{ color: '#d4a574' }}>{token}</span>;
    if (/^\d+\.?\d*$/.test(token)) return <span key={i} style={{ color: '#a78bfa' }}>{token}</span>;
    if (SQL_KEYWORDS.has(token.toUpperCase()) && /^[A-Za-z]+$/.test(token)) {
      return <span key={i} style={{ color: '#818cf8', fontWeight: 500 }}>{token.toUpperCase()}</span>;
    }
    if (token === '\n') return <br key={i} />;
    return <span key={i}>{token}</span>;
  });
}

export const SQLViewer = ({
  sql,
  explanation,
  confidence,
  llm_invoked = false,
  llm_model = null,
  cached = false,
  rag_mode = null,
}) => {
  const [copied, setCopied] = useState(false);

  const highlighted = useMemo(() => highlightSQL(sql), [sql]);

  const handleCopy = () => {
    navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const confidenceClass =
    confidence >= 0.8 ? 'badge-success' :
    confidence >= 0.5 ? 'badge-warning' :
    'badge-danger';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

      {/* Header row */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 8,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span className="section-label">Generated SQL</span>
          <span className={`badge ${confidenceClass}`}>
            {Math.round(confidence * 100)}% confidence
          </span>

          {/* LLM Invocation Status Indicator */}
          {llm_invoked ? (
            <span
              className="badge badge-accent"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                boxShadow: '0 0 8px rgba(99, 102, 241, 0.25)',
              }}
              title="This SQL query was generated via LLM model inference"
            >
              <Sparkles size={11} />
              LLM Invoked ({llm_model || 'Gemini 3.5 Flash'})
            </span>
          ) : cached ? (
            <span
              className="badge badge-success"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
              title="Retrieved from Redis cache — LLM inference was bypassed"
            >
              <Zap size={11} />
              Cache Hit (LLM Bypassed)
            </span>
          ) : rag_mode === 'direct' ? (
            <span
              className="badge badge-neutral"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: '#38bdf8' }}
              title="Constructed directly from deterministic RAG template match"
            >
              <Zap size={11} />
              Direct RAG (LLM Bypassed)
            </span>
          ) : (
            <span
              className="badge badge-neutral"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
            >
              <Cpu size={11} />
              Engine: {rag_mode || 'Rule-Based'}
            </span>
          )}
        </div>

        <button
          onClick={handleCopy}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 5,
            fontSize: '0.75rem',
            color: copied ? 'var(--color-success)' : 'var(--text-muted)',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '2px 0',
            transition: 'color 0.15s',
          }}
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>

      {/* Code block */}
      <pre className="code-block" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
        <code>{highlighted}</code>
      </pre>

      {/* Explanation */}
      {explanation && (
        <p style={{
          fontSize: '0.8rem',
          color: 'var(--text-muted)',
          lineHeight: 1.6,
          paddingTop: 4,
          borderTop: '1px solid var(--border-subtle)',
        }}>
          <span style={{ fontWeight: 600, color: 'var(--text-secondary)', marginRight: 4 }}>Explanation</span>
          {explanation}
        </p>
      )}
    </div>
  );
};
