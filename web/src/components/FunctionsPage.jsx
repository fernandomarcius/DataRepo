import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle, Code, Copy, Loader2, Pencil, Plus, Trash2, X } from 'lucide-react';
import api from '../api/client';

const TYPE_OPTIONS = [
    'text',
    'integer',
    'bigint',
    'numeric',
    'double precision',
    'boolean',
    'date',
    'timestamp',
    'timestamptz',
    'jsonb',
    'uuid',
];

const FUNCTION_KIND_HELP = {
    scalar: {
        title: 'Escalar',
        description: 'Retorna um único valor por chamada. Use para cálculos, formatações e regras que entram em colunas de SELECT.',
        example: 'SELECT fn_calcular_total(valor) AS total',
    },
    table: {
        title: 'Tabela',
        description: 'Retorna várias linhas e colunas. Use quando a função precisa montar um conjunto de dados para consultas e views.',
        example: 'SELECT * FROM fn_clientes_ativos()',
    },
};

const emptyForm = () => ({
    name: '',
    function_name: '',
    description: '',
    kind: 'scalar',
    parameters: [],
    return_type: 'text',
    return_columns: [{ name: 'resultado', type: 'text' }],
    sql_body: 'SELECT 1',
});

const emptyParam = () => ({ name: '', type: 'text' });
const emptyColumn = () => ({ name: '', type: 'text' });

