import React, { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AlertCircle, Eye, EyeOff, KeyRound, Loader2 } from 'lucide-react';
import { resetPassword } from '../api/client';
import { rota } from '../prefixo';

const MIN_PASSWORD_LENGTH = 8;

const ERROR_MESSAGES = {
    'Invalid or expired token': 'Link inválido ou expirado. Solicite um novo.',
    'Password must be at least 8 characters': `A senha deve ter pelo menos ${MIN_PASSWORD_LENGTH} caracteres.`,
    'Token and password are required': 'Preencha a nova senha.',
};

const ResetPassword = () => {
    const { token } = useParams();
    const navigate = useNavigate();
    const [password, setPassword] = useState('');
    const [confirmation, setConfirmation] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState(null);
    const [expired, setExpired] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (password.length < MIN_PASSWORD_LENGTH) {
            setError(`A senha deve ter pelo menos ${MIN_PASSWORD_LENGTH} caracteres.`);
            return;
        }
        if (password !== confirmation) {
            setError('As senhas não conferem.');
            return;
        }
        setSubmitting(true);
        setError(null);
        try {
            await resetPassword(token, password);
            navigate('/login', {
                replace: true,
                state: { notice: 'Senha redefinida. Entre com a nova senha.' },
            });
        } catch (err) {
            const apiError = err.response?.data?.error;
            setExpired(apiError === 'Invalid or expired token');
            setError(ERROR_MESSAGES[apiError] || 'Não foi possível redefinir a senha.');
        } finally {
            setSubmitting(false);
        }
    };

    const inputClass = 'w-full px-3 py-2 pr-10 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-violet-500 focus:border-transparent';

    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-100 dark:bg-slate-900 p-4">
            <div className="w-full max-w-md bg-white dark:bg-slate-800 rounded-xl shadow-xl border border-slate-200 dark:border-slate-700 p-8">
                <div className="flex items-center gap-3 mb-6">
                    <img src={rota('/logo.svg')} alt="DataRepo" className="w-10 h-10 rounded-md object-cover" />
                    <h1 className="text-2xl font-bold text-violet-600 dark:text-violet-400">
                        Data App
                    </h1>
                </div>
                <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-1">
                    Definir nova senha
                </h2>
                <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
                    Escolha uma senha com pelo menos {MIN_PASSWORD_LENGTH} caracteres.
                </p>

                {error && (
                    <div className="mb-4 p-3 rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 text-sm flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 shrink-0" />
                        {error}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                            Nova senha
                        </label>
                        <div className="relative">
                            <input
                                type={showPassword ? 'text' : 'password'}
                                autoFocus
                                autoComplete="new-password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className={inputClass}
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
                    <div>
                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                            Confirmar nova senha
                        </label>
                        <input
                            type={showPassword ? 'text' : 'password'}
                            autoComplete="new-password"
                            value={confirmation}
                            onChange={(e) => setConfirmation(e.target.value)}
                            className={inputClass}
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={submitting || !password || !confirmation}
                        className="w-full bg-violet-600 text-white px-4 py-2 rounded-md hover:bg-violet-700 disabled:opacity-50 flex items-center justify-center gap-2 transition-colors"
                    >
                        {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />}
                        Salvar nova senha
                    </button>
                </form>

                <div className="mt-6 text-center">
                    <Link
                        to={expired ? '/forgot-password' : '/login'}
                        className="text-sm text-violet-600 dark:text-violet-400 hover:underline"
                    >
                        {expired ? 'Solicitar um novo link' : 'Voltar ao login'}
                    </Link>
                </div>
            </div>
        </div>
    );
};

export default ResetPassword;
