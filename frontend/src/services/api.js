const rawBaseUrl = import.meta.env.VITE_API_URL || 'https://querymind-lnq3.onrender.com';
export const BASE_URL = rawBaseUrl.replace(/\/+$/, '');

export const getTokens = () => {
  return {
    accessToken: localStorage.getItem('access_token'),
    refreshToken: localStorage.getItem('refresh_token'),
  };
};

export const setTokens = (access, refresh) => {
  localStorage.setItem('access_token', access);
  localStorage.setItem('refresh_token', refresh);
};

export const clearTokens = () => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user_role');
  localStorage.removeItem('user_email');
  localStorage.removeItem('querymind_demo_banner_dismissed');
};

let isRefreshing = false;
let refreshSubscribers = [];

const subscribeTokenRefresh = (cb) => {
  refreshSubscribers.push(cb);
};

const onRefreshed = (token) => {
  refreshSubscribers.forEach((cb) => cb(token));
  refreshSubscribers = [];
};

// ─── API Activity Tracking ─────────────────────────────────
let reqIdCounter = 0;
const activeRequestsMap = new Map();
let lastCompletedRequest = null;
const activityListeners = new Set();

export const getApiActivityState = () => ({
  activeCount: activeRequestsMap.size,
  isLoading: activeRequestsMap.size > 0,
  activeRequests: Array.from(activeRequestsMap.values()),
  lastCompletedRequest,
  baseUrl: BASE_URL,
});

export const subscribeApiActivity = (callback) => {
  activityListeners.add(callback);
  // Call immediately with current state
  try {
    callback(getApiActivityState());
  } catch (err) {
    console.error('Error invoking API activity listener:', err);
  }

  return () => {
    activityListeners.delete(callback);
  };
};

const notifyActivity = () => {
  const state = getApiActivityState();
  activityListeners.forEach((listener) => {
    try {
      listener(state);
    } catch (err) {
      console.error('Error in API activity subscriber:', err);
    }
  });

  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('api_activity_change', { detail: state }));
  }
};

async function apiRequest(path, options = {}) {
  const reqId = ++reqIdCounter;
  const method = (options.method || 'GET').toUpperCase();
  const startTime = Date.now();

  const reqInfo = {
    id: reqId,
    method,
    path,
    startTime,
  };

  activeRequestsMap.set(reqId, reqInfo);
  notifyActivity();

  let reqStatus = null;
  let reqError = null;

  const { accessToken } = getTokens();
  
  const headers = new Headers(options.headers || {});
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }
  
  // Set Content-Type unless uploading FormData (boundary set automatically by fetch)
  if (!(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  try {
    let response;
    try {
      response = await fetch(`${BASE_URL}${path}`, {
        ...options,
        headers,
      });
    } catch (networkErr) {
      // If network dropped or cold-start reconnection needed, retry once after 1.2s
      if (networkErr.name === 'TypeError' || (networkErr.message && networkErr.message.toLowerCase().includes('fetch'))) {
        await new Promise((r) => setTimeout(r, 1200));
        try {
          response = await fetch(`${BASE_URL}${path}`, {
            ...options,
            headers,
          });
        } catch (retryErr) {
          throw new Error('Unable to connect to backend server. The cloud backend may be restarting or waking from cold sleep. Please retry in a moment.', { cause: retryErr });
        }
      } else {
        throw networkErr;
      }
    }

    reqStatus = response.status;

    if (response.status === 401) {
      // Don't attempt refresh for login/register routes
      if (path === '/auth/login' || path === '/auth/register') {
        const errorData = await response.json().catch(() => ({ detail: 'Invalid credentials' }));
        throw new Error(errorData.detail || 'Authentication failed');
      }

      const { refreshToken } = getTokens();
      if (!refreshToken) {
        clearTokens();
        window.dispatchEvent(new Event('auth_failed'));
        throw new Error('Session expired. Please log in again.');
      }

      if (!isRefreshing) {
        isRefreshing = true;
        try {
          const refreshRes = await fetch(`${BASE_URL}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken }),
          });

          if (!refreshRes.ok) {
            throw new Error('Failed to refresh token.');
          }

          const data = await refreshRes.json();
          setTokens(data.access_token, data.refresh_token);
          isRefreshing = false;
          onRefreshed(data.access_token);
        } catch (err) {
          isRefreshing = false;
          clearTokens();
          window.dispatchEvent(new Event('auth_failed'));
          throw new Error('Session expired. Please log in again.', { cause: err });
        }
      }

      // Return a promise that resolves when the token refresh finishes
      return await new Promise((resolve, reject) => {
        subscribeTokenRefresh((newToken) => {
          headers.set('Authorization', `Bearer ${newToken}`);
          fetch(`${BASE_URL}${path}`, { ...options, headers })
            .then(async (res) => {
              reqStatus = res.status;
              if (!res.ok) {
                const errorData = await res.json().catch(() => ({ detail: 'Request failed' }));
                throw new Error(errorData.detail || 'Request failed after token refresh');
              }
              if (res.status === 204) {
                return null;
              }
              return res.json();
            })
            .then(resolve)
            .catch(reject);
        });
      });
    }

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
      let detailMsg = 'Request failed';
      if (Array.isArray(errorData.detail)) {
        detailMsg = errorData.detail.map((d) => {
          const field = d.loc && d.loc.length > 0 ? d.loc[d.loc.length - 1] : '';
          return field ? `${field}: ${d.msg}` : d.msg;
        }).join(' | ');
      } else if (typeof errorData.detail === 'string') {
        detailMsg = errorData.detail;
      }
      throw new Error(detailMsg);
    }

    if (response.status === 204) {
      return null;
    }

    return await response.json();
  } catch (error) {
    reqError = error;
    loggerError(error);
    throw error;
  } finally {
    const duration = Date.now() - startTime;
    lastCompletedRequest = {
      id: reqId,
      method,
      path,
      status: reqStatus,
      duration,
      timestamp: Date.now(),
      success: !reqError,
      error: reqError ? reqError.message : null,
    };
    activeRequestsMap.delete(reqId);
    notifyActivity();
  }
}

function loggerError(error) {
  console.error('API Call error:', error.message || error);
}

export const api = {
  get: (path) => apiRequest(path, { method: 'GET' }),
  post: (path, body) => apiRequest(path, { method: 'POST', body: JSON.stringify(body) }),
  postMultipart: (path, formData) => apiRequest(path, { method: 'POST', body: formData }),
  delete: (path) => apiRequest(path, { method: 'DELETE' }),
};
