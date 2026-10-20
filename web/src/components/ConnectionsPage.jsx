import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle, Database, KeyRound, Loader2, Network, Pencil, Plus, RefreshCw, Server, Trash2, X } from 'lucide-react';
import {
    createConnection,
    deleteConnection,
    getConnections,
    syncConnection,
    testConnection,
    updateConnection,
} from '../api/client';

const TYPE_OPTIONS = [
    { value: 'sqlserver', label: 'SQL Server', defaultPort: 1433, defaultSchema: 'dbo' },
    { value: 'postgres', label: 'PostgreSQL', defaultPort: 5432, defaultSchema: 'public' },
];

const emptyForm = () => ({
    name: '',
    display_name: '',
    db_type: 'sqlserver',
    host: '',
    port: 1433,
    database: '',
    remote_schema: 'dbo',
    username: '',
    password: '',
});

const formatTimestamp = (value) => {
    if (!value) return '—';
    try {
        return new Date(value).toLocaleString();
    } catch {
        return value;
    }
};

const ConnectionsPage = () => {
    const [connections, setConnections] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [showModal, setShowModal] = useState(false);
    const [editingId, setEditingId] = useState(null);
    const [form, setForm] = useState(emptyForm());
    const [saving, setSaving] = useState(false);
    const [testing, setTesting] = useState(false);
    const [testResult, setTestResult] = useState(null);
    const [formError, setFormError] = useState(null);
    const [syncingId, setSyncingId] = useState(null);

    const fetchConnections = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await getConnections();
            setConnections(res.data.connections || []);
        } catch (err) {
            setError(err.response?.data?.error || 'Falha ao carregar conexões');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchConnections();
    }, [fetchConnections]);

    const payload = useMemo(() => ({
        name: form.name.trim(),
        display_name: form.display_name.trim() || form.name.trim(),
        db_type: form.db_type,
        host: form.host.trim(),
        port: Number(form.port),
        database: form.database.trim(),
        remote_schema: form.remote_schema.trim(),
        username: form.username.trim(),
        ...(form.password ? { password: form.password } : {}),
    }), [form]);

    const openCreate = () => {
        setEditingId(null);
        setForm(emptyForm());
        setTestResult(null);
        setFormError(null);
        setShowModal(true);
    };

    const openEdit = (conn) => {
        setEditingId(conn.id);
        setForm({
            name: conn.name,
            display_name: conn.display_name || '',
            db_type: conn.db_type,
            host: conn.host,
            port: conn.port,
            database: conn.database,
            remote_schema: conn.remote_schema || '',
            username: conn.username,
            password: '',
        });
        setTestResult(null);
        setFormError(null);
        setShowModal(true);
    };

    const closeModal = () => {
        if (saving) return;
        setShowModal(false);
        setEditingId(null);
        setTestResult(null);
        setFormError(null);
    };

    const handleTypeChange = (value) => {
        const type = TYPE_OPTIONS.find(t => t.value === value);
        setForm(prev => ({
            ...prev,
            db_type: value,
            port: type?.defaultPort || prev.port,
            remote_schema: type?.defaultSchema || prev.remote_schema,
        }));
        setTestResult(null);
    };

    const handleTest = async () => {
        if (editingId && !form.password) {
            setTestResult({ ok: false, error: 'Informe a senha para testar (a senha salva não é reaproveitada no teste).' });
            return;
        }
        setTesting(true);
        setTestResult(null);
        try {
            const res = await testConnection(payload);
            setTestResult({ ok: true, ...res.data });
        } catch (err) {
            setTestResult({ ok: false, error: err.response?.data?.error || 'Falha no teste de conexão' });
        } finally {
            setTesting(false);
        }
    };

    const handleSave = async () => {
        setSaving(true);
        setFormError(null);
        try {
            if (editingId) {
                await updateConnection(editingId, payload);
            } else {
                await createConnection(payload);
            }
            closeModal();
            fetchConnections();
        } catch (err) {
            setFormError(err.response?.data?.error || 'Falha ao salvar conexão');
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (conn) => {
        if (!window.confirm(`Excluir a conexão "${conn.display_name || conn.name}"? O schema ${conn.schema_name} e suas foreign tables serão removidos.`)) return;
        try {
            await deleteConnection(conn.id);
            fetchConnections();
        } catch (err) {
            setError(err.response?.data?.error || 'Falha ao excluir conexão');
        }
    };

    const handleSync = async (conn) => {
        setSyncingId(conn.id);
        try {
            await syncConnection(conn.id);
            fetchConnections();
        } catch (err) {
            setError(err.response?.data?.error || 'Falha ao sincronizar conexão');
        } finally {
            setSyncingId(null);
        }
    };

    return (
        <div className="flex flex-col gap-6">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Network className="w-6 h-6 text-violet-600 dark:text-violet-400" />
                    <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Conexões Externas</h2>
                </div>
                <button
                    onClick={openCreate}
                    className="bg-violet-600 text-white px-4 py-2 rounded-md hover:bg-violet-700 flex items-center gap-2"
                >
                    <Plus className="w-4 h-4" /> Nova Conexão
                </button>
            </div>

            <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md overflow-hidden border border-slate-200 dark:border-slate-700">
                {loading ? (
                    <div className="p-8 text-center text-slate-500">Carregando...</div>
                ) : error ? (
                    <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 flex items-center gap-2">
                        <AlertCircle className="w-4 h-4" /> {error}
                    </div>
                ) : connections.length === 0 ? (
                    <div className="p-8 text-center text-slate-400 italic">
                        Nenhuma conexão cadastrada. Clique em "Nova Conexão" para registrar um SQL Server ou Postgres externo.
                    </div>
                ) : (
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 dark:bg-slate-700/50 text-slate-600 dark:text-slate-300">
                            <tr>
                                <th className="text-left p-3">Nome</th>
                                <th className="text-left p-3">Tipo</th>
                                <th className="text-left p-3">Endpoint</th>
                                <th className="text-left p-3">Schema local</th>
                                <th className="text-left p-3">Último sync</th>
                                <th className="p-3"></th>
                            </tr>
                        </thead>
                        <tbody>
                            {connections.map(conn => (
                                <tr key={conn.id} className="border-t border-slate-200 dark:border-slate-700">
                                    <td className="p-3">
                                        <div className="font-medium text-slate-800 dark:text-slate-200">
                                            {conn.display_name || conn.name}
                                        </div>
                                        <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 font-mono">
                                            {conn.name}
                                        </div>
                                    </td>
                                    <td className="p-3 text-slate-600 dark:text-slate-300">
                                        {conn.db_type === 'sqlserver' ? 'SQL Server' : 'PostgreSQL'}
                                    </td>
                                    <td className="p-3 text-slate-600 dark:text-slate-300 font-mono text-xs">
                                        {conn.host}:{conn.port}/{conn.database}
                                        <div className="text-[11px] text-slate-400">remoto: {conn.remote_schema}</div>
                                    </td>
                                    <td className="p-3 font-mono text-xs text-slate-600 dark:text-slate-300">
                                        {conn.schema_name}
                                    </td>
                                    <td className="p-3 text-xs text-slate-500 dark:text-slate-400">
                                        {formatTimestamp(conn.last_synced_at)}
                                    </td>
                                    <td className="p-3 text-right whitespace-nowrap">
                                        <button
                                            onClick={() => handleSync(conn)}
                                            disabled={syncingId === conn.id}
                                            className="text-slate-400 hover:text-violet-500 p-1 disabled:opacity-50"
                                            title="Sincronizar schema (re-importar foreign tables)"
                                        >
                                            {syncingId === conn.id
                                                ? <Loader2 className="w-4 h-4 animate-spin" />
                                                : <RefreshCw className="w-4 h-4" />}
                                        </button>
                                        <button
                                            onClick={() => openEdit(conn)}
                                            className="text-slate-400 hover:text-blue-500 p-1 ml-1"
                                            title="Editar"
                                        >
                                            <Pencil className="w-4 h-4" />
                                        </button>
                                        <button
                                            onClick={() => handleDelete(conn)}
                                            className="text-slate-400 hover:text-red-500 p-1 ml-1"
                                            title="Excluir"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {showModal && (
                <div
                    className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
                    onClick={(e) => e.target === e.currentTarget && closeModal()}
                >
                    <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-3xl border border-slate-200 dark:border-slate-700 max-h-[90vh] overflow-y-auto">
                        <div className="flex justify-between items-start gap-4 p-5 border-b border-slate-200 dark:border-slate-700">
                            <div>
                                <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100">
                                    {editingId ? 'Editar Conexão' : 'Nova Conexão'}
                                </h3>
                                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                                    Informe os mesmos dados que você usaria em um cliente de banco, como DBeaver: tipo, servidor, banco, usuário e senha.
                                </p>
                            </div>
                            <button onClick={closeModal} disabled={saving} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 disabled:opacity-50">
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        <div className="p-5 space-y-5">
                            <div className="rounded-md border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900 dark:border-blue-800/60 dark:bg-blue-950/40 dark:text-blue-100">
                                <div className="font-semibold">O que esta conexão faz?</div>
                                <p className="mt-1">
                                    Ela cria um atalho seguro para consultar tabelas de outro banco dentro deste sistema.
                                    Os dados continuam no banco de origem.
                                </p>
                            </div>

                            <FormSection
                                icon={<Database className="w-4 h-4" />}
                                title="Banco de dados"
                                description="Primeiro escolha o tipo de banco e dê um nome fácil para reconhecer depois."
                            >
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <Field label="Tipo de banco" hint="Equivale ao driver escolhido no DBeaver.">
                                        <select
                                            value={form.db_type}
                                            onChange={(e) => handleTypeChange(e.target.value)}
                                            className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-violet-500"
                                        >
                                            {TYPE_OPTIONS.map(opt => (
                                                <option key={opt.value} value={opt.value}>{opt.label}</option>
                                            ))}
                                        </select>
                                    </Field>
                                    <Field label="Nome para aparecer na tela" hint="Exemplo: Vendas Produção, ERP Financeiro, CRM.">
                                        <input
                                            type="text"
                                            value={form.display_name}
                                            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                                            className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-violet-500"
                                            placeholder="Vendas (Produção)"
                                        />
                                    </Field>
                                    <Field label="Nome interno" hint="Identificador técnico. Use letras, números e underline, como vendas_prod.">
                                        <input
                                            type="text"
                                            value={form.name}
                                            onChange={(e) => setForm({ ...form, name: e.target.value })}
                                            disabled={!!editingId}
                                            className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-violet-500 disabled:opacity-60"
                                            placeholder="vendas_prod"
                                        />
                                    </Field>
                                    <Field label="Pasta/schema das tabelas" hint="Normalmente dbo no SQL Server ou public no PostgreSQL.">
                                        <input
                                            type="text"
                                            value={form.remote_schema}
                                            onChange={(e) => setForm({ ...form, remote_schema: e.target.value })}
                                            className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-violet-500"
                                            placeholder={form.db_type === 'sqlserver' ? 'dbo' : 'public'}
                                        />
                                    </Field>
                                </div>
                            </FormSection>

                            <FormSection
                                icon={<Server className="w-4 h-4" />}
                                title="Servidor"
                                description="Esta parte corresponde à aba de conexão principal: endereço, porta e nome do banco."
                            >
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <Field label="Host / servidor" hint="Pode ser um IP ou um nome de servidor informado pela TI.">
                                        <input
                                            type="text"
                                            value={form.host}
                                            onChange={(e) => setForm({ ...form, host: e.target.value })}
                                            className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-violet-500"
                                            placeholder="10.0.0.5 ou srv-bd.empresa.local"
                                        />
                                    </Field>
                                    <Field label="Porta" hint="Se ninguém informou uma porta, mantenha a sugerida.">
                                        <input
                                            type="number"
                                            value={form.port}
                                            onChange={(e) => setForm({ ...form, port: e.target.value })}
                                            className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-violet-500"
                                        />
                                    </Field>
                                    <Field label="Database / banco" hint="Nome do banco que contém as tabelas que serão consultadas.">
                                        <input
                                            type="text"
                                            value={form.database}
                                            onChange={(e) => setForm({ ...form, database: e.target.value })}
                                            className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-violet-500"
                                            placeholder="VendasDB"
                                        />
                                    </Field>
                                </div>
                            </FormSection>

                            <FormSection
                                icon={<KeyRound className="w-4 h-4" />}
                                title="Autenticação"
                                description="Use um usuário de leitura sempre que possível. Assim o sistema consulta as tabelas sem alterar dados na origem."
                            >
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <Field label="Usuário" hint="O mesmo usuário usado para entrar nesse banco no DBeaver.">
                                        <input
                                            type="text"
                                            value={form.username}
                                            onChange={(e) => setForm({ ...form, username: e.target.value })}
                                            className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-violet-500"
                                            placeholder="leitor_bi"
                                        />
                                    </Field>
                                    <Field
                                        label="Senha"
                                        hint={editingId ? 'Deixe em branco para manter a senha salva. Informe a senha se quiser testar ou trocar o acesso.' : 'A senha fica protegida antes de ser gravada.'}
                                    >
                                        <input
                                            type="password"
                                            value={form.password}
                                            onChange={(e) => setForm({ ...form, password: e.target.value })}
                                            autoComplete="new-password"
                                            className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-violet-500"
                                            placeholder={editingId ? 'Senha atual preservada' : ''}
                                        />
                                    </Field>
                                </div>
                            </FormSection>

                            {testResult && (
                                <div className={`p-3 rounded-md text-sm flex items-start gap-2 ${
                                    testResult.ok
                                        ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300'
                                        : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'
                                }`}>
                                    {testResult.ok
                                        ? <CheckCircle className="w-4 h-4 mt-0.5 shrink-0" />
                                        : <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />}
                                    <pre className="whitespace-pre-wrap font-sans flex-1">
                                        {testResult.ok
                                            ? `Conexão funcionando. Encontramos ${testResult.foreign_table_count ?? 0} tabela(s) disponíveis nessa pasta/schema do banco.`
                                            : testResult.error}
                                    </pre>
                                </div>
                            )}

                            {formError && (
                                <div className="p-3 rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm flex items-start gap-2">
                                    <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                                    <pre className="whitespace-pre-wrap font-sans flex-1">{formError}</pre>
                                </div>
                            )}
                        </div>

                        <div className="flex flex-col gap-3 p-5 border-t border-slate-200 dark:border-slate-700 sm:flex-row sm:items-center sm:justify-between">
                            <button
                                type="button"
                                onClick={handleTest}
                                disabled={testing || saving}
                                className="px-4 py-2 text-violet-600 bg-violet-50 dark:bg-violet-900/20 dark:text-violet-300 rounded-md hover:bg-violet-100 disabled:opacity-50 flex items-center justify-center gap-2"
                            >
                                {testing && <Loader2 className="w-4 h-4 animate-spin" />}
                                Testar conexão
                            </button>
                            <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                                <button
                                    type="button"
                                    onClick={closeModal}
                                    disabled={saving}
                                    className="px-4 py-2 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700 rounded-md disabled:opacity-50"
                                >
                                    Cancelar
                                </button>
                                <button
                                    type="button"
                                    onClick={handleSave}
                                    disabled={saving}
                                    className="bg-violet-600 text-white px-4 py-2 rounded-md hover:bg-violet-700 disabled:opacity-50 flex items-center justify-center gap-2"
                                >
                                    {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                                    {editingId ? 'Salvar alterações' : 'Salvar conexão'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

const FormSection = ({ icon, title, description, children }) => (
    <section className="space-y-3">
        <div className="flex items-start gap-2">
            <div className="mt-0.5 text-violet-600 dark:text-violet-300">{icon}</div>
            <div>
                <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{description}</p>
            </div>
        </div>
        {children}
    </section>
);

const Field = ({ label, hint, children }) => (
    <div>
        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">{label}</label>
        {children}
        {hint && <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{hint}</p>}
    </div>
);

export default ConnectionsPage;
