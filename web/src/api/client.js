import axios from 'axios';
import { prefixo } from '../prefixo';

// Token stored in localStorage. Acceptable for this internal tool (no user-generated
// content, no third-party scripts). Do not introduce XSS vectors assuming the token is safe.
const TOKEN_KEY = 'token';

export const getStoredToken = () => localStorage.getItem(TOKEN_KEY);
export const setStoredToken = (token) => {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
};

const api = axios.create({
    // Com o prefixo da plataforma quando houver (ver prefixo.js); na raiz fica /api/v1.
    baseURL: `${prefixo()}/api/v1`,
});

api.interceptors.request.use((config) => {
    const token = getStoredToken();
    if (token) {
        config.headers = config.headers || {};
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

api.interceptors.response.use(
    (res) => res,
    (err) => {
        if (err?.response?.status === 401) {
            setStoredToken(null);
            window.dispatchEvent(new CustomEvent('auth:unauthorized'));
        }
        return Promise.reject(err);
    }
);

export function forgotPassword(username) {
    return api.post('/auth/forgot-password', { username });
}

export function resetPassword(token, password) {
    return api.post('/auth/reset-password', { token, password });
}

export function changePassword(currentPassword, newPassword) {
    return api.post('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
    });
}

export function getAuditLogs(params = {}, signal) {
    return api.get('/audit-logs', { params, signal });
}

export function getAuditLog(id) {
    return api.get(`/audit-logs/${id}`);
}

export function getConnections() {
    return api.get('/connections');
}

export function getConnection(id) {
    return api.get(`/connections/${id}`);
}

export function createConnection(payload) {
    return api.post('/connections', payload);
}

export function updateConnection(id, payload) {
    return api.put(`/connections/${id}`, payload);
}

export function deleteConnection(id) {
    return api.delete(`/connections/${id}`);
}

export function testConnection(payload) {
    return api.post('/connections/test', payload);
}

export function syncConnection(id) {
    return api.post(`/connections/${id}/sync`);
}

export function getConnectionTables(id) {
    return api.get(`/connections/${id}/tables`);
}

export function getConnectionTableSchema(id, tableName) {
    return api.get(`/connections/${id}/tables/${tableName}/schema`);
}

export function materializeReport(id, schedule) {
    return api.post(`/reports/${id}/materialize`, { schedule });
}

export function unmaterializeReport(id) {
    return api.delete(`/reports/${id}/materialize`);
}

export function refreshReport(id) {
    return api.post(`/reports/${id}/refresh`);
}

export default api;
