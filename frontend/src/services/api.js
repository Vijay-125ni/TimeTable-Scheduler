import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('token');
      const isLoginRequest = error.config && error.config.url && error.config.url.includes('/auth/login');
      const isLoginPage = window.location.pathname === '/login';
      if (!isLoginRequest && !isLoginPage) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);


// Simple In-Memory Cache for ultra-fast page loads
const cache = new Map();
export const clearApiCache = () => cache.clear();

const getCached = async (url) => {
    if (cache.has(url)) {
        // Return a clone to prevent accidental mutations by components
        return { data: JSON.parse(JSON.stringify(cache.get(url))) };
    }
    const response = await api.get(url);
    cache.set(url, response.data);
    return response;
};

const withCacheClear = (requestPromise) => {
    return requestPromise.then(res => {
        clearApiCache();
        return res;
    });
};

export const authAPI = {
  login: (email, password) => api.post('/auth/login', new URLSearchParams({ username: email, password })),
  register: (data) => api.post('/auth/register', data),
  getCurrentUser: () => api.get('/auth/me'),
  changePassword: (data) => api.post('/auth/change-password', data),
  createFaculty: (data) => api.post('/auth/faculty', data),
  getFacultyAccounts: () => api.get('/auth/faculty'),
  deleteFacultyAccount: (id) => api.delete(`/auth/faculty/${id}`),
};

export const batchAPI = {
  getAll: () => getCached('/batches'),
  create: (data) => withCacheClear(api.post('/batches', data)),
  update: (id, data) => withCacheClear(api.put(`/batches/${id}`, data)),
  delete: (id) => withCacheClear(api.delete(`/batches/${id}`))
};

export const departmentAPI = {
  getAll: () => getCached('/departments'),
  create: (data) => withCacheClear(api.post('/departments', data)),
  update: (id, data) => withCacheClear(api.put(`/departments/${id}`, data)),
  delete: (id) => withCacheClear(api.delete(`/departments/${id}`))
};

export const classAPI = {
  getAll: () => getCached('/classes'),
  create: (data) => withCacheClear(api.post('/classes', data)),
  update: (id, data) => withCacheClear(api.put(`/classes/${id}`, data)),
  delete: (id) => withCacheClear(api.delete(`/classes/${id}`))
};

export const roomAPI = {
  getAll: () => getCached('/rooms'),
  create: (data) => withCacheClear(api.post('/rooms', data)),
  update: (id, data) => withCacheClear(api.put(`/rooms/${id}`, data)),
  delete: (id) => withCacheClear(api.delete(`/rooms/${id}`))
};

export const subjectAPI = {
  getAll: () => getCached('/subjects'),
  create: (data) => withCacheClear(api.post('/subjects', data)),
  update: (id, data) => withCacheClear(api.put(`/subjects/${id}`, data)),
  map: (id, data) => withCacheClear(api.post(`/subjects/${id}/map`, data)),
  delete: (id) => withCacheClear(api.delete(`/subjects/${id}`))
};

export const facultyAPI = {
  getAll: () => getCached('/faculty'),
  create: (data) => withCacheClear(api.post('/faculty', data)),
  update: (id, data) => withCacheClear(api.put(`/faculty/${id}`, data)),
  delete: (id) => withCacheClear(api.delete(`/faculty/${id}`))
};

export const timetableAPI = {
  generate: (data) => api.post('/generate', data),
  generateConstraintsFromFiles: (files, data = {}) => {
    const formData = new FormData();
    Array.from(files || []).forEach((file) => formData.append('files', file));
    Object.entries(data).forEach(([key, value]) => {
      if (value !== undefined && value !== null) formData.append(key, value);
    });
    return api.post('/constraints/from-files', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  getAll: () => api.get('/timetables'),
  getById: (id) => api.get(`/timetables/${id}`),
  delete: (id) => api.delete(`/timetables/${id}`)
};

export const ingestionAPI = {
  upload: (files) => {
    const formData = new FormData();
    Array.from(files).forEach((f) => formData.append('files', f));
    return api.post('/knowledge/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  getProgress: (sessionId) => `${API_BASE_URL}/knowledge/progress/${sessionId}`,
  getReview: (sessionId) => api.get(`/knowledge/review/${sessionId}`),
  applyDecisions: (sessionId, decisions) =>
    api.post('/knowledge/review/apply', { session_id: sessionId, decisions }),
  applyAutoMerges: (sessionId) =>
    api.post(`/knowledge/review/apply-auto/${sessionId}`),
  getHistory: () => api.get('/knowledge/history'),
  getSessionStatus: (sessionId) => api.get(`/knowledge/session/${sessionId}`),
  rollbackSession: (sessionId) =>
    api.post(`/knowledge/history/${sessionId}/rollback`),
  getAuditLogs: (params = {}) => api.get('/knowledge/audit-logs', { params }),
  getAliases: () => api.get('/knowledge/aliases'),
  createAlias: (data) => api.post('/knowledge/aliases', data),
  deleteAlias: (id) => api.delete(`/knowledge/aliases/${id}`),
};

export default api;
