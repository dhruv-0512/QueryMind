import React, { useState, useMemo } from 'react';
import { ChevronLeft, ChevronRight, Copy, Check } from 'lucide-react';

interface ResultsTableProps {
  data: Record<string, any>[] | null;
  isLoading?: boolean;
}

export const ResultsTable: React.FC<ResultsTableProps> = ({ data, isLoading }) => {
  const [currentPage, setCurrentPage] = useState(1);
  const [rowsPerPage] = useState(10);
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

  const totalPages = Math.ceil(data.length / rowsPerPage);
  const currentRows = useMemo(() => {
    const idx = currentPage * rowsPerPage;
    return data.slice(idx - rowsPerPage, idx);
  }, [data, currentPage, rowsPerPage]);

  const handleCopy = (val: any, cellId: string) => {
    navigator.clipboard.writeText(String(val));
    setCopiedCell(cellId);
    setTimeout(() => setCopiedCell(null), 1500);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-indigo-400 bg-indigo-500/10 px-3 py-1 rounded-full">
          Total rows: {data.length}
        </span>
        
        {totalPages > 1 && (
          <div className="flex items-center gap-1">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 disabled:hover:bg-slate-800 transition"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="text-xs text-slate-400 px-2">
              Page {currentPage} of {totalPages}
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
        <table className="w-full text-left border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-900/50">
              {columns.map((col) => (
                <th key={col} className="p-4 font-semibold text-slate-300 select-none">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {currentRows.map((row, rIdx) => (
              <tr 
                key={rIdx} 
                className="border-b border-slate-900 hover:bg-slate-900/20 transition-colors"
              >
                {columns.map((col) => {
                  const val = row[col];
                  const cellId = `${rIdx}-${col}`;
                  const isCopied = copiedCell === cellId;

                  return (
                    <td key={col} className="p-4 text-slate-400 font-mono text-xs relative group max-w-xs truncate">
                      <span title={String(val)}>{val === null ? <span className="text-slate-600 italic">null</span> : String(val)}</span>
                      {val !== null && (
                        <button
                          onClick={() => handleCopy(val, cellId)}
                          className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-1 bg-slate-800 hover:bg-slate-700 text-slate-400 rounded transition"
                          title="Copy cell value"
                        >
                          {isCopied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                        </button>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
