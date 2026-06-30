import { useState, useEffect, useCallback } from 'react';
import { Database, Trash2, Calendar, DatabaseZap, ShieldAlert, Loader2, ArrowRight, Layers, FileType } from 'lucide-react';
import { api } from '../services/api';
import { DatabaseUpload } from '../components/DatabaseUpload';

export const Dashboard = ({ userRole, onSelectDatabase }) => {
  const [databases, setDatabases] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');

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

  useEffect(() => {
    fetchDatabases();
  }, [fetchDatabases]);

  const handleDelete = async (id, name) => {
    if (!window.confirm(`Are you sure you want to delete the database "${name}" and all of its schema vector indexes?`)) {
      return;
    }

    try {
      await api.delete(`/database/${id}`);
      setDatabases((prev) => prev.filter((db) => db.id !== id));
    } catch (err) {
      alert(err.message || 'Failed to delete database.');
    }
  };

  const isUploader = userRole === 'admin' || userRole === 'analyst';

  return (
    <div className="space-y-8 animate-fade-in">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold glow-text">Database Registry</h1>
          <p className="text-slate-400 text-sm mt-1">
            Manage your SQLite database files and vector search indexes.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Upload Panel */}
        <div className="lg:col-span-1 space-y-6">
          <div className="glass-card p-6 space-y-4">
            <h2 className="text-lg font-bold text-indigo-300 flex items-center gap-2">
              <DatabaseZap size={18} />
              Register Database
            </h2>
            <p className="text-xs text-slate-400 leading-relaxed">
              Upload a CSV, XLSX, or JSON data file. We'll auto-detect column types, create a temporary PostgreSQL schema, and index the table for natural language queries.
            </p>

            {isUploader ? (
              <DatabaseUpload onUploadSuccess={fetchDatabases} />
            ) : (
              <div className="flex gap-2.5 p-4 bg-amber-950/20 border border-amber-900/30 text-amber-400 text-xs rounded-xl">
                <ShieldAlert size={16} className="shrink-0 mt-0.5" />
                <p>Only users with the **analyst** or **admin** roles can register and upload database schemas.</p>
              </div>
            )}
          </div>
        </div>

        {/* Database List */}
        <div className="lg:col-span-2 space-y-6">
          <div className="glass-card p-6 space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-indigo-300 flex items-center gap-2">
                <Database size={18} />
                Your Databases
              </h2>
              <span className="text-xs bg-indigo-500/10 text-indigo-400 px-2.5 py-1 rounded-full font-semibold">
                Count: {databases.length}
              </span>
            </div>

            {errorMsg && (
              <p className="text-sm text-rose-400 bg-rose-950/20 border border-rose-900/30 p-4 rounded-xl">
                {errorMsg}
              </p>
            )}

            {isLoading ? (
              <div className="flex items-center justify-center p-12">
                <Loader2 className="w-8 h-8 text-indigo-500 animate-spin" />
              </div>
            ) : databases.length === 0 ? (
              <div className="text-center py-16 border border-dashed border-slate-800 rounded-2xl bg-slate-950/10">
                <Database className="mx-auto text-slate-600 mb-3" size={32} />
                <p className="text-sm font-semibold text-slate-400">No databases registered yet</p>
                <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                  {isUploader 
                    ? 'Upload your first SQLite file to begin running natural language SQL queries.' 
                    : 'Contact your administrator to have database files indexed.'}
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {databases.map((db) => (
                  <div 
                    key={db.id} 
                    className="p-5 bg-slate-900/30 hover:bg-slate-900/50 border border-slate-800 hover:border-slate-700/80 rounded-2xl flex flex-col justify-between space-y-4 group transition-all duration-200"
                  >
                    <div className="space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="font-semibold text-slate-200 truncate" title={db.name}>
                          {db.name}
                        </h3>
                        <button
                          onClick={() => handleDelete(db.id, db.name)}
                          className="text-slate-500 hover:text-rose-400 p-1 hover:bg-slate-800 rounded transition opacity-0 group-hover:opacity-100"
                          title="Delete database"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                      
                      <div className="flex items-center gap-1.5 text-xs text-slate-500">
                        <FileType size={13} />
                        <span className="uppercase font-semibold text-indigo-400">{db.file_format}</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-slate-500">
                        <Layers size={13} />
                        <span>{db.row_count.toLocaleString()} rows</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-slate-500">
                        <Calendar size={13} />
                        <span>Uploaded: {new Date(db.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>

                    <button
                      onClick={() => onSelectDatabase(db.id, db.name)}
                      className="w-full flex items-center justify-center gap-1.5 py-2.5 bg-indigo-600/10 hover:bg-indigo-600 text-indigo-400 hover:text-white border border-indigo-500/20 hover:border-indigo-600 text-xs font-semibold rounded-xl transition"
                    >
                      Enter Query Workspace
                      <ArrowRight size={13} />
                    </button>
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
