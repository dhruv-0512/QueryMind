import { useState } from 'react';
import { Info, X, Rocket } from 'lucide-react';

export const DemoBanner = ({ alwaysShow = false }) => {
  const [isDismissed, setIsDismissed] = useState(() => {
    if (alwaysShow) return false;
    try {
      return localStorage.getItem('querymind_demo_banner_dismissed') === 'true';
    } catch {
      return false;
    }
  });

  // Display only in production deployments
  const isProd =
    import.meta.env.PROD ||
    (typeof window !== 'undefined' &&
      window.location.hostname !== 'localhost' &&
      window.location.hostname !== '127.0.0.1');

  if (!isProd || (!alwaysShow && isDismissed)) {
    return null;
  }

  const handleDismiss = () => {
    setIsDismissed(true);
    try {
      localStorage.setItem('querymind_demo_banner_dismissed', 'true');
    } catch (e) {
      console.error('Failed to save demo banner preference:', e);
    }
  };

  return (
    <div
      style={{
        background: 'rgba(59, 130, 246, 0.08)',
        border: '1px solid rgba(59, 130, 246, 0.22)',
        borderRadius: '8px',
        padding: '12px 16px',
        marginBottom: '20px',
        display: 'flex',
        alignItems: 'flex-start',
        gap: '12px',
        position: 'relative',
        transition: 'all 0.2s ease',
        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.12)',
      }}
      className="animate-fade-in"
      role="region"
      aria-label="Demo Deployment Information"
    >
      {/* Blue info/rocket icon */}
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: 6,
          background: 'rgba(59, 130, 246, 0.15)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          color: '#60a5fa',
        }}
      >
        <Info size={18} />
      </div>

      {/* Banner text block */}
      <div style={{ flex: 1, minWidth: 0, paddingRight: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
          <span style={{ fontSize: '0.875rem', fontWeight: 600, color: '#93c5fd' }}>
            🚀 Demo Deployment
          </span>
        </div>
        <p
          style={{
            fontSize: '0.8125rem',
            lineHeight: '1.45',
            color: 'var(--text-secondary, #cbd5e1)',
            margin: 0,
          }}
        >
          QueryMind is hosted on free-tier cloud infrastructure (Render, Neon, Upstash, and ChromaDB).
          After periods of inactivity, the first upload or query may take 30–60 seconds while backend services wake up.
          Once active, subsequent requests are near real-time.
        </p>
      </div>

      {/* Dismiss button */}
      <button
        onClick={handleDismiss}
        aria-label="Dismiss banner"
        title="Dismiss banner"
        style={{
          background: 'transparent',
          border: 'none',
          color: 'var(--text-muted, #94a3b8)',
          cursor: 'pointer',
          padding: '4px',
          borderRadius: '4px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          transition: 'color 0.15s ease, background 0.15s ease',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.color = '#ffffff';
          e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.color = 'var(--text-muted, #94a3b8)';
          e.currentTarget.style.background = 'transparent';
        }}
      >
        <X size={16} />
      </button>
    </div>
  );
};