const FunctionsPage = () => {
    const [functions, setFunctions] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [showModal, setShowModal] = useState(false);
    const [editingId, setEditingId] = useState(null);
    const [form, setForm] = useState(emptyForm());
    const [saving, setSaving] = useState(false);
    const [validating, setValidating] = useState(false);
    const [validation, setValidation] = useState(null);
    const [formError, setFormError] = useState(null);
    const [copiedId, setCopiedId] = useState(null);

    const fetchFunctions = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await api.get('/functions');
            setFunctions(res.data.functions || []);
        } catch (err) {
            setError(err.response?.data?.error || 'Falha ao carregar funções');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchFunctions();
    }, [fetchFunctions]);

    const resetValidation = () => {
        setValidation(null);
        setFormError(null);
    };

    const updateForm = (patch) => {
        setForm(prev => ({ ...prev, ...patch }));
        resetValidation();
    };

    const payload = useMemo(() => ({
        name: form.name,
        function_name: form.function_name || undefined,
        description: form.description,
        kind: form.kind,
        parameters: form.parameters.filter(p => p.name || p.type),
        return_type: form.kind === 'scalar' ? form.return_type : undefined,
        return_columns: form.kind === 'table' ? form.return_columns.filter(c => c.name || c.type) : [],
        sql_body: form.sql_body,
    }), [form]);

    const openCreate = () => {
        setEditingId(null);
        setForm(emptyForm());
        setValidation(null);
        setFormError(null);
        setShowModal(true);
    };

    const openEdit = async (fn) => {
        setEditingId(fn.id);
        setValidation({ type: 'success', message: 'Função existente validada.', signature: fn.signature });
        setFormError(null);
        setShowModal(true);
        try {
            const res = await api.get(`/functions/${fn.id}`);
            const full = res.data;
            setForm({
                name: full.name || '',
                function_name: full.function_name || '',
                description: full.description || '',
                kind: full.kind || 'scalar',
                parameters: full.parameters || [],
                return_type: full.return_type || 'text',
                return_columns: full.return_columns?.length ? full.return_columns : [{ name: 'resultado', type: 'text' }],
                sql_body: full.sql_body || '',
            });
        } catch (err) {
            setFormError(err.response?.data?.error || 'Falha ao carregar função');
        }
    };

    const handleValidate = async () => {
        setValidating(true);
        setFormError(null);
        setValidation(null);
        try {
            const res = await api.post('/functions/validate', payload);
            setValidation({
                type: 'success',
                message: 'Função validada com sucesso.',
                signature: res.data.signature,
                callExample: res.data.call_example,
            });
        } catch (err) {
            setValidation({
                type: 'error',
                message: err.response?.data?.error || 'Falha ao validar função',
            });
        } finally {
            setValidating(false);
        }
    };

    const handleSave = async () => {
        if (validation?.type !== 'success') return;
        setSaving(true);
        setFormError(null);
        try {
            if (editingId) {
                await api.put(`/functions/${editingId}`, payload);
            } else {
                await api.post('/functions', payload);
            }
            setShowModal(false);
            setEditingId(null);
            setForm(emptyForm());
            setValidation(null);
            fetchFunctions();
        } catch (err) {
            setFormError(err.response?.data?.error || 'Falha ao salvar função');
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (fn) => {
        if (!window.confirm(`Excluir a função "${fn.name}"?`)) return;
        try {
            await api.delete(`/functions/${fn.id}`);
            fetchFunctions();
        } catch (err) {
            setError(err.response?.data?.error || 'Falha ao excluir função');
        }
    };

    const copyText = async (fn) => {
        const text = fn.call_example || fn.function_name;
        try {
            await navigator.clipboard.writeText(text);
            setCopiedId(fn.id);
            setTimeout(() => setCopiedId(null), 1400);
        } catch {
            setCopiedId(null);
        }
    };

    const updateParameter = (idx, patch) => {
        const next = [...form.parameters];
        next[idx] = { ...next[idx], ...patch };
        updateForm({ parameters: next });
    };

    const updateReturnColumn = (idx, patch) => {
        const next = [...form.return_columns];
        next[idx] = { ...next[idx], ...patch };
        updateForm({ return_columns: next });
    };

    return (
        <div className="flex flex-col gap-6">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Code className="w-6 h-6 text-violet-600 dark:text-violet-400" />
                    <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Funções</h2>
                </div>
                <button
                    onClick={openCreate}
                    className="bg-violet-600 text-white px-4 py-2 rounded-md hover:bg-violet-700 flex items-center gap-2"
                >
                    <Plus className="w-4 h-4" /> Criar Função
                </button>
            </div>

            <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md overflow-hidden border border-slate-200 dark:border-slate-700">
                {loading ? (
                    <div className="p-8 text-center text-slate-500">Carregando...</div>
                ) : error ? (
                    <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 flex items-center gap-2">
                        <AlertCircle className="w-4 h-4" /> {error}
                    </div>
                ) : functions.length === 0 ? (
                    <div className="p-8 text-center text-slate-400 italic">Nenhuma função cadastrada.</div>
                ) : (
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 dark:bg-slate-700/50 text-slate-600 dark:text-slate-300">
                            <tr>
                                <th className="text-left p-3">Nome</th>
                                <th className="text-left p-3">Assinatura</th>
                                <th className="text-left p-3">Tipo</th>
                                <th className="p-3"></th>
                            </tr>
                        </thead>
                        <tbody>
                            {functions.map(fn => (
                                <tr key={fn.id} className="border-t border-slate-200 dark:border-slate-700">
                                    <td className="p-3">
                                        <div className="font-medium text-slate-800 dark:text-slate-200">{fn.name}</div>
                                        {fn.description && (
                                            <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">{fn.description}</div>
                                        )}
                                    </td>
                                    <td className="p-3">
                                        <code className="text-xs bg-slate-100 dark:bg-slate-900 text-slate-700 dark:text-slate-300 px-2 py-1 rounded-sm">
                                            {fn.signature}
                                        </code>
                                    </td>
                                    <td className="p-3 text-slate-600 dark:text-slate-300">
                                        {fn.kind === 'table' ? 'Tabela' : 'Escalar'}
                                    </td>
                                    <td className="p-3 text-right whitespace-nowrap">
                                        <button
                                            onClick={() => copyText(fn)}
                                            className="text-slate-400 hover:text-violet-500 p-1"
                                            title="Copiar chamada"
                                        >
                                            {copiedId === fn.id ? <CheckCircle className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                                        </button>
                                        <button
                                            onClick={() => openEdit(fn)}
                                            className="text-slate-400 hover:text-blue-500 p-1 ml-1"
                                            title="Editar"
                                        >
                                            <Pencil className="w-4 h-4" />
                                        </button>
                                        <button
                                            onClick={() => handleDelete(fn)}
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
                    className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
                    onClick={(e) => e.target === e.currentTarget && setShowModal(false)}
                >
                    <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-5xl p-6 max-h-[90vh] overflow-y-auto border dark:border-slate-700">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="text-xl font-bold text-slate-800 dark:text-slate-100">
                                {editingId ? 'Editar Função' : 'Criar Função'}
                            </h3>
                            <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
                                <X className="w-6 h-6" />
                            </button>
                        </div>

                        {formError && (
                            <div className="mb-4 p-3 rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 text-sm flex items-center gap-2">
                                <AlertCircle className="w-4 h-4" /> {formError}
                            </div>
                        )}

                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Nome</label>
                                <input
                                    value={form.name}
                                    onChange={e => updateForm({ name: e.target.value })}
                                    className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Nome SQL</label>
                                <input
                                    value={form.function_name}
                                    onChange={e => updateForm({ function_name: e.target.value })}
                                    placeholder="fn_minha_funcao"
                                    className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 font-mono text-sm"
                                />
                            </div>
                            <div className="lg:col-span-2">
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Descrição</label>
                                <textarea
                                    value={form.description}
                                    onChange={e => updateForm({ description: e.target.value })}
                                    rows={2}
                                    className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Tipo</label>
                                <select
                                    value={form.kind}
                                    onChange={e => updateForm({ kind: e.target.value })}
                                    className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                >
                                    <option value="scalar">Escalar</option>
                                    <option value="table">Tabela</option>
                                </select>
                            </div>
                            {form.kind === 'scalar' && (
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Retorno</label>
                                    <select
                                        value={form.return_type}
                                        onChange={e => updateForm({ return_type: e.target.value })}
                                        className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                    >
                                        {TYPE_OPTIONS.map(type => <option key={type} value={type}>{type}</option>)}
                                    </select>
                                </div>
                            )}
                            <div className="lg:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-3">
                                {Object.entries(FUNCTION_KIND_HELP).map(([kind, help]) => {
                                    const isActive = form.kind === kind;
                                    return (
                                        <div
                                            key={kind}
                                            className={`rounded-md border p-3 transition-colors ${isActive
                                                ? 'border-violet-300 bg-violet-50 dark:border-violet-700 dark:bg-violet-900/20'
                                                : 'border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-900/40'
                                                }`}
                                        >
                                            <div className="text-sm font-semibold text-slate-800 dark:text-slate-100">{help.title}</div>
                                            <p className="mt-1 text-xs leading-5 text-slate-600 dark:text-slate-400">{help.description}</p>
                                            <code className="mt-2 block text-xs text-slate-500 dark:text-slate-400 font-mono truncate">
                                                {help.example}
                                            </code>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>

                        <div className="mt-5">
                            <div className="flex items-center justify-between mb-2">
                                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Parâmetros</label>
                                <button
                                    onClick={() => updateForm({ parameters: [...form.parameters, emptyParam()] })}
                                    className="text-violet-600 dark:text-violet-300 text-sm font-medium flex items-center gap-1"
                                >
                                    <Plus className="w-4 h-4" /> Adicionar
                                </button>
                            </div>
                            <div className="space-y-2">
                                {form.parameters.length === 0 && (
                                    <div className="text-sm text-slate-400 italic">Sem parâmetros.</div>
                                )}
                                {form.parameters.map((param, idx) => (
                                    <div key={idx} className="grid grid-cols-[1fr_180px_36px] gap-2">
                                        <input
                                            value={param.name}
                                            onChange={e => updateParameter(idx, { name: e.target.value })}
                                            placeholder="nome_parametro"
                                            className="p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 font-mono text-sm"
                                        />
                                        <select
                                            value={param.type}
                                            onChange={e => updateParameter(idx, { type: e.target.value })}
                                            className="p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                        >
                                            {TYPE_OPTIONS.map(type => <option key={type} value={type}>{type}</option>)}
                                        </select>
                                        <button
                                            onClick={() => updateForm({ parameters: form.parameters.filter((_, i) => i !== idx) })}
                                            className="text-slate-400 hover:text-red-500"
                                            title="Remover"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {form.kind === 'table' && (
                            <div className="mt-5">
                                <div className="flex items-center justify-between mb-2">
                                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Colunas de retorno</label>
                                    <button
                                        onClick={() => updateForm({ return_columns: [...form.return_columns, emptyColumn()] })}
                                        className="text-violet-600 dark:text-violet-300 text-sm font-medium flex items-center gap-1"
                                    >
                                        <Plus className="w-4 h-4" /> Adicionar
                                    </button>
                                </div>
                                <div className="space-y-2">
                                    {form.return_columns.map((col, idx) => (
                                        <div key={idx} className="grid grid-cols-[1fr_180px_36px] gap-2">
                                            <input
                                                value={col.name}
                                                onChange={e => updateReturnColumn(idx, { name: e.target.value })}
                                                placeholder="nome_coluna"
                                                className="p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 font-mono text-sm"
                                            />
                                            <select
                                                value={col.type}
                                                onChange={e => updateReturnColumn(idx, { type: e.target.value })}
                                                className="p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                            >
                                                {TYPE_OPTIONS.map(type => <option key={type} value={type}>{type}</option>)}
                                            </select>
                                            <button
                                                onClick={() => updateForm({ return_columns: form.return_columns.filter((_, i) => i !== idx) })}
                                                className="text-slate-400 hover:text-red-500"
                                                title="Remover"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div className="mt-5">
                            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">SQL</label>
                            <textarea
                                value={form.sql_body}
                                onChange={e => updateForm({ sql_body: e.target.value })}
                                rows={8}
                                className="w-full p-3 border rounded-md font-mono text-sm bg-slate-50 dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-violet-500"
                            />
                        </div>

                        {validation && (
                            <div className={`mt-4 p-3 rounded-md text-sm flex items-start gap-2 ${validation.type === 'success' ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400' : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'}`}>
                                {validation.type === 'success' ? <CheckCircle className="w-4 h-4 mt-0.5" /> : <AlertCircle className="w-4 h-4 mt-0.5" />}
                                <div>
                                    <div>{validation.message}</div>
                                    {validation.signature && (
                                        <code className="block mt-1 text-xs">{validation.signature}</code>
                                    )}
                                    {validation.callExample && (
                                        <code className="block mt-1 text-xs">{validation.callExample}</code>
                                    )}
                                </div>
                            </div>
                        )}

                        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-slate-200 dark:border-slate-700">
                            <button
                                onClick={() => setShowModal(false)}
                                className="px-4 py-2 text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700 rounded-md"
                            >
                                Cancelar
                            </button>
                            <button
                                onClick={handleValidate}
                                disabled={validating || !form.name || !form.sql_body}
                                className="px-4 py-2 bg-slate-800 text-white rounded-md hover:bg-slate-700 disabled:opacity-50 flex items-center gap-2"
                            >
                                {validating && <Loader2 className="w-4 h-4 animate-spin" />}
                                Validar
                            </button>
                            <button
                                onClick={handleSave}
                                disabled={saving || validation?.type !== 'success'}
                                className="bg-violet-600 text-white px-6 py-2 rounded-md hover:bg-violet-700 disabled:opacity-50 flex items-center gap-2"
                            >
                                {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                                {editingId ? 'Atualizar' : 'Criar'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default FunctionsPage;
