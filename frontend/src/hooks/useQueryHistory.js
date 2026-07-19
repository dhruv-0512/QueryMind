import { useRef, useCallback } from 'react';

const STORAGE_KEY = 'querymind_query_history';
const MAX_HISTORY = 50;

/**
 * Terminal-style query history navigation (psql / mysql CLI behaviour).
 *
 * ↑  → older query
 * ↓  → newer query, then restores the draft you were typing
 *
 * Smart: on a multi-line textarea, ↑ only fires when cursor is on line 1,
 *        ↓ only fires when cursor is on the last line.
 *
 * History persisted to localStorage.
 */
export function useQueryHistory() {
  // Lazily-loaded from localStorage on first access
  const historyRef = useRef(null);
  // Current position while browsing. -1 = at the "live" input (not browsing)
  const indexRef   = useRef(-1);
  // Snapshot of what the user typed before they started pressing ↑
  const draftRef   = useRef('');

  // ── Private helpers ─────────────────────────────────────────────────────

  const load = () => {
    if (historyRef.current !== null) return historyRef.current;
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      historyRef.current = raw ? JSON.parse(raw) : [];
    } catch {
      historyRef.current = [];
    }
    return historyRef.current;
  };

  const save = (arr) => {
    historyRef.current = arr;
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(arr)); } catch {}
  };

  // ── Public API ───────────────────────────────────────────────────────────

  /**
   * Call on form submit.
   * Adds query to history, resets browsing position.
   */
  const push = useCallback((query) => {
    const q = query.trim();
    if (!q) return;
    const hist = load();
    // Deduplicate consecutive identical entries
    if (hist.length > 0 && hist[hist.length - 1] === q) {
      indexRef.current = -1;
      draftRef.current = '';
      return;
    }
    save([...hist, q].slice(-MAX_HISTORY));
    indexRef.current = -1;
    draftRef.current = '';
  }, []);

  /**
   * Call from textarea onKeyDown.
   *
   * Returns the string to put into the textarea, or null if the key
   * should be handled normally by the browser (cursor movement etc).
   *
   * @param {HTMLTextAreaElement} el          - the textarea DOM node
   * @param {'up'|'down'}         direction
   * @param {string}              liveValue   - current React state value
   */
  const navigate = useCallback((el, direction, liveValue) => {
    const hist = load();
    if (hist.length === 0) return null;

    const pos  = el.selectionStart;
    const text = el.value;         // DOM value (always up-to-date at keydown time)

    // Guard: only intercept when on the edge line
    if (direction === 'up') {
      const nl = text.indexOf('\n');
      if (nl !== -1 && pos > nl) return null; // cursor not on first line
    } else {
      const nl = text.lastIndexOf('\n');
      if (nl !== -1 && pos <= nl) return null; // cursor not on last line
    }

    if (direction === 'up') {
      if (indexRef.current === -1) {
        // First ↑ — save draft, jump to most-recent history entry
        draftRef.current = liveValue;
        indexRef.current = hist.length - 1;
      } else if (indexRef.current > 0) {
        indexRef.current--;
      }
      // If already at oldest, just return it again (clamp)
      return hist[indexRef.current];
    }

    // direction === 'down'
    if (indexRef.current === -1) return null; // not browsing, nothing to do

    if (indexRef.current < hist.length - 1) {
      indexRef.current++;
      return hist[indexRef.current];
    }

    // Went past the newest → restore draft
    indexRef.current = -1;
    return draftRef.current;
  }, []);

  /**
   * Returns how many items are in history (for display hint).
   * Reads synchronously from ref/localStorage.
   */
  const getCount = useCallback(() => load().length, []);

  return { push, navigate, getCount };
}
