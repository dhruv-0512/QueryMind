import { useState, useRef } from 'react';
import { Upload, File, Database, AlertCircle, CheckCircle, Loader2 } from 'lucide-react';
import { api } from '../services/api';

/*
  Why: Old DatabaseUpload had:
    - Drop zone with a rounded-full icon container (p-3 bg-indigo-500/10 rounded-full)
    - Emerald bg on file-selected state (border-emerald-500 bg-emerald-500/5)
    - Indigo bg on drag-active (border-indigo-500 bg-indigo-500/5)
    - Separate "emerald" upload button (shadow-emerald-600/20)
    - Status messages as large rounded-xl cards

  Fix:
    - Drop zone is a simple dashed rectangle — no colored icon circles
    - States communicated through border color change only
    - Upload button is the standard btn-primary (consistent with the rest of the app)
    - Status messages use the compact inline style
*/
const ALLOWED_EXTENSIONS = ['.csv', '.xls', '.xlsx', '.json'];

export const DatabaseUpload = ({ onUploadSuccess }) => {
  const [dragActive,  setDragActive]  = useState(false);
  const [file,        setFile]        = useState(null);
  const [statusMsg,   setStatusMsg]   = useState({ type: '', text: '' });
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true);
    else if (e.type === 'dragleave') setDragActive(false);
  };

  const validateFile = (selectedFile) => {
    const name  = selectedFile.name.toLowerCase();
    const valid = ALLOWED_EXTENSIONS.some(ext => name.endsWith(ext));
    if (!valid) {
      setStatusMsg({ type: 'error', text: `Invalid type. Allowed: ${ALLOWED_EXTENSIONS.join(', ')}` });
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
    if (e.dataTransfer.files?.[0]) validateFile(e.dataTransfer.files[0]);
  };

  const handleChange = (e) => {
    e.preventDefault();
    if (e.target.files?.[0]) validateFile(e.target.files[0]);
  };

  const handleUpload = async () => {
    if (!file) return;
    setIsUploading(true);
    setStatusMsg({ type: '', text: '' });

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await api.postMultipart('/database/upload', formData);
      setStatusMsg({ type: 'success', text: response.message });
      setFile(null);
      onUploadSuccess();
    } catch (err) {
      setStatusMsg({ type: 'error', text: err.message || 'Upload and indexing failed.' });
    } finally {
      setIsUploading(false);
    }
  };

  const dropZoneBorder = dragActive
    ? 'var(--accent)'
    : file
      ? 'var(--color-success)'
      : 'var(--border-strong)';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>

      {/* Drop zone */}
      <div
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '24px 16px',
          border: `1.5px dashed ${dropZoneBorder}`,
          borderRadius: 6,
          cursor: 'pointer',
          transition: 'border-color 0.15s, background 0.15s',
          background: dragActive ? 'rgba(99,102,241,0.04)' : 'var(--bg-base)',
          textAlign: 'center',
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          style={{ display: 'none' }}
          accept=".csv,.xls,.xlsx,.json"
          onChange={handleChange}
          disabled={isUploading}
        />

        {isUploading ? (
          <>
            <Loader2 size={22} style={{ color: 'var(--accent)', animation: 'spin 0.8s linear infinite', marginBottom: 8 }} />
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
              Parsing &amp; indexing…
            </p>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 3 }}>
              Loading into PostgreSQL and generating embeddings
            </p>
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          </>
        ) : file ? (
          <>
            <File size={20} style={{ color: 'var(--color-success)', marginBottom: 8 }} />
            <p style={{ fontSize: '0.8125rem', fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2 }}>
              {file.name}
            </p>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {(file.size / (1024 * 1024)).toFixed(2)} MB — click to change
            </p>
          </>
        ) : (
          <>
            <Upload size={20} style={{ color: 'var(--text-muted)', marginBottom: 8 }} />
            <p style={{ fontSize: '0.8125rem', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 2 }}>
              Drop file or click to browse
            </p>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              CSV, XLSX, XLS, JSON
            </p>
          </>
        )}
      </div>

      {file && !isUploading && (
        <button
          onClick={(e) => { e.stopPropagation(); handleUpload(); }}
          className="btn-primary"
          style={{ width: '100%' }}
        >
          <Database size={14} />
          Upload &amp; Index
        </button>
      )}

      {statusMsg.type && (
        <div
          className="animate-fade-in"
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8,
            padding: '9px 12px',
            background: statusMsg.type === 'success' ? 'var(--color-success-muted)' : 'var(--color-danger-muted)',
            border: `1px solid ${statusMsg.type === 'success' ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'}`,
            borderRadius: 5,
            fontSize: '0.8rem',
            color: statusMsg.type === 'success' ? 'var(--color-success)' : 'var(--color-danger)',
          }}
        >
          {statusMsg.type === 'success'
            ? <CheckCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
            : <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
          }
          <p style={{ lineHeight: 1.4 }}>{statusMsg.text}</p>
        </div>
      )}
    </div>
  );
};
