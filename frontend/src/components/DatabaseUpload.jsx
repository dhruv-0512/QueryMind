import { useState, useRef } from 'react';
import { Upload, File, Database, AlertCircle, CheckCircle, Loader2 } from 'lucide-react';
import { api } from '../services/api';

const ALLOWED_EXTENSIONS = ['.csv', '.xls', '.xlsx', '.json'];

export const DatabaseUpload = ({ onUploadSuccess }) => {
  const [dragActive, setDragActive] = useState(false);
  const [file, setFile] = useState(null);
  const [statusMsg, setStatusMsg] = useState({ type: '', text: '' });
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const validateFile = (selectedFile) => {
    const name = selectedFile.name.toLowerCase();
    const valid = ALLOWED_EXTENSIONS.some(ext => name.endsWith(ext));
    if (!valid) {
      setStatusMsg({
        type: 'error',
        text: `Invalid file type. Please upload: ${ALLOWED_EXTENSIONS.join(', ')}`
      });
      setFile(null);
      return false;
    }
    setStatusMsg({ type: '', text: '' });
    setFile(selectedFile);
    return true;
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateFile(e.dataTransfer.files[0]);
    }
  };

  const handleChange = (e) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      validateFile(e.target.files[0]);
    }
  };

  const onButtonClick = () => {
    fileInputRef.current?.click();
  };

  const handleUpload = async () => {
    if (!file) return;
    setIsUploading(true);
    setStatusMsg({ type: '', text: '' });

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await api.postMultipart('/database/upload', formData);
      setStatusMsg({
        type: 'success',
        text: response.message
      });
      setFile(null);
      onUploadSuccess();
    } catch (err) {
      setStatusMsg({
        type: 'error',
        text: err.message || 'File upload and indexing failed.'
      });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        onClick={onButtonClick}
        className={`relative flex flex-col items-center justify-center p-8 border-2 border-dashed rounded-2xl cursor-pointer transition-all duration-200 ${
          dragActive
            ? 'border-indigo-500 bg-indigo-500/5'
            : file
              ? 'border-emerald-500 bg-emerald-500/5'
              : 'border-slate-800 bg-slate-950/20 hover:border-slate-700'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept=".csv,.xls,.xlsx,.json"
          onChange={handleChange}
          disabled={isUploading}
        />

        {isUploading ? (
          <div className="flex flex-col items-center py-6 text-center space-y-4">
            <Loader2 size={36} className="text-indigo-400 animate-spin" />
            <div className="space-y-1">
              <p className="text-sm font-semibold text-indigo-300">Parsing file & creating schema...</p>
              <p className="text-xs text-slate-500">Loading data into PostgreSQL and generating embeddings</p>
            </div>
          </div>
        ) : file ? (
          <div className="flex flex-col items-center py-4 text-center space-y-3 animate-fade-in">
            <div className="p-3 bg-emerald-500/10 text-emerald-400 rounded-full border border-emerald-500/20">
              <File size={28} />
            </div>
            <div className="space-y-1">
              <p className="text-sm font-semibold text-emerald-300">{file.name}</p>
              <p className="text-xs text-slate-500">{(file.size / (1024 * 1024)).toFixed(2)} MB</p>
            </div>
            <p className="text-xs text-indigo-400 underline font-semibold mt-1">Click or drag to change file</p>
          </div>
        ) : (
          <div className="flex flex-col items-center py-6 text-center space-y-3">
            <div className="p-3 bg-indigo-500/10 text-indigo-400 rounded-full border border-indigo-500/20">
              <Upload size={24} />
            </div>
            <div className="space-y-1">
              <p className="text-sm font-semibold text-slate-300">Drag & drop your data file here</p>
              <p className="text-xs text-slate-500">Supports CSV, XLSX, XLS, and JSON formats</p>
            </div>
            <button type="button" className="text-xs text-indigo-400 font-semibold underline mt-1">
              Browse files
            </button>
          </div>
        )}
      </div>

      {file && !isUploading && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            handleUpload();
          }}
          className="w-full flex items-center justify-center gap-2 py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-xl transition shadow-lg shadow-emerald-600/20"
        >
          <Database size={16} />
          Upload & Index Data
        </button>
      )}

      {statusMsg.type && (
        <div
          className={`flex gap-3 p-4 border rounded-xl text-sm animate-fade-in ${
            statusMsg.type === 'success'
              ? 'bg-emerald-950/20 border-emerald-900/30 text-emerald-400'
              : 'bg-rose-950/20 border-rose-900/30 text-rose-400'
          }`}
        >
          {statusMsg.type === 'success' ? <CheckCircle size={18} className="shrink-0" /> : <AlertCircle size={18} className="shrink-0" />}
          <p className="leading-relaxed">{statusMsg.text}</p>
        </div>
      )}
    </div>
  );
};
