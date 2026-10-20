import React, { useCallback, useEffect, useState } from 'react';
import { Users, Plus, Pencil, Trash2, X, Loader2, AlertCircle, Eye, EyeOff, KeyRound, ShieldCheck } from 'lucide-react';
import api from '../api/client';
import { useAuth } from '../context/AuthContext';

const PERMISSION_FIELDS = [
    { key: 'can_query', label: 'Consultar (SQL/Visual)' },
    { key: 'can_upload', label: 'Upload de dados' },
    { key: 'can_manage_views', label: 'Gerenciar views/tabelas' },
    { key: 'can_manage_functions', label: 'Gerenciar funções' },
    { key: 'can_manage_users', label: 'Gerenciar usuários' },
    { key: 'can_view_audit', label: 'Ver Audit Log' },
    { key: 'can_manage_connections', label: 'Gerenciar conexões externas' },
];

const emptyForm = () => ({
    username: '',
    password: '',
    can_query: false,
    can_upload: false,
    can_manage_views: false,
    can_manage_functions: false,
    can_manage_users: false,
    can_view_audit: false,
    can_manage_connections: false,
});

const UsersPage = () => {
    const { user: currentUser } = useAuth();
    const [users, setUsers] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [showModal, setShowModal] = useState(false);
    const [editingId, setEditingId] = useState(null);
    const [form, setForm] = useState(emptyForm());
    const [saving, setSaving] = useState(false);
    const [formError, setFormError] = useState(null);
    const [showPassword, setShowPassword] = useState(false);

    const fetchUsers = useCallback(async (signal) => {
        setLoading(true);
        setError(null);
        try {
            const res = await api.get('/users', { signal });
            setUsers(res.data.users || []);
        } catch (err) {
            if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED') return;
            setError(err.response?.data?.error || 'Falha ao carregar usuários');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        fetchUsers(controller.signal);
        return () => controller.abort();
    }, [fetchUsers]);

    const openCreate = () => {
        setEditingId(null);
        setForm(emptyForm());
        setFormError(null);
        setShowPassword(false);
        setShowModal(true);
    };

    const openEdit = (u) => {
        setEditingId(u.id);
        setForm({
            username: u.username,
            password: '',
            can_query: u.perms.can_query,
            can_upload: u.perms.can_upload,
            can_manage_views: u.perms.can_manage_views,
            can_manage_functions: u.perms.can_manage_functions || false,
            can_manage_users: u.perms.can_manage_users,
            can_view_audit: u.perms.can_view_audit || false,
            can_manage_connections: u.perms.can_manage_connections || false,
        });
        setFormError(null);
        setShowPassword(false);
        setShowModal(true);
    };

    const handleSave = async () => {
        if (!form.username) return;
        if (!editingId && !form.password) {
            setFormError('Senha obrigatória ao criar usuário');
            return;
        }
        setSaving(true);
        setFormError(null);
        try {
            const payload = {
                username: form.username,
                can_query: form.can_query,
                can_upload: form.can_upload,
                can_manage_views: form.can_manage_views,
                can_manage_functions: form.can_manage_functions,
                can_manage_users: form.can_manage_users,
                can_view_audit: form.can_view_audit,
                can_manage_connections: form.can_manage_connections,
            };
            if (form.password) payload.password = form.password;

            if (editingId) {
                await api.put(`/users/${editingId}`, payload);
            } else {
                await api.post('/users', payload);
            }
            setShowModal(false);
            fetchUsers();
        } catch (err) {
            setFormError(err.response?.data?.error || 'Falha ao salvar usuário');
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (u) => {
        if (!window.confirm(`Excluir o usuário "${u.username}"?`)) return;
        try {
            await api.delete(`/users/${u.id}`);
            fetchUsers();
        } catch (err) {
            setError(err.response?.data?.error || 'Falha ao excluir');
        }
    };

    return (
        <div className="flex flex-col gap-6">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Users className="w-6 h-6 text-violet-600 dark:text-violet-400" />
                    <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Usuários</h2>
                </div>
                <button
                    onClick={openCreate}
                    className="bg-violet-600 text-white px-4 py-2 rounded-md hover:bg-violet-700 flex items-center gap-2"
                >
                    <Plus className="w-4 h-4" /> Criar Usuário
                </button>
            </div>

            <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md overflow-hidden border border-slate-200 dark:border-slate-700">
                {loading ? (
                    <div className="p-8 text-center text-slate-500">Carregando...</div>
                ) : error ? (
                    <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 flex items-center gap-2">
                        <AlertCircle className="w-4 h-4" /> {error}
                    </div>
                ) : users.length === 0 ? (
                    <div className="p-8 text-center text-slate-400 italic">Nenhum usuário cadastrado.</div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full min-w-[1180px] text-sm">
                            <thead className="bg-slate-50 dark:bg-slate-700/50 text-slate-600 dark:text-slate-300">
                                <tr>
                                    <th className="text-left p-3 w-14">#</th>
                                    <th className="text-left p-3 min-w-56">Usuário</th>
                                    {PERMISSION_FIELDS.map(f => (
                                        <th key={f.key} className="text-center p-3 whitespace-nowrap">{f.label}</th>
                                    ))}
                                    <th className="p-3 text-right w-24">Ações</th>
                                </tr>
                            </thead>
                            <tbody>
                                {users.map(u => (
                                    <tr key={u.id} className="border-t border-slate-200 dark:border-slate-700">
                                        <td className="p-3 font-mono text-violet-600 dark:text-violet-400">{u.id}</td>
                                        <td className="p-3 font-medium text-slate-800 dark:text-slate-200 whitespace-nowrap">
                                            {u.username}
                                            {u.id === currentUser?.id && (
                                                <span className="ml-2 text-[10px] uppercase bg-violet-100 text-violet-700 px-1.5 py-0.5 rounded-sm">você</span>
                                            )}
                                        </td>
                                        {PERMISSION_FIELDS.map(f => (
                                            <td key={f.key} className="p-3 text-center">
                                                {u.perms[f.key] ? (
                                                    <span className="inline-block w-2.5 h-2.5 rounded-full bg-green-500" />
                                                ) : (
                                                    <span className="inline-block w-2.5 h-2.5 rounded-full bg-slate-300 dark:bg-slate-600" />
                                                )}
                                            </td>
                                        ))}
                                        <td className="p-3 text-right whitespace-nowrap">
                                            <button
                                                onClick={() => openEdit(u)}
                                                className="text-slate-400 hover:text-blue-500 p-1"
                                                title="Editar"
                                            >
                                                <Pencil className="w-4 h-4" />
                                            </button>
                                            <button
                                                onClick={() => handleDelete(u)}
                                                className="text-slate-400 hover:text-red-500 p-1 ml-1 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:text-slate-400"
                                                title="Excluir"
                                                disabled={u.id === currentUser?.id}
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {showModal && (
                <div
                    className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
                    onClick={(e) => e.target === e.currentTarget && setShowModal(false)}
                >
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="user-modal-title"
                        onKeyDown={(e) => e.key === 'Escape' && setShowModal(false)}
                        className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-lg p-6 border dark:border-slate-700"
                    >
                        <div className="flex justify-between items-center mb-6">
                            <h3 id="user-modal-title" className="text-xl font-bold text-slate-800 dark:text-slate-100">
                                {editingId ? 'Editar Usuário' : 'Criar Usuário'}
                            </h3>
                            <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        {formError && (
                            <div className="mb-4 p-3 rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 text-sm flex items-center gap-2">
                                <AlertCircle className="w-4 h-4 shrink-0" /> {formError}
                            </div>
                        )}

                        <div className="space-y-5">
                            {/* Credentials section */}
                            <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-4 space-y-4">
                                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
                                    <KeyRound className="w-3.5 h-3.5" /> Credenciais
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Usuário</label>
                                    <input
                                        type="text"
                                        value={form.username}
                                        onChange={e => setForm({ ...form, username: e.target.value })}
                                        className="w-full px-3 py-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-violet-500 focus:border-transparent"
                                        autoFocus
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                                        Senha{editingId && <span className="ml-1.5 text-xs font-normal text-slate-400">(deixe em branco para manter)</span>}
                                    </label>
                                    <div className="relative">
                                        <input
                                            type={showPassword ? 'text' : 'password'}
                                            value={form.password}
                                            onChange={e => setForm({ ...form, password: e.target.value })}
                                            className="w-full px-3 py-2 pr-10 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-violet-500 focus:border-transparent"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setShowPassword(v => !v)}
                                            className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                                            tabIndex={-1}
                                            aria-label={showPassword ? 'Ocultar senha' : 'Mostrar senha'}
                                        >
                                            {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                        </button>
                                    </div>
                                </div>
                            </div>

                            {/* Permissions section */}
                            <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-4">
                                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500 mb-3">
                                    <ShieldCheck className="w-3.5 h-3.5" /> Permissões
                                </div>
                                <div className="grid grid-cols-1 gap-1">
                                    {PERMISSION_FIELDS.map(f => (
                                        <label key={f.key} className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-slate-50 dark:hover:bg-slate-700/50 cursor-pointer transition-colors">
                                            <input
                                                type="checkbox"
                                                checked={form[f.key]}
                                                onChange={e => setForm({ ...form, [f.key]: e.target.checked })}
                                                className="w-4 h-4 rounded-sm border-slate-300 text-violet-600 focus:ring-violet-500 dark:border-slate-600 dark:bg-slate-800"
                                            />
                                            <span className="text-sm text-slate-700 dark:text-slate-300">{f.label}</span>
                                        </label>
                                    ))}
                                </div>
                            </div>

                            <div className="flex justify-end gap-3 pt-2">
                                <button
                                    onClick={() => setShowModal(false)}
                                    className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700 rounded-md transition-colors"
                                >
                                    Cancelar
                                </button>
                                <button
                                    onClick={handleSave}
                                    disabled={saving || !form.username}
                                    className="bg-violet-600 text-white px-6 py-2 text-sm rounded-md hover:bg-violet-700 disabled:opacity-50 flex items-center gap-2 transition-colors"
                                >
                                    {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                                    {editingId ? 'Atualizar' : 'Criar'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default UsersPage;
