import { useState, useEffect } from 'react';
import { Send, AlertCircle, Database, HelpCircle, Table, BarChart2, Zap, Clock, ShieldCheck, RefreshCw } from 'lucide-react';
import { api } from '../services/api';
import { SQLViewer } from '../components/SQLViewer';
import { ResultsTable } from '../components/ResultsTable';
import { ChartView } from '../components/ChartView';

export const QueryWorkspace = ({ selectedDbId }) => {
  const [databases, setDatabases] = useState([]);
  const [activeDbId, setActiveDbId] = useState('');
  const [question, setQuestion] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  
  // Results State
  const [queryResult, setQueryResult] = useState(null);

  const [activeTab, setActiveTab] = useState('table');

  useEffect(() => {
    const fetchDatabases = async () => {
      try {
        const data = await api.get('/database/list');
        setDatabases(data);
        
        // Use database selected from dashboard if available
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
    if (!activeDbId) {
      setErrorMsg('Please select a database to query.');
      return;
    }
    if (!question.trim()) return;

    setIsLoading(true);
    setErrorMsg('');
    setQueryResult(null);

    try {
      const response = await api.post('/query', {
        db_id: activeDbId,
        question: question.trim()
      });
      setQueryResult(response);
    } catch (err) {
      setErrorMsg(err.message || 'An error occurred during query execution.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-3xl font-bold glow-text">AI Query Workspace</h1>
        <p className="text-slate-400 text-sm mt-1">
          Ask questions in plain English and generate real-time SQL execution results.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Input Panel */}
        <div className="lg:col-span-1 space-y-6">
          <div className="glass-card p-6 space-y-5">
            <h2 className="text-lg font-bold text-indigo-300 flex items-center gap-2">
              <HelpCircle size={18} />
              Query Creator
            </h2>

            <form onSubmit={handleQuery} className="space-y-4">
              {/* Select DB */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Target Database</label>
                <div className="relative">
                  <Database size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
                  <select
                    value={activeDbId}
                    onChange={(e) => setActiveDbId(e.target.value)}
                    className="input-field pl-11 appearance-none bg-slate-950 outline-none"
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

              {/* Natural Language Question */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Natural Language Question</label>
                <textarea
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="e.g. List the top 5 customers by sales volume in 2025"
                  rows={4}
                  className="input-field resize-none leading-relaxed"
                  disabled={isLoading || databases.length === 0}
                  required
                />
              </div>

              <button
                type="submit"
                disabled={isLoading || databases.length === 0}
                className="w-full btn-primary py-3.5"
              >
                {isLoading ? (
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                    Executing...
                  </span>
                ) : (
                  <>
                    <Send size={16} />
                    Run Query
                  </>
                )}
              </button>
            </form>
          </div>
        </div>

        {/* Right Output Panel */}
        <div className="lg:col-span-2 space-y-6">
          {errorMsg && (
            <div className="flex gap-3 p-5 bg-rose-950/20 border border-rose-900/30 text-rose-400 rounded-2xl animate-fade-in">
              <AlertCircle size={20} className="shrink-0 mt-0.5" />
              <div className="space-y-1">
                <h4 className="text-sm font-semibold uppercase">Query Execution Failed</h4>
                <p className="text-xs leading-relaxed">{errorMsg}</p>
              </div>
            </div>
          )}

          {isLoading && (
            <div className="glass-card p-12 flex flex-col items-center justify-center space-y-4">
              <RefreshCw className="w-10 h-10 text-indigo-400 animate-spin" />
              <p className="text-sm text-indigo-300 font-semibold animate-pulse">Consulting LLM and validating SQL...</p>
            </div>
          )}

          {!queryResult && !isLoading && !errorMsg && (
            <div className="glass-card p-12 text-center border-dashed border-slate-800 bg-slate-950/10">
              <Database size={36} className="mx-auto text-slate-600 mb-3" />
              <h3 className="text-slate-400 text-sm font-semibold">Workspace Idle</h3>
              <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                Submit a natural language question in the query creator panel to run Gemini generated SQL.
              </p>
            </div>
          )}

          {queryResult && !isLoading && (
            <div className="space-y-6 animate-fade-in">
              {/* Stats Bar */}
              <div className="grid grid-cols-3 gap-4">
                <div className="p-4 bg-slate-900/30 border border-slate-800 rounded-2xl flex items-center gap-3">
                  <div className="p-2 bg-indigo-500/10 text-indigo-400 rounded-lg">
                    <Clock size={16} />
                  </div>
                  <div>
                    <p className="text-[10px] uppercase font-semibold text-slate-500">Latency</p>
                    <p className="text-sm font-bold text-slate-200">{queryResult.execution_time.toFixed(3)}s</p>
                  </div>
                </div>

                <div className="p-4 bg-slate-900/30 border border-slate-800 rounded-2xl flex items-center gap-3">
                  <div className="p-2 bg-purple-500/10 text-purple-400 rounded-lg">
                    <ShieldCheck size={16} />
                  </div>
                  <div>
                    <p className="text-[10px] uppercase font-semibold text-slate-500">Confidence</p>
                    <p className="text-sm font-bold text-slate-200">{Math.round(queryResult.confidence * 100)}%</p>
                  </div>
                </div>

                <div className="p-4 bg-slate-900/30 border border-slate-800 rounded-2xl flex items-center gap-3">
                  <div className={`p-2 rounded-lg ${queryResult.cached ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'}`}>
                    <Zap size={16} />
                  </div>
                  <div>
                    <p className="text-[10px] uppercase font-semibold text-slate-500">Cache Status</p>
                    <p className="text-sm font-bold text-slate-200">{queryResult.cached ? 'Hit (Redis)' : 'Miss (Fresh)'}</p>
                  </div>
                </div>
              </div>

              {/* SQL Viewer */}
              <div className="glass-card p-6">
                <SQLViewer 
                  sql={queryResult.sql} 
                  explanation={queryResult.explanation} 
                  confidence={queryResult.confidence} 
                />
              </div>

              {/* Results visualization */}
              <div className="glass-card p-6 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <h3 className="text-sm font-bold text-indigo-300">Dataset Output</h3>
                  
                  {queryResult.results && queryResult.results.length > 0 && (
                    <div className="flex bg-slate-950 p-0.5 border border-slate-850 rounded-lg text-xs">
                      <button
                        onClick={() => setActiveTab('table')}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-semibold transition ${activeTab === 'table' ? 'bg-indigo-500/20 text-indigo-400' : 'text-slate-500 hover:text-slate-300'}`}
                      >
                        <Table size={14} />
                        Table Grid
                      </button>
                      <button
                        onClick={() => setActiveTab('chart')}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-semibold transition ${activeTab === 'chart' ? 'bg-indigo-500/20 text-indigo-400' : 'text-slate-500 hover:text-slate-300'}`}
                      >
                        <BarChart2 size={14} />
                        Visualizer Chart
                      </button>
                    </div>
                  )}
                </div>

                {activeTab === 'table' ? (
                  <ResultsTable data={queryResult.results} />
                ) : (
                  <ChartView data={queryResult.results} />
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
