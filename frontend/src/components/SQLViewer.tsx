import React, { useState } from 'react';
import { Copy, Check, Terminal, HelpCircle } from 'lucide-react';

interface SQLViewerProps {
  sql: string;
  explanation: string;
  confidence: number;
}

export const SQLViewer: React.FC<SQLViewerProps> = ({ sql, explanation, confidence }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getConfidenceColor = (score: number) => {
    if (score >= 0.8) return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
    if (score >= 0.5) return 'text-amber-400 bg-amber-500/10 border-amber-500/20';
    return 'text-rose-400 bg-rose-500/10 border-rose-500/20';
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-indigo-400">
          <Terminal size={18} />
          <h3 className="text-sm font-semibold uppercase tracking-wider">Generated Query</h3>
        </div>
        
        <div className="flex items-center gap-3">
          {/* Confidence Score */}
          <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-semibold ${getConfidenceColor(confidence)}`}>
            Confidence: {Math.round(confidence * 100)}%
          </div>

          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg border border-slate-700 transition"
          >
            {copied ? (
              <>
                <Check size={14} className="text-emerald-400" />
                Copied
              </>
            ) : (
              <>
                <Copy size={14} />
                Copy SQL
              </>
            )}
          </button>
        </div>
      </div>

      {/* SQL Code Block */}
      <pre className="code-block whitespace-pre-wrap break-all relative">
        <code className="text-emerald-300">{sql}</code>
      </pre>

      {/* Explanation Box */}
      <div className="flex gap-3 p-4 bg-indigo-950/20 border border-indigo-900/30 rounded-xl">
        <div className="text-indigo-400 mt-0.5">
          <HelpCircle size={18} />
        </div>
        <div className="space-y-1">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-indigo-400">Model Explanation</h4>
          <p className="text-xs text-slate-300 leading-relaxed">{explanation}</p>
        </div>
      </div>
    </div>
  );
};
