import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  GitMerge,
  Check,
  X,
  ShieldCheck,
  AlertCircle,
  ArrowRight,
  Loader2,
  SlidersHorizontal,
  Link2,
  CheckSquare,
  Square,
  Sparkles,
} from 'lucide-react';
import { api } from '../services/api';

export const DetectedRelationshipsModal = ({ activeDbIds, onConfirmRelationships }) => {
  const [candidates, setCandidates] = useState([]);
  const [selectedKeys, setSelectedKeys] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isConfirmed, setIsConfirmed] = useState(false);

  const onConfirmRef = useRef(onConfirmRelationships);
  useEffect(() => {
    onConfirmRef.current = onConfirmRelationships;
  }, [onConfirmRelationships]);

  // Helper to build a unique key for each relationship candidate
  const getCandidateKey = (c) =>
    `${c.source_table}.${c.source_column}->${c.target_table}.${c.target_column}`;

  const activeDbIdsJson = JSON.stringify(activeDbIds || []);

  useEffect(() => {
    const ids = JSON.parse(activeDbIdsJson);
    if (!ids || ids.length < 2) {
      setCandidates([]);
      setSelectedKeys([]);
      setIsConfirmed(false);
      return;
    }

    let isMounted = true;

    const detectRelationships = async () => {
      setIsLoading(true);
      setErrorMsg('');
      setIsConfirmed(false);

      try {
        const response = await api.post('/database/relationships/detect', { db_ids: ids });
        if (!isMounted) return;
        const detected = response?.candidates || [];
        setCandidates(detected);

        // Pre-select strong candidates (or all if all are moderate/strong)
        const initialSelected = detected
          .filter((c) => c.confidence_level === 'strong' || c.score >= 0.75)
          .map(getCandidateKey);

        const defaultKeys = initialSelected.length > 0 ? initialSelected : detected.map(getCandidateKey);
        setSelectedKeys(defaultKeys);

        // Auto-propagate initial confirmed list to parent
        const initialConfirmed = detected.filter((c) => defaultKeys.includes(getCandidateKey(c)));
        if (onConfirmRef.current) {
          onConfirmRef.current(initialConfirmed);
        }
      } catch (err) {
        if (!isMounted) return;
        console.warn('Relationship detection note:', err?.message || err);
        setCandidates([]);
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    detectRelationships();

    return () => {
      isMounted = false;
    };
  }, [activeDbIdsJson]);

  // Handle toggle of a candidate key
  const toggleCandidate = (key) => {
    setSelectedKeys((prev) => {
      const updated = prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key];
      const confirmedList = candidates.filter((c) => updated.includes(getCandidateKey(c)));
      if (onConfirmRef.current) {
        onConfirmRef.current(confirmedList);
      }
      setIsConfirmed(true);
      return updated;
    });
  };

  const handleSelectAll = useCallback(() => {
    const allKeys = candidates.map(getCandidateKey);
    setSelectedKeys(allKeys);
    if (onConfirmRef.current) {
      onConfirmRef.current(candidates);
    }
    setIsConfirmed(true);
  }, [candidates]);

  const handleSelectStrongOnly = useCallback(() => {
    const strongKeys = candidates
      .filter((c) => c.confidence_level === 'strong' || c.score >= 0.8)
      .map(getCandidateKey);
    setSelectedKeys(strongKeys);
    const confirmedList = candidates.filter((c) => strongKeys.includes(getCandidateKey(c)));
    if (onConfirmRef.current) {
      onConfirmRef.current(confirmedList);
    }
    setIsConfirmed(true);
  }, [candidates]);

  const handleClearAll = useCallback(() => {
    setSelectedKeys([]);
    if (onConfirmRef.current) {
      onConfirmRef.current([]);
    }
    setIsConfirmed(true);
  }, []);

  const handleApplyAndClose = () => {
    const confirmedList = candidates.filter((c) => selectedKeys.includes(getCandidateKey(c)));
    if (onConfirmRef.current) {
      onConfirmRef.current(confirmedList);
    }
    setIsConfirmed(true);
    setIsModalOpen(false);
  };

  // Close modal on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isModalOpen) {
        setIsModalOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isModalOpen]);

  const selectedCount = selectedKeys.length;
  const strongCount = useMemo(
    () => candidates.filter((c) => c.confidence_level === 'strong' || c.score >= 0.8).length,
    [candidates]
  );

  if (!activeDbIds || activeDbIds.length < 2) {
    return null;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }} className="animate-fade-in">
      {/* ── Compact Sidebar Widget ── */}
      <div
        style={{
          background: 'var(--bg-raised)',
          border: '1px solid var(--border-default)',
          borderRadius: 8,
          padding: '12px 14px',
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
        }}
      >
        {/* Header Row */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <div
              style={{
                width: 22,
                height: 22,
                borderRadius: 5,
                background: 'rgba(99, 102, 241, 0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--accent)',
              }}
            >
              <GitMerge size={13} />
            </div>
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              Schema Links
            </span>
          </div>

          <span
            style={{
              fontSize: '0.65rem',
              background: 'rgba(99, 102, 241, 0.12)',
              color: 'var(--accent)',
              borderRadius: 4,
              padding: '1px 6px',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: 3,
            }}
          >
            <Sparkles size={9} />
            Deterministic
          </span>
        </div>

        {/* State View */}
        {isLoading ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '4px 0', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            <Loader2 size={13} style={{ animation: 'spin 0.8s linear infinite', color: 'var(--accent)' }} />
            <span>Analyzing overlap…</span>
          </div>
        ) : errorMsg ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.73rem', color: 'var(--color-danger)' }}>
            <AlertCircle size={13} />
            <span>{errorMsg}</span>
          </div>
        ) : candidates.length === 0 ? (
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
            No deterministic join keys detected across selected datasets.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {/* Summary Count & Quick Preview */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                <strong style={{ color: selectedCount > 0 ? 'var(--color-success)' : 'var(--text-muted)' }}>
                  {selectedCount}
                </strong>{' '}
                of {candidates.length} active
              </span>

              {isConfirmed && selectedCount > 0 && (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 3,
                    fontSize: '0.68rem',
                    color: 'var(--color-success)',
                    fontWeight: 600,
                  }}
                >
                  <Check size={11} />
                  Ready
                </span>
              )}
            </div>

            {/* In-sidebar mini pill list */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5, maxHeight: 110, overflowY: 'auto' }}>
              {candidates.map((c) => {
                const key = getCandidateKey(c);
                const isChecked = selectedKeys.includes(key);
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => toggleCandidate(key)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '5px 8px',
                      borderRadius: 5,
                      background: isChecked ? 'rgba(99, 102, 241, 0.08)' : 'var(--bg-surface)',
                      border: `1px solid ${isChecked ? 'rgba(99, 102, 241, 0.25)' : 'var(--border-subtle)'}`,
                      cursor: 'pointer',
                      fontSize: '0.72rem',
                      textAlign: 'left',
                      transition: 'all 0.12s ease',
                      width: '100%',
                    }}
                    title={`${c.source_table}.${c.source_column} -> ${c.target_table}.${c.target_column} (${Math.round(c.score * 100)}% match)`}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5, minWidth: 0, overflow: 'hidden' }}>
                      {isChecked ? (
                        <CheckSquare size={12} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                      ) : (
                        <Square size={12} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                      )}
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          color: isChecked ? 'var(--text-primary)' : 'var(--text-muted)',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          fontSize: '0.7rem',
                        }}
                      >
                        {c.source_column} ➔ {c.target_column}
                      </span>
                    </div>

                    <span
                      style={{
                        fontSize: '0.65rem',
                        fontWeight: 600,
                        color: c.confidence_level === 'strong' ? '#22c55e' : '#f59e0b',
                        flexShrink: 0,
                        marginLeft: 4,
                      }}
                    >
                      {Math.round(c.score * 100)}%
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Manage Links Modal Button */}
            <button
              type="button"
              onClick={() => setIsModalOpen(true)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 5,
                width: '100%',
                padding: '5px 10px',
                borderRadius: 5,
                background: 'transparent',
                border: '1px dashed var(--border-strong)',
                color: 'var(--text-secondary)',
                fontSize: '0.73rem',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                marginTop: 2,
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--accent)';
                e.currentTarget.style.color = 'var(--text-primary)';
                e.currentTarget.style.background = 'var(--bg-surface)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--border-strong)';
                e.currentTarget.style.color = 'var(--text-secondary)';
                e.currentTarget.style.background = 'transparent';
              }}
            >
              <SlidersHorizontal size={12} />
              Configure JOIN Graph
            </button>
          </div>
        )}
      </div>

      {/* ── Full Relationship Inspector Modal Dialog ── */}
      {isModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
            background: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(4px)',
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setIsModalOpen(false);
          }}
        >
          <div
            className="surface animate-fade-in"
            style={{
              width: '100%',
              maxWidth: 680,
              maxHeight: '90vh',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-default)',
              borderRadius: 12,
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 20px 50px rgba(0, 0, 0, 0.6), 0 0 0 1px var(--border-subtle)',
              overflow: 'hidden',
            }}
          >
            {/* Modal Header */}
            <div
              style={{
                padding: '18px 24px',
                borderBottom: '1px solid var(--border-subtle)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                background: 'var(--bg-raised)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div
                  style={{
                    width: 34,
                    height: 34,
                    borderRadius: 8,
                    background: 'rgba(99, 102, 241, 0.15)',
                    border: '1px solid rgba(99, 102, 241, 0.3)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--accent)',
                  }}
                >
                  <GitMerge size={18} />
                </div>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <h2 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
                      Deterministic Schema Relationships
                    </h2>
                    <span className="badge badge-accent" style={{ fontSize: '0.65rem' }}>
                      Auto-Inferred
                    </span>
                  </div>
                  <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 2, margin: 0 }}>
                    Deterministic matching infers exact foreign keys based on column names, data types, and value overlap.
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                aria-label="Close dialog"
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                  padding: 6,
                  borderRadius: 6,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = 'var(--text-primary)';
                  e.currentTarget.style.background = 'var(--bg-overlay)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = 'var(--text-muted)';
                  e.currentTarget.style.background = 'transparent';
                }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Toolbar */}
            <div
              style={{
                padding: '12px 24px',
                borderBottom: '1px solid var(--border-subtle)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                background: 'var(--bg-base)',
                flexWrap: 'wrap',
                gap: 8,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                  Active Links:
                </span>
                <span
                  style={{
                    fontSize: '0.78rem',
                    fontWeight: 700,
                    color: selectedCount > 0 ? 'var(--color-success)' : 'var(--color-danger)',
                  }}
                >
                  {selectedCount} of {candidates.length}
                </span>
              </div>

              {/* Action Buttons */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                {strongCount > 0 && (
                  <button
                    type="button"
                    onClick={handleSelectStrongOnly}
                    style={{
                      padding: '4px 10px',
                      fontSize: '0.72rem',
                      fontWeight: 600,
                      color: 'var(--color-success)',
                      background: 'var(--color-success-muted)',
                      border: '1px solid rgba(34, 197, 94, 0.25)',
                      borderRadius: 5,
                      cursor: 'pointer',
                    }}
                  >
                    Select Strong ({strongCount})
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleSelectAll}
                  style={{
                    padding: '4px 10px',
                    fontSize: '0.72rem',
                    fontWeight: 500,
                    color: 'var(--text-secondary)',
                    background: 'var(--bg-raised)',
                    border: '1px solid var(--border-default)',
                    borderRadius: 5,
                    cursor: 'pointer',
                  }}
                >
                  Select All
                </button>
                <button
                  type="button"
                  onClick={handleClearAll}
                  style={{
                    padding: '4px 10px',
                    fontSize: '0.72rem',
                    fontWeight: 500,
                    color: 'var(--text-muted)',
                    background: 'transparent',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 5,
                    cursor: 'pointer',
                  }}
                >
                  Clear All
                </button>
              </div>
            </div>

            {/* Modal Body / Relationship Cards List */}
            <div
              style={{
                padding: '20px 24px',
                overflowY: 'auto',
                display: 'flex',
                flexDirection: 'column',
                gap: 12,
                maxHeight: 'calc(90vh - 220px)',
              }}
            >
              {candidates.map((c) => {
                const key = getCandidateKey(c);
                const isChecked = selectedKeys.includes(key);
                const scorePct = Math.round(c.score * 100);
                const isStrong = c.confidence_level === 'strong' || c.score >= 0.8;

                return (
                  <div
                    key={key}
                    onClick={() => toggleCandidate(key)}
                    style={{
                      background: isChecked ? 'rgba(99, 102, 241, 0.05)' : 'var(--bg-raised)',
                      border: `1px solid ${isChecked ? 'rgba(99, 102, 241, 0.4)' : 'var(--border-default)'}`,
                      borderRadius: 8,
                      padding: '14px 16px',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 10,
                    }}
                  >
                    {/* Top Row: Checkbox + Table Nodes + Score */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                      {/* Checkbox and Connector */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0, flex: 1 }}>
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => {}} // Handled by container click
                          style={{
                            accentColor: 'var(--accent)',
                            cursor: 'pointer',
                            width: 16,
                            height: 16,
                            flexShrink: 0,
                          }}
                        />

                        {/* Schema Connection Visual Pill */}
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            flexWrap: 'wrap',
                            fontSize: '0.8125rem',
                          }}
                        >
                          {/* Source Table & Column */}
                          <div
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              background: 'var(--bg-surface)',
                              border: '1px solid var(--border-default)',
                              borderRadius: 6,
                              padding: '3px 8px',
                              fontFamily: 'var(--font-mono)',
                            }}
                          >
                            <span style={{ color: 'var(--text-secondary)', marginRight: 3 }}>
                              {c.source_table}.
                            </span>
                            <span style={{ fontWeight: 700, color: 'var(--accent)' }}>
                              {c.source_column}
                            </span>
                          </div>

                          {/* Arrow Connector */}
                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: 4,
                              color: isChecked ? 'var(--accent)' : 'var(--text-muted)',
                            }}
                          >
                            <Link2 size={13} style={{ opacity: 0.8 }} />
                            <ArrowRight size={13} />
                          </div>

                          {/* Target Table & Column */}
                          <div
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              background: 'var(--bg-surface)',
                              border: '1px solid var(--border-default)',
                              borderRadius: 6,
                              padding: '3px 8px',
                              fontFamily: 'var(--font-mono)',
                            }}
                          >
                            <span style={{ color: 'var(--text-secondary)', marginRight: 3 }}>
                              {c.target_table}.
                            </span>
                            <span style={{ fontWeight: 700, color: 'var(--accent)' }}>
                              {c.target_column}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Confidence Score Pill */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                        <span
                          style={{
                            fontSize: '0.72rem',
                            fontWeight: 700,
                            padding: '3px 8px',
                            borderRadius: 6,
                            background: isStrong ? 'var(--color-success-muted)' : 'var(--color-warning-muted)',
                            color: isStrong ? 'var(--color-success)' : 'var(--color-warning)',
                            border: `1px solid ${isStrong ? 'rgba(34, 197, 94, 0.25)' : 'rgba(245, 158, 11, 0.25)'}`,
                          }}
                        >
                          {scorePct}% {isStrong ? 'Strong Match' : 'Possible Match'}
                        </span>
                      </div>
                    </div>

                    {/* Bottom Row: Match Signals & Explanation */}
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        borderTop: '1px solid var(--border-subtle)',
                        paddingTop: 8,
                        fontSize: '0.72rem',
                        color: 'var(--text-muted)',
                        flexWrap: 'wrap',
                        gap: 6,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                        <span style={{ fontWeight: 500 }}>Signals:</span>
                        {c.signals && Array.isArray(c.signals) && c.signals.length > 0 ? (
                          c.signals.map((sig, idx) => (
                            <span
                              key={idx}
                              style={{
                                background: 'var(--bg-overlay)',
                                border: '1px solid var(--border-subtle)',
                                padding: '1px 6px',
                                borderRadius: 4,
                                color: 'var(--text-secondary)',
                                fontSize: '0.68rem',
                              }}
                            >
                              {sig.replace(/_/g, ' ')}
                            </span>
                          ))
                        ) : (
                          <span style={{ color: 'var(--text-disabled)' }}>Column name & type affinity</span>
                        )}
                      </div>

                      {c.cardinality && (
                        <span style={{ color: 'var(--text-disabled)', fontFamily: 'var(--font-mono)' }}>
                          {c.cardinality.replace(/_/g, ' ')}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Modal Footer */}
            <div
              style={{
                padding: '14px 24px',
                borderTop: '1px solid var(--border-subtle)',
                background: 'var(--bg-raised)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Links will be used to construct SQL JOIN clauses.
              </span>

              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="btn-secondary"
                  style={{ height: 34, fontSize: '0.8rem', padding: '0 14px' }}
                >
                  Cancel
                </button>

                <button
                  type="button"
                  onClick={handleApplyAndClose}
                  className="btn-primary"
                  style={{ height: 34, fontSize: '0.8rem', padding: '0 16px', gap: 6 }}
                >
                  <ShieldCheck size={14} />
                  Apply Relationships ({selectedCount})
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
