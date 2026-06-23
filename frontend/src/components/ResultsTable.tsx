import React, { useState, useMemo } from 'react';
import { ChevronLeft, ChevronRight, Copy, Check } from 'lucide-react';

interface ResultsTableProps {
  data: Record<string, any>[] | null;
  isLoading?: boolean;
}

function formatColumnHeader(col: string): string {
  return col
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function isNumeric(val: any): boolean {
  if (typeof val === 'number') return true;
  if (typeof val === 'bigint') return true;
  return false;
}

function isDateLike(val: any): boolean {
  if (val instanceof Date) return true;
  if (typeof val === 'string') {
    const d = new Date(val);
    return !isNaN(d.getTime()) && (
      /^\d{4}-\d{2}-\d{2}/.test(val) || /^\d{2}\/\d{2}\/\d{4}/.test(val)
    );
  }
  return false;
}

function formatCellValue(val: any): string {
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

function getColumnAlignment(columns: string[], data: Record<string, any>[]): Record<string, 'left' | 'right'> {
  const alignments: Record<string, 'left' | 'right'> = {};
  for (const col of columns) {
    const sample = data.slice(0, 20).map((r) => r[col]).filter((v) => v !== null && v !== undefined);
    const allNumeric = sample.length > 0 && sample.every((v) => isNumeric(v));
    alignments[col] = allNumeric ? 'right' : 'left';
  }
  return alignments;
}

export const ResultsTable: React.FC<ResultsTableProps> = ({ data, isLoading }) => {
  const [currentPage, setCurrentPage] = useState(1);
  const [rowsPerPage] = useState(25);
  const [copiedCell, setCopiedCell] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center p-12 space-y-4">
        <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-slate-400 text-sm">Executing query and retrieving results...</p>
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center border border-dashed border-slate-800 rounded-xl bg-slate-900/30">
        <p className="text-slate-400 text-sm font-medium">No results returned</p>
        <p className="text-slate-500 text-xs mt-1">Execute a valid SQL query to view data.</p>
      </div>
    );
  }

  const columns = Object.keys(data[0]);
  const colAlignments = useMemo(() => getColumnAlignment(columns, data), [data, columns]);

  const totalPages = Math.ceil(data.length / rowsPerPage);
  const currentRows = useMemo(() => {
    const start = (currentPage - 1) * rowsPerPage;
    return data.slice(start, start + rowsPerPage);
  }, [data, currentPage, rowsPerPage]);

  const handleCopy = (val: any, cellId: string) => {
    navigator.clipboard.writeText(formatCellValue(val));
    setCopiedCell(cellId);
    setTimeout(() => setCopiedCell(null), 1500);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-indigo-400 bg-indigo-500/10 px-3 py-1 rounded-full">
          {data.length.toLocaleString()} row{data.length !== 1 ? 's' : ''}
        </span>

        {totalPages > 1 && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:hover:bg-slate-800 transition"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="text-xs text-slate-400 font-mono">
              {currentPage} / {totalPages}
            </span>
            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:hover:bg-slate-800 transition"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        )}
      </div>

      <div className="overflow-x-auto border border-slate-800 rounded-xl bg-slate-950/80">
        <table className="w-full border-collapse text-sm table-auto">
          <thead>
            <tr className="border-b border-slate-700 bg-slate-900/70">
              <th className="p-3 text-center font-semibold text-slate-500 text-xs w-10 select-none border-r border-slate-800">
                #
              </th>
              {columns.map((col) => (
                <th
                  key={col}
                  className={`p-3 font-semibold text-slate-300 text-xs select-none whitespace-nowrap ${
                    colAlignments[col] === 'right' ? 'text-right' : 'text-left'
                  }`}
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
                  className={`border-b border-slate-900/80 transition-colors ${
                    rIdx % 2 === 0 ? 'bg-transparent' : 'bg-slate-900/15'
                  } hover:bg-slate-800/30`}
                >
                  <td className="p-3 text-center text-slate-600 font-mono text-xs border-r border-slate-800/60 select-none">
                    {globalIdx}
                  </td>
                  {columns.map((col) => {
                    const val = row[col];
                    const cellId = `${globalIdx}-${col}`;
                    const isCopied = copiedCell === cellId;
                    const isNull = val === null || val === undefined;
                    const align = colAlignments[col];

                    return (
                      <td
                        key={col}
                        className={`p-3 font-mono text-xs relative group ${
                          align === 'right'
                            ? 'text-right text-slate-300'
                            : 'text-left text-slate-400'
                        }`}
                      >
                        <div className="flex items-start gap-1.5">
                          <span className="break-words min-w-0 flex-1">
                            {isNull ? (
                              <span className="text-slate-600 italic select-none">NULL</span>
                            ) : (
                              formatCellValue(val)
                            )}
                          </span>
                          {!isNull && (
                            <button
                              onClick={() => handleCopy(val, cellId)}
                              className="shrink-0 mt-px opacity-0 group-hover:opacity-100 p-0.5 bg-slate-800 hover:bg-slate-700 text-slate-400 rounded transition"
                              title="Copy"
                            >
                              {isCopied ? (
                                <Check size={12} className="text-emerald-400" />
                              ) : (
                                <Copy size={12} />
                              )}
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

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-1">
          {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
            let pageNum: number;
            if (totalPages <= 7) {
              pageNum = i + 1;
            } else if (currentPage <= 4) {
              pageNum = i < 6 ? i + 1 : totalPages;
            } else if (currentPage >= totalPages - 3) {
              pageNum = i === 0 ? 1 : totalPages - 6 + i;
            } else {
              pageNum = i === 0 ? 1 : i === 6 ? totalPages : currentPage - 2 + i;
            }
            const isEllipsis =
              (i === 5 && totalPages > 7 && currentPage <= 4) ||
              (i === 1 && totalPages > 7 && currentPage >= totalPages - 3);

            if (isEllipsis) {
              return (
                <span key={`ellipsis-${i}`} className="px-2 text-slate-600 text-xs">
                  \u2026
                </span>
              );
            }

            return (
              <button
                key={pageNum}
                onClick={() => setCurrentPage(pageNum)}
                className={`w-8 h-8 rounded text-xs font-mono transition ${
                  pageNum === currentPage
                    ? 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30'
                    : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800'
                }`}
              >
                {pageNum}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};
