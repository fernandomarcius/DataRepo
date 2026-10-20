import React, { useState } from 'react';
import { useNavigate, useLocation, Navigate, Link } from 'react-router-dom';
import { LogIn, Loader2, AlertCircle, CheckCircle, Eye, EyeOff } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { rota } from '../prefixo';

const Login = () => {
    const { login, user, loading } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState(null);
    const [showPassword, setShowPassword] = useState(false);
    const notice = location.state?.notice;

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-slate-100 dark:bg-slate-900">
                <Loader2 className="w-8 h-8 text-violet-500 animate-spin" />
            </div>
        );
    }
    if (user) {
        const target = location.state?.from || '/';
        return <Navigate to={target} replace />;
    }

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!username || !password) return;
        setSubmitting(true);
        setError(null);
        try {
            await login(username, password);
            const target = location.state?.from || '/';
            navigate(target, { replace: true });
        } catch (err) {
            setError(err.response?.data?.error || 'Falha ao entrar');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-100 dark:bg-slate-900 p-4">
            <div className="w-full max-w-md bg-white dark:bg-slate-800 rounded-xl shadow-xl border border-slate-200 dark:border-slate-700 p-8">
                <div className="flex items-center gap-3 mb-6">
                    <img src={rota('/logo.svg')} alt="DataRepo" className="w-10 h-10 rounded-md object-cover" />
                    <h1 className="text-2xl font-bold text-violet-600 dark:text-violet-400">
                        Data App
                    </h1>
                </div>
                <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-1">Entrar</h2>
                <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
                    Use suas credenciais para acessar o sistema.
                </p>

                {notice && !error && (
                    <div className="mb-4 p-3 rounded-md bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 text-sm flex items-center gap-2">
                        <CheckCircle className="w-4 h-4 shrink-0" />
                        {notice}
                    </div>
                )}

                {error && (
                    <div className="mb-4 p-3 rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 text-sm flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 shrink-0" />
                        {error}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                            Usuário
                        </label>
                        <input
                            type="text"
                            autoFocus
                            autoComplete="username"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            className="w-full px-3 py-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-violet-500 focus:border-transparent"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                            Senha
                        </label>
                        <div className="relative">
                            <input
                                type={showPassword ? 'text' : 'password'}
                                autoComplete="current-password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="w-full px-3 py-2 pr-10 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-violet-500 focus:border-transparent"
                            />
                            <button
                                type="button"
                                onClick={() => setShowPassword(v => !v)}
                                tabIndex={-1}
                                className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                                aria-label={showPassword ? 'Ocultar senha' : 'Mostrar senha'}
                            >
                                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                            </button>
                        </div>
                    </div>
                    <button
                        type="submit"
                        disabled={submitting || !username || !password}
                        className="w-full bg-violet-600 text-white px-4 py-2 rounded-md hover:bg-violet-700 disabled:opacity-50 flex items-center justify-center gap-2 transition-colors"
                    >
                        {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <LogIn className="w-4 h-4" />}
                        Entrar
                    </button>
                </form>

                <div className="mt-6 text-center">
                    <Link to="/forgot-password" className="text-sm text-violet-600 dark:text-violet-400 hover:underline">
                        Esqueci minha senha
                    </Link>
                </div>
            </div>
        </div>
    );
};

export default Login;
