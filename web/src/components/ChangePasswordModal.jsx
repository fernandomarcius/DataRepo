import React, { useState } from 'react';
import { AlertCircle, CheckCircle, Eye, EyeOff, KeyRound, Loader2, X } from 'lucide-react';
import { changePassword } from '../api/client';

const MIN_PASSWORD_LENGTH = 8;

const ERROR_MESSAGES = {
    'Current password is incorrect': 'Senha atual incorreta.',
    'Password must be at least 8 characters': `A nova senha deve ter pelo menos ${MIN_PASSWORD_LENGTH} caracteres.`,
    'Current and new password are required': 'Preencha a senha atual e a nova senha.',
};

const ChangePasswordModal = ({ username, onClose }) => {
    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmation, setConfirmation] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (newPassword.length < MIN_PASSWORD_LENGTH) {
            setError(`A nova senha deve ter pelo menos ${MIN_PASSWORD_LENGTH} caracteres.`);
            return;
        }
        if (newPassword !== confirmation) {
            setError('As senhas não conferem.');
            return;
        }
        if (newPassword === currentPassword) {
            setError('A nova senha deve ser diferente da atual.');
            return;
        }
        setSaving(true);
        setError(null);
        try {
            await changePassword(currentPassword, newPassword);
            setSuccess(true);
        } catch (err) {
            const apiError = err.response?.data?.error;
            setError(ERROR_MESSAGES[apiError] || 'Falha ao alterar senha.');
        } finally {
            setSaving(false);
        }
    };

    const inputClass = 'w-full px-3 py-2 pr-10 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-violet-500 focus:border-transparent';

    return (
        <div
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
            onClick={(e) => e.target === e.currentTarget && onClose()}
        >
            <div
                role="dialog"
                aria-modal="true"
                aria-labelledby="change-password-title"
                onKeyDown={(e) => e.key === 'Escape' && onClose()}
                className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-md p-6 border dark:border-slate-700"
            >
                <div className="flex justify-between items-center mb-6">
                    <h3 id="change-password-title" className="text-xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
                        <KeyRound className="w-5 h-5 text-violet-500" /> Alterar senha
                    </h3>
                    <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
                    Usuário <span className="font-medium text-slate-700 dark:text-slate-300">{username}</span>.
                    O login não pode ser alterado aqui.
                </p>

                {error && (
                    <div className="mb-4 p-3 rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 text-sm flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 shrink-0" /> {error}
                    </div>
                )}

                {success ? (
                    <>
                        <div className="mb-6 p-3 rounded-md bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 text-sm flex items-center gap-2">
                            <CheckCircle className="w-4 h-4 shrink-0" /> Senha alterada com sucesso.
                        </div>
                        <button
                            onClick={onClose}
                            className="w-full bg-violet-600 text-white px-4 py-2 rounded-md hover:bg-violet-700 transition-colors"
                        >
                            Fechar
                        </button>
                    </>
                ) : (
                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                                Senha atual
                            </label>
                            <div className="relative">
                                <input
                                    type={showPassword ? 'text' : 'password'}
                                    autoFocus
                                    autoComplete="current-password"
                                    value={currentPassword}
                                    onChange={(e) => setCurrentPassword(e.target.value)}
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
                                Nova senha
                            </label>
                            <input
                                type={showPassword ? 'text' : 'password'}
                                autoComplete="new-password"
                                value={newPassword}
                                onChange={(e) => setNewPassword(e.target.value)}
                                className={inputClass}
                            />
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
                        <div className="flex gap-3 pt-2">
                            <button
                                type="button"
                                onClick={onClose}
                                className="flex-1 px-4 py-2 rounded-md border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors"
                            >
                                Cancelar
                            </button>
                            <button
                                type="submit"
                                disabled={saving || !currentPassword || !newPassword || !confirmation}
                                className="flex-1 bg-violet-600 text-white px-4 py-2 rounded-md hover:bg-violet-700 disabled:opacity-50 flex items-center justify-center gap-2 transition-colors"
                            >
                                {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                                Salvar
                            </button>
                        </div>
                    </form>
                )}
            </div>
        </div>
    );
};

export default ChangePasswordModal;
