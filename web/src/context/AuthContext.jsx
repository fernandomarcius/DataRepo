import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import api, { getStoredToken, setStoredToken } from '../api/client';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    const refresh = useCallback(async () => {
        const token = getStoredToken();
        if (!token) {
            setUser(null);
            setLoading(false);
            return;
        }
        try {
            const res = await api.get('/auth/me');
            setUser(res.data);
        } catch (err) {
            setStoredToken(null);
            setUser(null);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        refresh();
    }, [refresh]);

    useEffect(() => {
        const handler = () => {
            setUser(null);
        };
        window.addEventListener('auth:unauthorized', handler);
        return () => window.removeEventListener('auth:unauthorized', handler);
    }, []);

    const login = useCallback(async (username, password) => {
        const res = await api.post('/auth/login', { username, password });
        setStoredToken(res.data.token);
        setUser(res.data.user);
        return res.data.user;
    }, []);

    const logout = useCallback(() => {
        setStoredToken(null);
        setUser(null);
    }, []);

    const hasPermission = useCallback((flag) => {
        return Boolean(user?.perms?.[flag]);
    }, [user]);

    return (
        <AuthContext.Provider value={{ user, loading, login, logout, hasPermission, refresh }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
    return ctx;
};
