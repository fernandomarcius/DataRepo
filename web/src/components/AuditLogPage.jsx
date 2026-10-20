import React, { useCallback, useEffect, useState } from 'react';
import { ShieldCheck, AlertCircle, ChevronLeft, ChevronRight } from 'lucide-react';
import { getAuditLogs } from '../api/client';
import { ACTION_BADGE, ACTION_LABELS, ENTITY_LABELS, formatTs } from '../utils/auditFormat';
import AuditLogDetail from './AuditLogDetail';

const ENTITY_TYPES = ['', 'user', 'report', 'view', 'table', 'table_row', 'file', 'function', 'connection'];
const ACTIONS = ['', 'CREATE', 'UPDATE', 'DELETE', 'UPLOAD', 'RENAME', 'ANALYZE', 'INSERT', 'SYNC',
    'PASSWORD_RESET_REQUEST', 'PASSWORD_RESET', 'PASSWORD_CHANGE'];
const PAGE_SIZES = [25, 50, 100];

const emptyFilters = () => ({
    entity_type: '',
    action: '',
    q: '',
    from: '',
    to: '',
});

const AuditLogPage = () => {
    const [logs, setLogs] = useState([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(25);
    const [filters, setFilters] = useState(emptyFilters());
    const [qInput, setQInput] = useState('');
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [selectedEntry, setSelectedEntry] = useState(null);

    const totalPages = Math.max(1, Math.ceil(total / pageSize));

    const fetchLogs = useCallback(async (signal) => {
        setLoading(true);
        setError(null);
        try {
            const params = { page, page_size: pageSize };
            if (filters.entity_type) params.entity_type = filters.entity_type;
            if (filters.action) params.action = filters.action;
            if (filters.q) params.q = filters.q;
            if (filters.from) params.from = filters.from;
            if (filters.to) params.to = filters.to;

            const res = await getAuditLogs(params, signal);
            setLogs(res.data.logs || []);
            setTotal(res.data.total || 0);
        } catch (err) {
            if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED') return;
            setError(err.response?.data?.error || 'Falha ao carregar audit log');
            setLogs([]);
            setTotal(0);
        } finally {
            setLoading(false);
        }
    }, [page, pageSize, filters]);

    useEffect(() => {
        const controller = new AbortController();
        fetchLogs(controller.signal);
        return () => controller.abort();
    }, [fetchLogs]);

    // Debounce the free-text search so each keystroke doesn't fire a request.
    useEffect(() => {
        const handle = setTimeout(() => {
            setFilters((prev) => (prev.q === qInput ? prev : { ...prev, q: qInput }));
            setPage(1);
        }, 350);
        return () => clearTimeout(handle);
    }, [qInput]);

    const handleFilterChange = (key, value) => {
        setFilters((prev) => ({ ...prev, [key]: value }));
        setPage(1);
    };

    const handlePageSizeChange = (e) => {
        setPageSize(Number(e.target.value));
        setPage(1);
    };

    const inputCls = 'px-3 py-2 text-sm border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-800 dark:text-slate-200 focus:outline-hidden focus:ring-2 focus:ring-violet-500 focus:border-transparent';

    return (
        <div className="flex flex-col gap-6">
            {/* Page header */}
            <div className="flex items-center gap-2">
                <ShieldCheck className="w-6 h-6 text-violet-600 dark:text-violet-400" />
                <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Audit Log</h2>
            </div>

            {/* Filter bar */}
            <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xs border border-slate-200 dark:border-slate-700 p-4">
                <div className="flex flex-wrap items-end gap-3">
                    <div className="flex flex-col gap-1">
                        <label className="text-xs font-medium text-slate-500 dark:text-slate-400">Entidade</label>
                        <select
                            value={filters.entity_type}
                            onChange={(e) => handleFilterChange('entity_type', e.target.value)}
                            className={inputCls}
                        >
                            <option value="">Todas</option>
                            {ENTITY_TYPES.filter(Boolean).map((t) => (
                                <option key={t} value={t}>{ENTITY_LABELS[t] || t}</option>
                            ))}
                        </select>
                    </div>

                    <div className="flex flex-col gap-1">
                        <label className="text-xs font-medium text-slate-500 dark:text-slate-400">Ação</label>
                        <select
                            value={filters.action}
                            onChange={(e) => handleFilterChange('action', e.target.value)}
                            className={inputCls}
                        >
                            <option value="">Todas</option>
                            {ACTIONS.filter(Boolean).map((a) => (
                                <option key={a} value={a}>{ACTION_LABELS[a] || a}</option>
                            ))}
                        </select>
                    </div>

                    <div className="flex flex-col gap-1 flex-1 min-w-[140px]">
                        <label className="text-xs font-medium text-slate-500 dark:text-slate-400">Usuário / ID</label>
                        <input
                            type="text"
                            value={qInput}
                            onChange={(e) => setQInput(e.target.value)}
                            placeholder="buscar por usuário ou ID…"
                            className={inputCls}
                        />
                    </div>

                    <div className="flex flex-col gap-1">
                        <label className="text-xs font-medium text-slate-500 dark:text-slate-400">De</label>
                        <input type="date" value={filters.from} onChange={(e) => handleFilterChange('from', e.target.value)} className={inputCls} />
                    </div>

                    <div className="flex flex-col gap-1">
                        <label className="text-xs font-medium text-slate-500 dark:text-slate-400">Até</label>
                        <input type="date" value={filters.to} onChange={(e) => handleFilterChange('to', e.target.value)} className={inputCls} />
                    </div>

                    <button
                        onClick={() => { setFilters(emptyFilters()); setQInput(''); setPage(1); }}
                        className="px-3 py-2 text-sm text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 border border-slate-300 dark:border-slate-600 rounded-md hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                    >
                        Limpar
                    </button>
                </div>
            </div>

            {/* Table */}
            <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md overflow-hidden border border-slate-200 dark:border-slate-700">
                {loading ? (
                    <div className="p-8 text-center text-slate-500 dark:text-slate-400">Carregando…</div>
                ) : error ? (
                    <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 shrink-0" /> {error}
                    </div>
                ) : logs.length === 0 ? (
                    <div className="p-8 text-center text-slate-400 dark:text-slate-500 italic">Nenhum evento encontrado.</div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead className="bg-slate-50 dark:bg-slate-700/50 text-slate-600 dark:text-slate-300">
                                <tr>
                                    <th className="text-left p-3 whitespace-nowrap">Data / Hora</th>
                                    <th className="text-left p-3">Usuário</th>
                                    <th className="text-left p-3">Ação</th>
                                    <th className="text-left p-3">Entidade</th>
                                    <th className="text-left p-3">ID</th>
                                    <th className="text-left p-3">Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {logs.map((log) => (
                                    <tr
                                        key={log.id}
                                        onClick={() => setSelectedEntry(log)}
                                        className="border-t border-slate-200 dark:border-slate-700 cursor-pointer hover:bg-violet-50 dark:hover:bg-violet-900/10 transition-colors"
                                    >
                                        <td className="p-3 text-slate-500 dark:text-slate-400 whitespace-nowrap font-mono text-xs">
                                            {formatTs(log.ts)}
                                        </td>
                                        <td className="p-3 text-slate-700 dark:text-slate-200 font-medium">
                                            {log.username || <span className="text-slate-400 italic">—</span>}
                                        </td>
                                        <td className="p-3">
                                            <span className={`text-xs font-bold px-2 py-0.5 rounded-sm uppercase tracking-wide ${ACTION_BADGE[log.action] || 'bg-slate-100 text-slate-700'}`}>
                                                {ACTION_LABELS[log.action] || log.action}
                                            </span>
                                        </td>
                                        <td className="p-3 text-slate-600 dark:text-slate-300">
                                            {ENTITY_LABELS[log.entity_type] || log.entity_type}
                                        </td>
                                        <td className="p-3 text-slate-500 dark:text-slate-400 font-mono text-xs">
                                            {log.entity_id || '—'}
                                        </td>
                                        <td className="p-3">
                                            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                                                log.status === 'success'
                                                    ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                                                    : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                                            }`}>
                                                {log.status === 'success' ? 'OK' : 'Erro'}
                                            </span>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Pagination */}
            {!loading && !error && (
                <div className="flex items-center justify-between text-sm text-slate-600 dark:text-slate-400">
                    <div className="flex items-center gap-2">
                        <span>Por página:</span>
                        <select
                            value={pageSize}
                            onChange={handlePageSizeChange}
                            className="px-2 py-1.5 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-800 dark:text-slate-200 focus:outline-hidden focus:ring-2 focus:ring-violet-500 focus:border-transparent"
                        >
                            {PAGE_SIZES.map((s) => <option key={s} value={s}>{s}</option>)}
                        </select>
                        <span className="text-slate-400 dark:text-slate-500">
                            {total} {total === 1 ? 'entrada' : 'entradas'}
                        </span>
                    </div>

                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setPage((p) => Math.max(1, p - 1))}
                            disabled={page <= 1}
                            className="p-1.5 rounded-md border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                            <ChevronLeft className="w-4 h-4" />
                        </button>
                        <span className="px-2">
                            <span className="font-semibold text-slate-800 dark:text-slate-200">{page}</span> / {totalPages}
                        </span>
                        <button
                            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                            disabled={page >= totalPages}
                            className="p-1.5 rounded-md border border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                            <ChevronRight className="w-4 h-4" />
                        </button>
                    </div>
                </div>
            )}

            {/* Detail modal */}
            {selectedEntry && (
                <AuditLogDetail
                    entry={selectedEntry}
                    onClose={() => setSelectedEntry(null)}
                />
            )}
        </div>
    );
};

export default AuditLogPage;
