import { useState, useEffect, useRef } from 'react';
import { Radio, Clock, Server, ChevronDown, Sparkles, Cpu } from 'lucide-react';
import { useApiStatus } from '../hooks/useApiStatus';

/**
 * Global slim progress bar at the very top edge of the browser viewport.
 * Automatically animates when any API/LLM call is in-flight.
 */
export const GlobalTopProgressBar = () => {
  const { isLoading } = useApiStatus();
  const [visible, setVisible] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let timer;
    let fadeTimer;

    if (isLoading) {
      setVisible(true);
      setProgress(25);
      timer = setInterval(() => {
        setProgress((prev) => {
          if (prev < 70) return prev + Math.random() * 15;
          if (prev < 90) return prev + Math.random() * 5;
          return prev;
        });
      }, 250);
    } else if (visible) {
      setProgress(100);
      fadeTimer = setTimeout(() => {
        setVisible(false);
        setProgress(0);
      }, 350);
    }

    return () => {
      clearInterval(timer);
      clearTimeout(fadeTimer);
    };
  }, [isLoading, visible]);

  if (!visible && !isLoading) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        height: '2.5px',
        zIndex: 99999,
        pointerEvents: 'none',
        overflow: 'hidden',
        background: 'rgba(99, 102, 241, 0.15)',
      }}
      aria-hidden="true"
    >
      <div
        style={{
          height: '100%',
          width: `${progress}%`,
          background: 'linear-gradient(90deg, #6366f1, #818cf8, #38bdf8, #6366f1)',
          backgroundSize: '200% 100%',
          boxShadow: '0 0 10px rgba(99, 102, 241, 0.8), 0 0 4px rgba(56, 189, 248, 0.8)',
          transition: progress === 100 ? 'width 0.2s ease-out, opacity 0.3s ease-out' : 'width 0.35s ease',
          opacity: progress === 100 && !isLoading ? 0 : 1,
        }}
      />
    </div>
  );
};

/**
 * Interactive API & LLM Activity Monitor Badge & Inspector Widget.
 * Can be placed in headers, sidebars, or floating on screens.
 */
