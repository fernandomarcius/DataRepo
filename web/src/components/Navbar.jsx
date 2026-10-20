import React, { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { Code, Database, FileText, Upload, Sun, Moon, Users, LogOut, ShieldCheck, Network, KeyRound } from 'lucide-react';
import ChangePasswordModal from './ChangePasswordModal';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { rota } from '../prefixo';

const linkClass = ({ isActive }) => `
    px-4 py-2 rounded-md flex items-center gap-2 text-sm font-medium transition-colors
    ${isActive
        ? 'bg-violet-50 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300'
        : 'text-slate-600 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-700/50'}
`;

const Navbar = () => {
    const { theme, toggleTheme } = useTheme();
    const { user, logout, hasPermission } = useAuth();
    const navigate = useNavigate();
    const [showChangePassword, setShowChangePassword] = useState(false);

    const handleLogout = () => {
        logout();
        navigate('/login', { replace: true });
    };

    return (
        <nav className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 mb-6 transition-colors duration-200">
            <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
                <div className="flex items-center gap-8">
                    <h1 className="text-xl font-bold text-violet-600 dark:text-violet-400 flex items-center gap-2">
                        <img src={rota('/logo.svg')} alt="DataRepo" className="w-8 h-8 rounded-md object-cover" />
                        Data App
                    </h1>

                    <div className="flex items-center gap-2">
                        {hasPermission('can_query') && (
                            <NavLink to="/" className={linkClass}>
                                <Database className="w-4 h-4" />
                                Query
                            </NavLink>
                        )}

                        <NavLink to="/reports" className={linkClass}>
                            <FileText className="w-4 h-4" />
                            Views
                        </NavLink>

                        {hasPermission('can_manage_functions') && (
                            <NavLink to="/functions" className={linkClass}>
                                <Code className="w-4 h-4" />
                                Funções
                            </NavLink>
                        )}

                        {hasPermission('can_upload') && (
                            <NavLink to="/upload" className={linkClass}>
                                <Upload className="w-4 h-4" />
                                Upload
                            </NavLink>
                        )}

                        {hasPermission('can_manage_users') && (
                            <NavLink to="/users" className={linkClass}>
                                <Users className="w-4 h-4" />
                                Usuários
                            </NavLink>
                        )}

                        {hasPermission('can_view_audit') && (
                            <NavLink to="/audit" className={linkClass}>
                                <ShieldCheck className="w-4 h-4" />
                                Audit Log
                            </NavLink>
                        )}

                        {hasPermission('can_manage_connections') && (
                            <NavLink to="/connections" className={linkClass}>
                                <Network className="w-4 h-4" />
                                Conexões
                            </NavLink>
                        )}
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    <button
                        onClick={toggleTheme}
                        className="p-2 rounded-md text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700 transition-colors"
                        title={theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
                    >
                        {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
                    </button>
                    {user && (
                        <div className="flex items-center gap-2 pl-3 border-l border-slate-200 dark:border-slate-700">
                            <button
                                onClick={() => setShowChangePassword(true)}
                                title="Alterar senha"
                                className="text-sm font-medium text-slate-700 dark:text-slate-300 hover:text-violet-600 dark:hover:text-violet-400 flex items-center gap-1.5 transition-colors"
                            >
                                <KeyRound className="w-3.5 h-3.5" />
                                {user.username}
                            </button>
                            <button
                                onClick={handleLogout}
                                className="p-2 rounded-md text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700 transition-colors"
                                title="Sair"
                            >
                                <LogOut className="w-4 h-4" />
                            </button>
                        </div>
                    )}
                </div>
            </div>

            {showChangePassword && (
                <ChangePasswordModal
                    username={user?.username}
                    onClose={() => setShowChangePassword(false)}
                />
            )}
        </nav>
    );
};

export default Navbar;
