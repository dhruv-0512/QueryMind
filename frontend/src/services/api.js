const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

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

async function apiRequest(path, options = {}) {
  const { accessToken } = getTokens();
  
  const headers = new Headers(options.headers || {});
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }
  
  // Set Content-Type unless we are uploading a file (FormData needs boundary set automatically by fetch)
  if (!(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      // Don't attempt refresh for login routes
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
      return new Promise((resolve, reject) => {
        subscribeTokenRefresh((newToken) => {
          headers.set('Authorization', `Bearer ${newToken}`);
          fetch(`${BASE_URL}${path}`, { ...options, headers })
            .then(async (res) => {
              if (!res.ok) {
                const errorData = await res.json().catch(() => ({ detail: 'Request failed' }));
                throw new Error(errorData.detail || 'Request failed after token refresh');
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
      throw new Error(errorData.detail || 'Request failed');
    }

    if (response.status === 204) {
      return null;
    }

    return await response.json();
  } catch (error) {
    loggerError(error);
    throw error;
  }
}

function loggerError(error) {
  console.error("API Call error:", error.message || error);
}

export const api = {
  get: (path) => apiRequest(path, { method: 'GET' }),
  post: (path, body) => apiRequest(path, { method: 'POST', body: JSON.stringify(body) }),
  postMultipart: (path, formData) => apiRequest(path, { method: 'POST', body: formData }),
  delete: (path) => apiRequest(path, { method: 'DELETE' }),
};
