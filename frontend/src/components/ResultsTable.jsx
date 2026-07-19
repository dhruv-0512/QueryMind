import { useState, useMemo } from 'react';
import { ChevronLeft, ChevronRight, Copy, Check } from 'lucide-react';

/*
  Why: Old ResultsTable had:
    - Row count as bg-indigo-500/10 rounded-full badge — decorative, not informative
    - Table container as "border border-slate-800 rounded-xl bg-slate-950/80"
    - Pagination buttons as rounded squares (w-8 h-8 rounded) with indigo active state
    - Cell copy buttons always present but opacity-0 — good pattern, keeping it

  Fix:
    - Row count as plain muted text (already done at results panel level, so just remove badge)
    - Table in the parent's surface card already — no extra border wrapper needed
    - Pagination: simple prev/next with page indicator, no number grid
*/

function formatColumnHeader(col) {
  return col.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function isNumeric(val) {
  return typeof val === 'number' || typeof val === 'bigint';
}

function isDateLike(val) {
  if (val instanceof Date) return true;
  if (typeof val === 'string') {
    const d = new Date(val);
    return !isNaN(d.getTime()) && (
      /^\d{4}-\d{2}-\d{2}/.test(val) || /^\d{2}\/\d{2}\/\d{4}/.test(val)
    );
  }
  return false;
}

function formatCellValue(val) {
  if (val === null || val === undefined) return '';
  if (typeof val === 'number') {
    if (Number.isInteger(val)) return val.toLocaleString();
    return val.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 6 });
  }
  if (typeof val === 'bigint') return val.toLocaleString();
  if (typeof val === 'boolean') return val ? 'true' : 'false';
  if (val instanceof Date) return val.toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, '');
  if (isDateLike(val)) return String(val).replace('T', ' ');
  if (typeof val === 'object') return JSON.stringify(val);
  if (typeof val === 'string' && val.length > 200) return val.slice(0, 200) + '\u2026';
  return String(val);
}

function getColumnAlignment(columns, data) {
  const alignments = {};
  for (const col of columns) {
    const sample = data.slice(0, 20).map((r) => r[col]).filter((v) => v !== null && v !== undefined);
    const allNumeric = sample.length > 0 && sample.every((v) => isNumeric(v));
    alignments[col] = allNumeric ? 'right' : 'left';
  }
  return alignments;
}

