import { useState, useEffect } from 'react';
import { GitMerge, Check, X, ShieldCheck, AlertCircle, ArrowRight, Loader2 } from 'lucide-react';
import { api } from '../services/api';

export const DetectedRelationshipsModal = ({ activeDbIds, onConfirmRelationships }) => {
  const [candidates, setCandidates] = useState([]);
  const [selectedCandidates, setSelectedCandidates] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [isConfirmed, setIsConfirmed] = useState(false);

  useEffect(() => {
    if (!activeDbIds || activeDbIds.length < 2) {
      setCandidates([]);
      setSelectedCandidates([]);
      return;
    }

    const detectRelationships = async () => {
      setIsLoading(true);
      setErrorMsg('');
      setIsConfirmed(false);

      try {
        const response = await api.post('/database/relationships/detect', { db_ids: activeDbIds });
        const detected = response.candidates || [];
        setCandidates(detected);

        // Pre-select strong candidates (score >= 0.85)
        const strongKeys = detected
          .filter(c => c.confidence_level === 'strong')
          .map(c => `${c.source_table}.${c.source_column}->${c.target_table}.${c.target_column}`);

        setSelectedCandidates(strongKeys);
      } catch (err) {
        console.error('Relationship detection error:', err);
        setErrorMsg('Failed to detect database relationships.');
      } finally {
        setIsLoading(false);
      }
    };

    detectRelationships();
  }, [activeDbIds]);

  if (!activeDbIds || activeDbIds.length < 2) {
    return null;
  }

  const toggleCandidate = (key) => {
    setSelectedCandidates(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    );
  };

  const handleConfirm = () => {
    const confirmedList = candidates.filter(c =>
      selectedCandidates.includes(`${c.source_table}.${c.source_column}->${c.target_table}.${c.target_column}`)
    );

    setIsConfirmed(true);
    if (onConfirmRelationships) {
      onConfirmRelationships(confirmedList);
    }
  };

  return (
    <div style={{
      background: 'var(--bg-raised)',
      border: '1px solid var(--border-default)',
      borderRadius: 8,
      padding: '14px 16px',
      marginBottom: 16,
      display: 'flex',
      flexDirection: 'column',
      gap: 12,
    }} className="animate-fade-in">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <GitMerge size={16} style={{ color: 'var(--accent)' }} />
          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            Detected Relationships
          </span>
          <span style={{
            fontSize: '0.7rem',
            background: 'rgba(var(--accent-rgb, 99, 102, 241), 0.12)',
            color: 'var(--accent)',
            borderRadius: 10,
            padding: '2px 8px',
            fontWeight: 600,
          }}>
            Deterministic Engine
          </span>
        </div>

        {isConfirmed && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.75rem', color: '#10b981', fontWeight: 600 }}>
            <Check size={14} />
            Confirmed
          </span>
        )}
      </div>

      {isLoading ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 0', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          <Loader2 size={15} style={{ animation: 'spin 0.8s linear infinite', color: 'var(--accent)' }} />
          <span>Analyzing schema & column value overlap...</span>
        </div>
      ) : candidates.length === 0 ? (
        <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
          No strong relationship links inferred between selected datasets. Querying will rely on question semantics.
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {candidates.map((c) => {
            const key = `${c.source_table}.${c.source_column}->${c.target_table}.${c.target_column}`;
            const isChecked = selectedCandidates.includes(key);
            const scorePct = Math.round(c.score * 100);

            return (
              <label
                key={key}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 12,
                  padding: '8px 12px',
                  background: isChecked ? 'rgba(var(--accent-rgb, 99, 102, 241), 0.06)' : 'var(--bg-surface)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 6,
                  cursor: 'pointer',
                  fontSize: '0.8rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, flex: 1 }}>
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => toggleCandidate(key)}
                    style={{ accentColor: 'var(--accent)', cursor: 'pointer' }}
                  />
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 500, color: 'var(--text-primary)' }}>
                    <span>{c.source_table}.<strong style={{ color: 'var(--accent)' }}>{c.source_column}</strong></span>
                    <ArrowRight size={12} style={{ color: 'var(--text-muted)' }} />
                    <span>{c.target_table}.<strong style={{ color: 'var(--accent)' }}>{c.target_column}</strong></span>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{
                    fontSize: '0.7rem',
                    fontWeight: 600,
                    padding: '2px 7px',
                    borderRadius: 10,
                    background: c.confidence_level === 'strong' ? 'rgba(16, 185, 129, 0.12)' : 'rgba(245, 158, 11, 0.12)',
                    color: c.confidence_level === 'strong' ? '#10b981' : '#f59e0b',
                  }}>
                    {scorePct}% {c.confidence_level === 'strong' ? 'Strong' : 'Possible'}
                  </span>
                </div>
              </label>
            );
          })}

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 4 }}>
            <button
              type="button"
              onClick={handleConfirm}
              className="btn-primary"
              style={{ height: 30, padding: '0 14px', fontSize: '0.75rem', gap: 5 }}
            >
              <ShieldCheck size={13} />
              {isConfirmed ? 'Update Confirmed Links' : 'Confirm Selected Links'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
