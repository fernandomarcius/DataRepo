import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import UploadSection from './components/UploadSection';
import QueryInterface from './components/QueryInterface';
import ReportsPage from './components/ReportsPage';
import FunctionsPage from './components/FunctionsPage';
import UsersPage from './components/UsersPage';
import AuditLogPage from './components/AuditLogPage';
import ConnectionsPage from './components/ConnectionsPage';
import Login from './components/Login';
import ForgotPassword from './components/ForgotPassword';
import ResetPassword from './components/ResetPassword';
import Navbar from './components/Navbar';
import RequireAuth from './auth/RequireAuth';
import RequirePermission from './auth/RequirePermission';

import { ThemeProvider } from './context/ThemeContext';
import { AuthProvider } from './context/AuthContext';
import { prefixo } from './prefixo';

const Shell = () => (
    <div className="min-h-screen bg-slate-100 dark:bg-slate-900 transition-colors duration-200">
        <Navbar />
        <div className="max-w-7xl mx-auto px-4 pb-8">
            <Outlet />
        </div>
    </div>
);

function App() {
    return (
        <ThemeProvider>
            {/* Sob a plataforma as rotas ficam abaixo de /workloads/{tenant}/{servico} (prefixo.js). */}
            <Router basename={prefixo() || '/'}>
                <AuthProvider>
                    <Routes>
                        <Route path="/login" element={<Login />} />
                        <Route path="/forgot-password" element={<ForgotPassword />} />
                        <Route path="/reset-password/:token" element={<ResetPassword />} />
                        <Route element={<RequireAuth><Shell /></RequireAuth>}>
                            <Route
                                path="/"
                                element={
                                    <RequirePermission flag="can_query" redirectTo="/reports">
                                        <QueryInterface />
                                    </RequirePermission>
                                }
                            />
                            <Route path="/reports" element={<ReportsPage />} />
                            <Route
                                path="/functions"
                                element={
                                    <RequirePermission flag="can_manage_functions">
                                        <FunctionsPage />
                                    </RequirePermission>
                                }
                            />
                            <Route
                                path="/upload"
                                element={
                                    <RequirePermission flag="can_upload">
                                        <UploadSection />
                                    </RequirePermission>
                                }
                            />
                            <Route
                                path="/users"
                                element={
                                    <RequirePermission flag="can_manage_users">
                                        <UsersPage />
                                    </RequirePermission>
                                }
                            />
                            <Route
                                path="/audit"
                                element={
                                    <RequirePermission flag="can_view_audit">
                                        <AuditLogPage />
                                    </RequirePermission>
                                }
                            />
                            <Route
                                path="/connections"
                                element={
                                    <RequirePermission flag="can_manage_connections">
                                        <ConnectionsPage />
                                    </RequirePermission>
                                }
                            />
                            <Route path="*" element={<Navigate to="/" replace />} />
                        </Route>
                    </Routes>
                </AuthProvider>
            </Router>
        </ThemeProvider>
    );
}

export default App;