export const ResultsTable = ({ data, isLoading }) => {
  const [currentPage,  setCurrentPage]  = useState(1);
  const [rowsPerPage] = useState(25);
  const [copiedCell,   setCopiedCell]   = useState(null);

  const columns     = useMemo(() => (data?.length > 0 ? Object.keys(data[0]) : []), [data]);
  const colAlignments = useMemo(() => (data && columns.length > 0 ? getColumnAlignment(columns, data) : {}), [data, columns]);

  const totalPages  = Math.ceil((data?.length ?? 0) / rowsPerPage);
  const currentRows = useMemo(() => {
    if (!data) return [];
    const start = (currentPage - 1) * rowsPerPage;
    return data.slice(start, start + rowsPerPage);
  }, [data, currentPage, rowsPerPage]);

  if (isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '32px 0', color: 'var(--text-muted)', fontSize: '0.8125rem' }}>
        <span style={{
          width: 14,
          height: 14,
          border: '2px solid var(--border-strong)',
          borderTopColor: 'var(--accent)',
          borderRadius: '50%',
          animation: 'spin 0.7s linear infinite',
          flexShrink: 0,
        }} />
        Executing query…
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div style={{ padding: '32px 0', textAlign: 'center' }}>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>No results returned</p>
        <p style={{ fontSize: '0.8rem', color: 'var(--text-disabled)', marginTop: 4 }}>The query executed successfully but returned 0 rows.</p>
      </div>
    );
  }

  const handleCopy = (val, cellId) => {
    navigator.clipboard.writeText(formatCellValue(val));
    setCopiedCell(cellId);
    setTimeout(() => setCopiedCell(null), 1500);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

      {/* Pagination controls — top */}
      {totalPages > 1 && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          gap: 8,
        }}>
          <button
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            className="btn-secondary"
            style={{ height: 28, padding: '0 8px', gap: 4 }}
          >
            <ChevronLeft size={14} />
          </button>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
            className="btn-secondary"
            style={{ height: 28, padding: '0 8px', gap: 4 }}
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}

      {/* Table */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border-default)', background: 'var(--bg-raised)' }}>
              <th style={{
                padding: '8px 10px',
                textAlign: 'center',
                fontWeight: 500,
                fontSize: '0.72rem',
                color: 'var(--text-disabled)',
                width: 36,
                borderRight: '1px solid var(--border-subtle)',
              }}>
                #
              </th>
              {columns.map((col) => (
                <th
                  key={col}
                  style={{
                    padding: '8px 12px',
                    fontWeight: 600,
                    color: 'var(--text-muted)',
                    fontSize: '0.72rem',
                    letterSpacing: '0.02em',
                    whiteSpace: 'nowrap',
                    textAlign: colAlignments[col] === 'right' ? 'right' : 'left',
                  }}
                >
                  {formatColumnHeader(col)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {currentRows.map((row, rIdx) => {
              const globalIdx = (currentPage - 1) * rowsPerPage + rIdx + 1;
              return (
                <tr
                  key={globalIdx}
                  style={{
                    borderBottom: '1px solid var(--border-subtle)',
                    background: rIdx % 2 === 0 ? 'transparent' : 'var(--bg-raised)',
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(99,102,241,0.04)'}
                  onMouseLeave={e => e.currentTarget.style.background = rIdx % 2 === 0 ? 'transparent' : 'var(--bg-raised)'}
                >
                  <td style={{
                    padding: '7px 10px',
                    textAlign: 'center',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.7rem',
                    color: 'var(--text-disabled)',
                    borderRight: '1px solid var(--border-subtle)',
                    userSelect: 'none',
                  }}>
                    {globalIdx}
                  </td>
                  {columns.map((col) => {
                    const val    = row[col];
                    const cellId = `${globalIdx}-${col}`;
                    const isCopied = copiedCell === cellId;
                    const isNull = val === null || val === undefined;
                    const align  = colAlignments[col];

                    return (
                      <td
                        key={col}
                        style={{
                          padding: '7px 12px',
                          fontFamily: 'var(--font-mono)',
                          fontSize: '0.78rem',
                          textAlign: align === 'right' ? 'right' : 'left',
                          color: align === 'right' ? 'var(--text-primary)' : 'var(--text-secondary)',
                          position: 'relative',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: align === 'right' ? 'flex-end' : 'flex-start' }}>
                          <span style={{ wordBreak: 'break-word', minWidth: 0, flex: 1 }}>
                            {isNull
                              ? <span style={{ color: 'var(--text-disabled)', fontStyle: 'italic', userSelect: 'none' }}>NULL</span>
                              : formatCellValue(val)
                            }
                          </span>
                          {!isNull && (
                            <button
                              onClick={() => handleCopy(val, cellId)}
                              title="Copy value"
                              className="group-hover:opacity-100"
                              style={{
                                flexShrink: 0,
                                opacity: 0,
                                background: 'var(--bg-overlay)',
                                border: '1px solid var(--border-subtle)',
                                borderRadius: 3,
                                padding: 2,
                                cursor: 'pointer',
                                color: isCopied ? 'var(--color-success)' : 'var(--text-muted)',
                                lineHeight: 0,
                                transition: 'opacity 0.1s, color 0.15s',
                              }}
                              onMouseEnter={e => e.currentTarget.style.opacity = 1}
                              onMouseLeave={e => e.currentTarget.style.opacity = 0}
                            >
                              {isCopied ? <Check size={11} /> : <Copy size={11} />}
                            </button>
                          )}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Bottom pagination */}
      {totalPages > 1 && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          paddingTop: 4,
        }}>
          <button
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            className="btn-secondary"
            style={{ height: 28, padding: '0 8px' }}
          >
            <ChevronLeft size={14} />
          </button>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            {currentPage} / {totalPages}
          </span>
          <button
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
            className="btn-secondary"
            style={{ height: 28, padding: '0 8px' }}
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
};
