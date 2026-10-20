import React, { useEffect, useRef, useState } from 'react';
import { X, ChevronDown, ChevronUp, AlertTriangle, User, Calendar, Tag, Hash } from 'lucide-react';
import ReactDiffViewer, { DiffMethod } from 'react-diff-viewer-continued';
import { getAuditLog } from '../api/client';
import { ACTION_BADGE, ACTION_LABELS, ENTITY_LABELS, formatTs } from '../utils/auditFormat';
import { useTheme } from '../context/ThemeContext';

// Human-readable labels for common DB column names
const FIELD_LABELS = {
    id: 'ID', username: 'Nome de usuário', created_at: 'Criado em',
    updated_at: 'Atualizado em', can_query: 'Permissão: Consultas',
    can_upload: 'Permissão: Upload', can_manage_views: 'Permissão: Views',
    can_manage_functions: 'Permissão: Funções',
    can_manage_users: 'Permissão: Usuários', can_view_audit: 'Permissão: Audit Log',
    password_hash: 'Senha', name: 'Nome', description: 'Descrição',
    definition: 'Definição SQL', table_name: 'Tabela', rows_inserted: 'Linhas inseridas',
    filename: 'Arquivo', status: 'Status', error: 'Erro', rows: 'Linhas',
    // Function entity
    kind: 'Tipo', sql_body: 'Corpo SQL', signature: 'Assinatura',
    parameters: 'Parâmetros', return_type: 'Tipo de retorno',
    return_columns: 'Colunas de retorno', call_example: 'Exemplo de chamada',
    function_name: 'Nome no banco',
};

const summarizeObject = (value) => {
    if (Array.isArray(value)) return `${value.length} ${value.length === 1 ? 'item' : 'itens'}`;
    const count = Object.keys(value).length;
    return `${count} ${count === 1 ? 'campo' : 'campos'}`;
};

// Function parameters and return columns share the {name, type} shape — render
// them inline as readable pills instead of an opaque "N itens" summary.
const isNameTypeArray = (value) =>
    Array.isArray(value) && value.length > 0 && value.every(
        (item) => item && typeof item === 'object' && 'name' in item && 'type' in item,
    );

const NameTypeList = ({ items }) => (
    <div className="flex flex-wrap gap-1">
        {items.map((item, i) => (
            <span
                key={`${item.name}-${i}`}
                className="inline-flex items-center gap-1 rounded-md bg-slate-100 dark:bg-slate-700 px-2 py-0.5 text-xs"
            >
                <span className="font-medium text-slate-800 dark:text-slate-200">{item.name}</span>
                <span className="text-slate-400">:</span>
                <span className="font-mono text-slate-600 dark:text-slate-300">{item.type}</span>
            </span>
        ))}
    </div>
);

