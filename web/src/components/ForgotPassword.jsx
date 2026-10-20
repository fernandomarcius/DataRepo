import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, CheckCircle, Loader2, Send } from 'lucide-react';
import { forgotPassword } from '../api/client';
import { rota } from '../prefixo';

const ForgotPassword = () => {
    const [username, setUsername] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [sent, setSent] = useState(false);
    const [error, setError] = useState(null);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!username) return;
        setSubmitting(true);
        setError(null);
        try {
            await forgotPassword(username);
            setSent(true);
        } catch (err) {
            if (err.response?.status === 429) {
                setError('Muitas tentativas. Aguarde um minuto e tente de novo.');
            } else {
                setError(err.response?.data?.error || 'Falha ao enviar o link');
            }
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
                <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-1">
                    Esqueci minha senha
                </h2>
                <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">
                    Informe seu usuário. Enviaremos um link de redefinição para o e-mail cadastrado como usuário.
                </p>

                {error && (
                    <div className="mb-4 p-3 rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 text-sm flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 shrink-0" />
                        {error}
                    </div>
                )}

                {sent ? (
                    <div className="mb-6 p-3 rounded-md bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 text-sm flex items-start gap-2">
                        <CheckCircle className="w-4 h-4 shrink-0 mt-0.5" />
                        <span>
                            Se a conta existir, você receberá um e-mail com o link para redefinir a senha.
                            O link vale por 30 minutos.
                        </span>
                    </div>
                ) : (
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
                        <button
                            type="submit"
                            disabled={submitting || !username}
                            className="w-full bg-violet-600 text-white px-4 py-2 rounded-md hover:bg-violet-700 disabled:opacity-50 flex items-center justify-center gap-2 transition-colors"
                        >
                            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                            Enviar link
                        </button>
                    </form>
                )}

                <div className="mt-6 text-center">
                    <Link to="/login" className="text-sm text-violet-600 dark:text-violet-400 hover:underline">
                        Voltar ao login
                    </Link>
                </div>
            </div>
        </div>
    );
};

export default ForgotPassword;
