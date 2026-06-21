import React, { useState, useEffect, useMemo } from 'react';
import { HelpCircle, Calendar, ShieldCheck, Clock, Terminal, AlertTriangle, AlertOctagon, CheckCircle2, Search } from 'lucide-react';
import { api } from '../services/api';

interface QueryRecord {
  id: string;
  db_id: string;
  question: string;
  sql: string;
  explanation: string;
  confidence: number;
  execution_time: number;
  status: 'success' | 'failed' | 'rejected';
  error_message: string | null;
  created_at: string;
}

export const QueryHistory: React.FC = () => {
  const [history, setHistory] = useState<QueryRecord[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    const fetchHistory = async () => {
      setIsLoading(true);
      setErrorMsg('');
      try {
        const data = await api.get('/query/history');
        setHistory(data);
      } catch (err: any) {
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

  const getStatusBadge = (status: 'success' | 'failed' | 'rejected') => {
    switch (status) {
      case 'success':
        return (
          <span className="flex items-center gap-1 text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-0.5 rounded-full text-xs font-semibold">
            <CheckCircle2 size={12} />
            Success
          </span>
        );
      case 'rejected':
        return (
          <span className="flex items-center gap-1 text-rose-400 bg-rose-500/10 border border-rose-500/20 px-2.5 py-0.5 rounded-full text-xs font-semibold">
            <AlertOctagon size={12} />
            Rejected
          </span>
        );
      case 'failed':
        return (
          <span className="flex items-center gap-1 text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2.5 py-0.5 rounded-full text-xs font-semibold">
            <AlertTriangle size={12} />
            Failed
          </span>
        );
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold glow-text">Query History</h1>
          <p className="text-slate-400 text-sm mt-1">
            Review your past natural language queries and execution logs.
          </p>
        </div>

        {/* Search filter */}
        <div className="relative w-full md:w-80">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search question or SQL..."
            className="input-field pl-11 text-xs py-2"
          />
        </div>
      </div>

      {errorMsg && (
        <div className="p-4 bg-rose-950/20 border border-rose-900/30 text-rose-400 rounded-xl text-sm">
          {errorMsg}
        </div>
      )}

      {isLoading ? (
        <div className="flex flex-col items-center justify-center p-20 space-y-4">
          <div className="w-10 h-10 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
          <p className="text-slate-400 text-xs">Retrieving execution audit trace...</p>
        </div>
      ) : filteredHistory.length === 0 ? (
        <div className="text-center py-20 border border-dashed border-slate-800 rounded-2xl bg-slate-950/10">
          <HelpCircle className="mx-auto text-slate-600 mb-3" size={32} />
          <p className="text-sm font-semibold text-slate-400">No query history records found</p>
          <p className="text-xs text-slate-500 mt-1">
            {searchTerm ? 'No matches found for your filter criteria.' : 'Create natural language queries to populate history logs.'}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredHistory.map((item) => (
            <div key={item.id} className="glass-card p-6 space-y-4 hover:border-indigo-500/20 transition-all duration-200">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-900 pb-3">
                <h3 className="font-semibold text-slate-200 text-sm max-w-2xl leading-relaxed">
                  {item.question}
                </h3>
                <div className="flex items-center gap-2">
                  {getStatusBadge(item.status)}
                </div>
              </div>

              {/* SQL Code Block */}
              {item.sql && (
                <div className="space-y-1.5">
                  <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider flex items-center gap-1.5">
                    <Terminal size={12} />
                    Executed Statement
                  </span>
                  <pre className="code-block p-3 text-xs whitespace-pre-wrap break-all bg-black/40 border border-slate-900 rounded-lg max-h-40 overflow-y-auto">
                    <code className="text-indigo-300/95 font-mono">{item.sql}</code>
                  </pre>
                </div>
              )}

              {/* Error Box */}
              {item.error_message && (
                <div className="p-3.5 bg-rose-950/20 border border-rose-900/30 text-rose-400 text-xs rounded-xl font-mono leading-relaxed">
                  <span className="font-bold block uppercase tracking-wider text-[10px] text-rose-400 mb-1">Execution Error Details</span>
                  {item.error_message}
                </div>
              )}

              {/* Stats row */}
              <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-500 pt-1">
                <div className="flex items-center gap-1">
                  <Calendar size={13} />
                  <span>{new Date(item.created_at).toLocaleString()}</span>
                </div>
                
                {item.status === 'success' && (
                  <>
                    <div className="flex items-center gap-1">
                      <Clock size={13} />
                      <span>Latency: {item.execution_time.toFixed(3)}s</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <ShieldCheck size={13} />
                      <span>Confidence: {Math.round(item.confidence * 100)}%</span>
                    </div>
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