const formatFieldValue = (key, value) => {
    if (value === null || value === undefined) return <span className="italic text-slate-400">—</span>;
    if (typeof value === 'boolean') {
        return (
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                value ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                      : 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400'
            }`}>
                {value ? 'Sim' : 'Não'}
            </span>
        );
    }
    if (Array.isArray(value) && value.length === 0) {
        return <span className="italic text-slate-400">vazio</span>;
    }
    if (isNameTypeArray(value)) {
        return <NameTypeList items={value} />;
    }
    if (key === 'sql_body' && typeof value === 'string') {
        return (
            <pre className="whitespace-pre-wrap break-all font-mono text-xs bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-700 rounded-sm p-2 text-slate-800 dark:text-slate-200">
                {value}
            </pre>
        );
    }
    if (typeof value === 'object') {
        return (
            <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                {summarizeObject(value)}
            </span>
        );
    }
    if (key.endsWith('_at') || key === 'ts') return <span>{formatTs(value)}</span>;
    return <span>{String(value)}</span>;
};

// Shows state fields as a readable table rather than raw JSON
const FieldsTable = ({ data, label, highlight }) => {
    if (!data || typeof data !== 'object') return null;

    const entries = Object.entries(data);
    if (entries.length === 0) return <p className="text-sm text-slate-400 italic">Sem dados.</p>;

    return (
        <div>
            {label && (
                <p className={`text-xs font-semibold mb-2 uppercase tracking-wide ${
                    highlight === 'green' ? 'text-green-600 dark:text-green-400'
                    : highlight === 'red' ? 'text-red-600 dark:text-red-400'
                    : 'text-slate-500 dark:text-slate-400'
                }`}>{label}</p>
            )}
            <div className="rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
                <table className="w-full text-sm">
                    <tbody>
                        {entries.map(([k, v], i) => (
                            <tr key={k} className={i % 2 === 0 ? 'bg-white dark:bg-slate-800' : 'bg-slate-50 dark:bg-slate-700/60'}>
                                <td className="px-3 py-2 font-medium text-slate-500 dark:text-slate-400 whitespace-nowrap w-48">
                                    {FIELD_LABELS[k] || k}
                                </td>
                                <td className="px-3 py-2 text-slate-800 dark:text-slate-200 break-all">
                                    {formatFieldValue(k, v)}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

const MetadataBlock = ({ metadata }) => {
    if (!metadata || Object.keys(metadata).length === 0) {
        return <p className="text-sm text-slate-400 italic">Sem metadados adicionais.</p>;
    }
    return (
        <div className="rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
            <table className="w-full text-sm">
                <tbody>
                    {Object.entries(metadata).map(([k, v], i) => (
                        <tr key={k} className={i % 2 === 0 ? 'bg-white dark:bg-slate-800' : 'bg-slate-50 dark:bg-slate-700/60'}>
                            <td className="px-3 py-2 font-medium text-slate-500 dark:text-slate-400 whitespace-nowrap w-48">
                                {FIELD_LABELS[k] || k}
                            </td>
                            <td className="px-3 py-2 text-slate-800 dark:text-slate-200 break-all">
                                {String(v ?? '—')}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
};

// Computes which keys differ between before and after states
const changedFields = (before, after) => {
    if (!before || !after) return [];
    const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
    return [...keys].filter((k) => JSON.stringify(before[k]) !== JSON.stringify(after[k]));
};

const ChangeValue = ({ fieldKey, value, tone }) => {
    const toneClass = tone === 'before'
        ? 'border-red-200 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-900/20 dark:text-red-200'
        : 'border-green-200 bg-green-50 text-green-900 dark:border-green-800 dark:bg-green-900/20 dark:text-green-200';

    return (
        <div className={`min-h-10 rounded-md border px-3 py-2 text-sm ${toneClass}`}>
            {formatFieldValue(fieldKey, value)}
        </div>
    );
};

const ChangedFieldsTable = ({ before, after }) => {
    const fields = changedFields(before, after);

    if (fields.length === 0) {
        return <p className="text-sm text-slate-400 italic">Nenhum campo alterado encontrado.</p>;
    }

    return (
        <div className="space-y-3">
            <div className="flex flex-wrap gap-1.5 items-center">
                <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                    {fields.length} {fields.length === 1 ? 'campo alterado' : 'campos alterados'}
                </span>
                {fields.map((field) => (
                    <span key={field} className="text-xs bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 px-2 py-0.5 rounded-sm font-medium">
                        {FIELD_LABELS[field] || field}
                    </span>
                ))}
            </div>

            <div className="rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
                <div className="hidden md:grid md:grid-cols-[minmax(9rem,14rem)_1fr_1fr] bg-slate-50 dark:bg-slate-700/50 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-300">
                    <div className="px-3 py-2">Campo</div>
                    <div className="px-3 py-2 text-red-600 dark:text-red-300">Antes</div>
                    <div className="px-3 py-2 text-green-600 dark:text-green-300">Depois</div>
                </div>
                {fields.map((field, index) => (
                    <div
                        key={field}
                        className={`grid grid-cols-1 md:grid-cols-[minmax(9rem,14rem)_1fr_1fr] gap-2 md:gap-3 px-3 py-3 text-sm ${
                            index % 2 === 0 ? 'bg-white dark:bg-slate-800' : 'bg-slate-50/70 dark:bg-slate-700/60'
                        }`}
                    >
                        <div className="font-medium text-slate-600 dark:text-slate-300">
                            {FIELD_LABELS[field] || field}
                        </div>
                        <div>
                            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-red-600 dark:text-red-300 md:hidden">Antes</p>
                            <ChangeValue fieldKey={field} value={before?.[field]} tone="before" />
                        </div>
                        <div>
                            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-green-600 dark:text-green-300 md:hidden">Depois</p>
                            <ChangeValue fieldKey={field} value={after?.[field]} tone="after" />
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

const BodyContent = ({ entry }) => {
    const { action, before_state, after_state, metadata } = entry;

    if (action === 'UPDATE' || action === 'RENAME') {
        if (before_state == null && after_state == null) {
            return <p className="text-sm text-slate-400 italic">Diff indisponível — estado anterior/posterior ausentes no log.</p>;
        }
        return (
            <ChangedFieldsTable before={before_state} after={after_state} />
        );
    }

    if (action === 'CREATE') {
        return <FieldsTable data={after_state} label="Dados criados" highlight="green" />;
    }

    if (action === 'DELETE') {
        return <FieldsTable data={before_state} label="Dados removidos" highlight="red" />;
    }

    // UPLOAD, ANALYZE, LOGIN, INSERT, QUERY — metadata key-value
    return (
        <div className="space-y-3">
            <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide">Detalhes do evento</p>
            <MetadataBlock metadata={metadata} />
        </div>
    );
};

const AuditLogDetail = ({ entry, onClose }) => {
    const [showRaw, setShowRaw] = useState(false);
    const [fullEntry, setFullEntry] = useState(entry);
    const { theme } = useTheme();
    const dialogRef = useRef(null);
    const errorText = fullEntry.error ?? fullEntry.error_message;

    // Focus dialog on mount so the Escape keydown handler receives the event.
    useEffect(() => {
        dialogRef.current?.focus();
    }, []);

    // Fetch the full entry — list endpoint may return summarized rows.
    useEffect(() => {
        let cancelled = false;
        getAuditLog(entry.id)
            .then((res) => { if (!cancelled) setFullEntry(res.data); })
            .catch(() => {});  // fall back to list payload silently
        return () => { cancelled = true; };
    }, [entry.id]);

    const badgeClass = ACTION_BADGE[fullEntry.action] || 'bg-slate-100 text-slate-700';
    const isFailure = fullEntry.status !== 'success';

    return (
        <div
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
            onClick={(e) => e.target === e.currentTarget && onClose()}
        >
            <div
                ref={dialogRef}
                tabIndex={-1}
                role="dialog"
                aria-modal="true"
                aria-labelledby="audit-detail-title"
                onKeyDown={(e) => e.key === 'Escape' && onClose()}
                className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col border dark:border-slate-700 focus:outline-hidden"
            >
                {/* Header — two rows */}
                <div className="p-5 border-b border-slate-200 dark:border-slate-700">
                    <div className="flex items-start justify-between gap-4">
                        {/* Action + entity */}
                        <div className="flex flex-wrap items-center gap-2 min-w-0 flex-1">
                            <span id="audit-detail-title" className={`text-sm font-bold px-3 py-1 rounded-full uppercase tracking-wide ${badgeClass}`}>
                                {ACTION_LABELS[fullEntry.action] || fullEntry.action}
                            </span>
                            <span className="text-base font-semibold text-slate-800 dark:text-slate-100">
                                {ENTITY_LABELS[fullEntry.entity_type] || fullEntry.entity_type}
                                {fullEntry.entity_id && (
                                    <span className="ml-1 text-slate-400 dark:text-slate-500 font-mono text-sm">
                                        #{fullEntry.entity_id}
                                    </span>
                                )}
                            </span>
                            {isFailure && (
                                <span className="flex items-center gap-1 text-xs font-semibold text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 px-2 py-0.5 rounded-full border border-red-200 dark:border-red-800">
                                    <AlertTriangle className="w-3 h-3" /> Falha
                                </span>
                            )}
                        </div>
                        <button
                            onClick={onClose}
                            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 shrink-0 p-1 rounded-md hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                            aria-label="Fechar"
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>

                    {/* Metadata row */}
                    <div className="mt-3 flex flex-wrap gap-4 text-sm text-slate-600 dark:text-slate-400">
                        <div className="flex items-center gap-1.5">
                            <User className="w-3.5 h-3.5 text-slate-400" />
                            <span>{fullEntry.username || <span className="italic text-slate-400">—</span>}</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                            <Calendar className="w-3.5 h-3.5 text-slate-400" />
                            <span>{formatTs(fullEntry.ts)}</span>
                        </div>
                        {fullEntry.entity_type && (
                            <div className="flex items-center gap-1.5">
                                <Tag className="w-3.5 h-3.5 text-slate-400" />
                                <span>{ENTITY_LABELS[fullEntry.entity_type] || fullEntry.entity_type}</span>
                            </div>
                        )}
                        {fullEntry.entity_id && (
                            <div className="flex items-center gap-1.5">
                                <Hash className="w-3.5 h-3.5 text-slate-400" />
                                <span className="font-mono">{fullEntry.entity_id}</span>
                            </div>
                        )}
                    </div>
                </div>

                {/* Error message */}
                {errorText && (
                    <div className="mx-5 mt-4 flex items-start gap-2 px-3 py-2.5 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 text-sm rounded-lg border border-red-200 dark:border-red-800">
                        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                        <div className="flex-1 min-w-0 max-h-48 overflow-y-auto whitespace-pre-wrap break-all">
                            <span className="font-semibold">Erro:</span> {errorText}
                        </div>
                    </div>
                )}

                {/* Body */}
                <div className="flex-1 overflow-auto p-5 space-y-5">
                    <BodyContent entry={fullEntry} />

                    {/* Raw JSON toggle */}
                    <div className="border-t border-slate-200 dark:border-slate-700 pt-4">
                        <button
                            onClick={() => setShowRaw((v) => !v)}
                            className="flex items-center gap-1.5 text-xs text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                        >
                            {showRaw ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                            Ver JSON bruto
                        </button>

                        {showRaw && (
                            <div className="mt-3">
                                {fullEntry.before_state == null && fullEntry.after_state == null && (
                                    <p className="text-sm text-slate-400 italic">Sem before_state nem after_state.</p>
                                )}
                                {(fullEntry.before_state != null || fullEntry.after_state != null) && (
                                    <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
                                        <ReactDiffViewer
                                            splitView={true}
                                            compareMethod={DiffMethod.WORDS}
                                            useDarkTheme={theme === 'dark'}
                                            oldValue={JSON.stringify(fullEntry.before_state ?? null, null, 2)}
                                            newValue={JSON.stringify(fullEntry.after_state ?? null, null, 2)}
                                            leftTitle="before_state"
                                            rightTitle="after_state"
                                        />
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AuditLogDetail;