export const ApiStatusIndicator = ({ compact = false, floating = false }) => {
  const { isLoading, activeCount, activeRequests, lastCompletedRequest, baseUrl } = useApiStatus();
  const [isOpen, setIsOpen] = useState(false);
  const [now, setNow] = useState(0);
  const popoverRef = useRef(null);

  const isLlmActive = activeRequests.some((r) => r.path === '/query' || r.path.startsWith('/query'));

  // Keep timestamp fresh when dropdown is opened
  useEffect(() => {
    if (isOpen) {
      setNow(Date.now());
      const interval = setInterval(() => setNow(Date.now()), 1000);
      return () => clearInterval(interval);
    }
  }, [isOpen]);

  // Close dropdown on outside click or Escape key
  useEffect(() => {
    const handleOutsideClick = (e) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') setIsOpen(false);
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleOutsideClick);
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  const methodColor = (method) => {
    switch (method) {
      case 'GET': return '#38bdf8';
      case 'POST': return '#22c55e';
      case 'DELETE': return '#ef4444';
      default: return '#a1a1aa';
    }
  };

  const getRelativeTime = (timestamp) => {
    if (!timestamp) return '';
    if (!now) return 'recently';
    const diff = Math.max(0, Math.floor((now - timestamp) / 1000));
    if (diff < 2) return 'just now';
    if (diff < 60) return `${diff}s ago`;
    const mins = Math.floor(diff / 60);
    return `${mins}m ago`;
  };

  // Primary active request label
  const primaryActive = activeRequests.length > 0 ? activeRequests[0] : null;

  return (
    <div
      ref={popoverRef}
      style={{
        position: floating ? 'fixed' : 'relative',
        ...(floating ? { top: 16, right: 16, zIndex: 90 } : {}),
        display: 'inline-flex',
        alignItems: 'center',
      }}
    >
      {/* ── Status Trigger Button / Pill ── */}
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        title={
          isLoading
            ? isLlmActive
              ? 'LLM Model Inference in progress...'
              : `API call in progress (${activeCount} active)`
            : 'AI Pipeline & API Connected (Click for details)'
        }
        aria-label="API and LLM Activity Status"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: compact ? 5 : 7,
          padding: compact ? '3px 8px' : '4px 10px',
          height: compact ? 26 : 28,
          borderRadius: 6,
          background: isLlmActive
            ? 'rgba(168, 85, 247, 0.15)'
            : isLoading
            ? 'rgba(99, 102, 241, 0.12)'
            : 'var(--bg-raised)',
          border: `1px solid ${
            isLlmActive
              ? 'rgba(168, 85, 247, 0.4)'
              : isLoading
              ? 'rgba(99, 102, 241, 0.35)'
              : 'var(--border-default)'
          }`,
          color: isLoading ? 'var(--text-primary)' : 'var(--text-secondary)',
          fontSize: '0.73rem',
          fontWeight: 500,
          cursor: 'pointer',
          transition: 'all 0.15s ease',
          outline: 'none',
          userSelect: 'none',
          boxShadow: isLlmActive
            ? '0 0 12px rgba(168, 85, 247, 0.25)'
            : isLoading
            ? '0 0 10px rgba(99, 102, 241, 0.18)'
            : 'none',
        }}
        onMouseEnter={(e) => {
          if (!isLoading) {
            e.currentTarget.style.borderColor = 'var(--border-strong)';
            e.currentTarget.style.color = 'var(--text-primary)';
          }
        }}
        onMouseLeave={(e) => {
          if (!isLoading) {
            e.currentTarget.style.borderColor = 'var(--border-default)';
            e.currentTarget.style.color = 'var(--text-secondary)';
          }
        }}
      >
        {/* Pulsing Status Dot */}
        <span style={{ position: 'relative', display: 'flex', width: 8, height: 8, flexShrink: 0 }}>
          {isLlmActive ? (
            <>
              <span
                style={{
                  position: 'absolute',
                  inset: 0,
                  borderRadius: '50%',
                  background: '#a855f7',
                  opacity: 0.8,
                  animation: 'apiPing 1.0s cubic-bezier(0, 0, 0.2, 1) infinite',
                }}
              />
              <span
                style={{
                  position: 'relative',
                  display: 'inline-flex',
                  borderRadius: '50%',
                  width: 8,
                  height: 8,
                  background: '#c084fc',
                }}
              />
            </>
          ) : isLoading ? (
            <>
              <span
                style={{
                  position: 'absolute',
                  inset: 0,
                  borderRadius: '50%',
                  background: '#6366f1',
                  opacity: 0.75,
                  animation: 'apiPing 1.2s cubic-bezier(0, 0, 0.2, 1) infinite',
                }}
              />
              <span
                style={{
                  position: 'relative',
                  display: 'inline-flex',
                  borderRadius: '50%',
                  width: 8,
                  height: 8,
                  background: '#818cf8',
                }}
              />
            </>
          ) : (
            <span
              style={{
                display: 'inline-flex',
                borderRadius: '50%',
                width: 8,
                height: 8,
                background: '#22c55e',
                boxShadow: '0 0 5px rgba(34, 197, 94, 0.6)',
              }}
            />
          )}
        </span>

        {/* Text / Badge details */}
        {isLlmActive ? (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <Sparkles size={11} style={{ color: '#c084fc' }} />
            <span style={{ fontWeight: 600, color: '#d8b4fe' }}>
              {compact ? 'LLM' : 'LLM Invoking'}
            </span>
          </span>
        ) : isLoading ? (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span style={{ fontWeight: 600, color: '#a5b4fc' }}>
              {compact ? 'API' : 'API Active'}
            </span>
            {activeCount > 1 && (
              <span
                style={{
                  fontSize: '0.65rem',
                  padding: '1px 5px',
                  borderRadius: 4,
                  background: 'rgba(99, 102, 241, 0.25)',
                  color: '#e0e7ff',
                  fontWeight: 600,
                }}
              >
                {activeCount}
              </span>
            )}
            {!compact && primaryActive && (
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.67rem',
                  color: 'var(--text-muted)',
                  maxWidth: 120,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
                title={`${primaryActive.method} ${primaryActive.path}`}
              >
                {primaryActive.path}
              </span>
            )}
          </span>
        ) : (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <span>{compact ? 'LLM: Ready' : 'AI Engine: Ready'}</span>
          </span>
        )}

        <ChevronDown
          size={11}
          style={{
            opacity: 0.6,
            transform: isOpen ? 'rotate(180deg)' : 'none',
            transition: 'transform 0.15s ease',
            marginLeft: 1,
          }}
        />
      </button>

      {/* ── Popover Details Dropdown ── */}
      {isOpen && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            right: 0,
            width: 310,
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-default)',
            borderRadius: 8,
            boxShadow: '0 8px 24px rgba(0, 0, 0, 0.4), 0 0 0 1px var(--border-subtle)',
            padding: 14,
            zIndex: 9999,
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
            animation: 'fadeIn 0.15s ease-out',
          }}
        >
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Radio size={14} style={{ color: isLoading ? '#818cf8' : '#22c55e' }} />
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                AI & API Pipeline Monitor
              </span>
            </div>
            <span
              style={{
                fontSize: '0.68rem',
                fontWeight: 600,
                color: isLlmActive ? '#d8b4fe' : isLoading ? '#a5b4fc' : '#22c55e',
                background: isLlmActive ? 'rgba(168, 85, 247, 0.15)' : isLoading ? 'rgba(99, 102, 241, 0.12)' : 'rgba(34, 197, 94, 0.12)',
                padding: '2px 7px',
                borderRadius: 4,
              }}
            >
              {isLlmActive ? 'LLM Invoking' : isLoading ? `${activeCount} in-flight` : 'Ready'}
            </span>
          </div>

          {/* AI Model & LLM Engine Status Box */}
          <div
            style={{
              padding: '8px 10px',
              background: 'var(--bg-raised)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 6,
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4 }}>
                <Cpu size={12} style={{ color: 'var(--accent)' }} />
                LLM Engine
              </span>
              <span style={{ fontSize: '0.68rem', fontWeight: 600, color: isLlmActive ? '#d8b4fe' : '#22c55e' }}>
                {isLlmActive ? 'Inference Running…' : 'Gemini 3.5 Flash'}
              </span>
            </div>

            <p style={{ fontSize: '0.68rem', color: 'var(--text-muted)', margin: 0, lineHeight: 1.4 }}>
              Natural language queries are grounded with ChromaDB RAG and converted to PostgreSQL SQL via LLM inference.
            </p>
          </div>

          {/* Active Calls List */}
          {isLoading && activeRequests.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: '0.68rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-muted)' }}>
                In-flight Requests
              </span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 120, overflowY: 'auto' }}>
                {activeRequests.map((req) => (
                  <div
                    key={req.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '5px 8px',
                      background: 'var(--bg-raised)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: 5,
                      fontSize: '0.73rem',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                      <span style={{ fontWeight: 700, color: methodColor(req.method), fontSize: '0.67rem' }}>
                        {req.method}
                      </span>
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          color: 'var(--text-primary)',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                        title={req.path}
                      >
                        {req.path}
                      </span>
                    </div>
                    <span style={{ fontSize: '0.67rem', color: req.path === '/query' ? '#c084fc' : 'var(--text-muted)', flexShrink: 0, display: 'flex', alignItems: 'center', gap: 3 }}>
                      {req.path === '/query' && <Sparkles size={10} />}
                      {req.path === '/query' ? 'LLM Call…' : 'Calling…'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Last Completed Request */}
          {lastCompletedRequest && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <span style={{ fontSize: '0.68rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-muted)' }}>
                Last Operation
              </span>
              <div
                style={{
                  padding: '8px 10px',
                  background: 'var(--bg-raised)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 6,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                    <span style={{ fontWeight: 700, color: methodColor(lastCompletedRequest.method), fontSize: '0.68rem' }}>
                      {lastCompletedRequest.method}
                    </span>
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '0.73rem',
                        color: 'var(--text-primary)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                      title={lastCompletedRequest.path}
                    >
                      {lastCompletedRequest.path}
                    </span>
                  </div>

                  <span
                    style={{
                      fontSize: '0.68rem',
                      fontWeight: 600,
                      color: lastCompletedRequest.success ? '#22c55e' : '#ef4444',
                    }}
                  >
                    {lastCompletedRequest.status || (lastCompletedRequest.success ? '200' : 'ERR')}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 2 }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                    <Clock size={11} />
                    {lastCompletedRequest.duration}ms
                  </span>
                  <span>{getRelativeTime(lastCompletedRequest.timestamp)}</span>
                </div>

                {lastCompletedRequest.error && (
                  <p style={{ fontSize: '0.68rem', color: 'var(--color-danger)', marginTop: 2 }}>
                    Error: {lastCompletedRequest.error}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Backend Info Footer */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 6, borderTop: '1px solid var(--border-subtle)', fontSize: '0.68rem', color: 'var(--text-muted)' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <Server size={11} />
              Backend:
            </span>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                color: 'var(--text-secondary)',
                maxWidth: 160,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
              title={baseUrl}
            >
              {baseUrl ? baseUrl.replace(/^https?:\/\//, '') : 'connected'}
            </span>
          </div>
        </div>
      )}

      {/* Embedded Animations */}
      <style>{`
        @keyframes apiPing {
          0% { transform: scale(0.95); opacity: 0.8; }
          70%, 100% { transform: scale(2.2); opacity: 0; }
        }
      `}</style>
    </div>
  );
};
