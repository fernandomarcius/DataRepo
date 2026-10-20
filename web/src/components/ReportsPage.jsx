import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { FileText, Play, Trash2, Loader2, AlertCircle, Plus, X, CheckCircle, Pencil, Search, Database, RefreshCw, CalendarClock } from 'lucide-react';
import ResultsTable from './ResultsTable';
import api, { materializeReport, unmaterializeReport, refreshReport } from '../api/client';
import { useAuth } from '../context/AuthContext';

const WEEKDAY_LABELS = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];

const buildScheduleLabel = (preset) => {
    if (!preset) return '';
    if (preset.type === 'hourly') return 'A cada hora';
    if (preset.type === 'every_n_hours') return `A cada ${preset.interval}h`;
    if (preset.type === 'every_n_days') return `A cada ${preset.day_interval}d · ${preset.times_per_day}x/dia`;
    if (preset.type === 'weekdays') {
        const days = [...(preset.weekdays || [])].sort((a, b) => a - b).map(d => WEEKDAY_LABELS[d]).join(', ');
        return days ? `${days} às ${preset.time}` : 'Dias da semana';
    }
    if (preset.type === 'daily') return `Diário às ${preset.time}`;
    if (preset.type === 'weekly') return `Semanal · ${WEEKDAY_LABELS[preset.weekday] || ''} às ${preset.time}`;
    return '';
};

const formatTimestamp = (value) => {
    if (!value) return null;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d.toLocaleString();
};

const ReportsPage = () => {
    const { hasPermission } = useAuth();
    const canManage = hasPermission('can_manage_views');
    const [reports, setReports] = useState([]);
    const [managedFunctions, setManagedFunctions] = useState([]);
    const [loading, setLoading] = useState(false);
    const [executingId, setExecutingId] = useState(null);
    const [results, setResults] = useState(null);
    const [activeReport, setActiveReport] = useState(null);
    const [error, setError] = useState(null);

    // Create/Edit Modal State
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [createForm, setCreateForm] = useState({ name: '', description: '', sql: '' });
    const [testStatus, setTestStatus] = useState(null);
    const [isVerified, setIsVerified] = useState(false);
    const [testing, setTesting] = useState(false);
    const [isEditing, setIsEditing] = useState(false);
    const [editingId, setEditingId] = useState(null);
    const [reportsListWidth, setReportsListWidth] = useState(380);
    const [searchOpen, setSearchOpen] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const isResizing = useRef(false);
    const reportsLayoutRef = useRef(null);
    const searchInputRef = useRef(null);

    // Materialization state
    const [showScheduleModal, setShowScheduleModal] = useState(false);
    const [scheduleTarget, setScheduleTarget] = useState(null);
    const [schedulePreset, setSchedulePreset] = useState({ type: 'daily', time: '08:00', weekday: 1, interval: 3, day_interval: 1, times_per_day: 1, weekdays: [1, 4] });
    const [togglingId, setTogglingId] = useState(null);

    const normalizedSearch = searchTerm.trim().toLowerCase();
    const filteredReports = useMemo(() => {
        if (!normalizedSearch) return reports;
        return reports.filter(report => [
            report.id,
            report.name,
            report.description,
            report.view_name,
        ].some(value => String(value || '').toLowerCase().includes(normalizedSearch)));
    }, [reports, normalizedSearch]);

    useEffect(() => {
        fetchReports();
        fetchFunctions();
    }, []);

    // Poll while any view is being built/refreshed so the badge updates itself.
    const hasPending = reports.some(r => ['building', 'refreshing'].includes(r.materialization?.last_status));
    useEffect(() => {
        if (!hasPending) return undefined;
        const interval = setInterval(fetchReports, 5000);
        return () => clearInterval(interval);
    }, [hasPending]);

    const toggleSearch = () => {
        setSearchOpen(prev => {
            if (prev) setSearchTerm('');
            return !prev;
        });
    };

    useEffect(() => {
        if (searchOpen) {
            searchInputRef.current?.focus();
        }
    }, [searchOpen]);

    const startResizing = useCallback((e) => {
        isResizing.current = true;
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    }, []);

    const stopResizing = useCallback(() => {
        isResizing.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    }, []);

    const resizeReportsList = useCallback((e) => {
        if (!isResizing.current || !reportsLayoutRef.current) return;
        const rect = reportsLayoutRef.current.getBoundingClientRect();
        const newWidth = Math.min(620, Math.max(320, e.clientX - rect.left));
        setReportsListWidth(newWidth);
    }, []);

    useEffect(() => {
        window.addEventListener('mousemove', resizeReportsList);
        window.addEventListener('mouseup', stopResizing);
        return () => {
            window.removeEventListener('mousemove', resizeReportsList);
            window.removeEventListener('mouseup', stopResizing);
        };
    }, [resizeReportsList, stopResizing]);

    const fetchReports = async () => {
        setLoading(true);
        try {
            const res = await api.get('/reports');
            setReports(res.data.reports || []);
        } catch (err) {
            setError("Failed to load reports");
        } finally {
            setLoading(false);
        }
    };

    const fetchFunctions = async () => {
        try {
            const res = await api.get('/functions');
            setManagedFunctions(res.data.functions || []);
        } catch (err) {
            console.error('Failed to load functions', err);
        }
    };

    const handleSelect = (report) => {
        if (activeReport?.id === report.id) return;
        setActiveReport(report);
        setResults(null);
        setError(null);
    };

    const handleExecute = async (report) => {
        setExecutingId(report.id);
        setResults(null);
        setError(null);
        setActiveReport(report);

        try {
            const res = await api.get(`/reports/${report.id}/execute`);
            setResults(res.data.results);
        } catch (err) {
            setError(err.response?.data?.error || "Failed to execute report");
        } finally {
            setExecutingId(null);
        }
    };

    const handleDelete = async (id, e) => {
        e.stopPropagation();
        if (!window.confirm("Are you sure you want to delete this report?")) return;

        try {
            await api.delete(`/reports/${id}`);
            setReports(reports.filter(r => r.id !== id));
            if (activeReport?.id === id) {
                setResults(null);
                setActiveReport(null);
            }
        } catch (err) {
            alert("Failed to delete report");
        }
    };

    const handleTestQuery = async () => {
        if (!createForm.sql) return;
        setTesting(true);
        setTestStatus(null);
        setIsVerified(false);
        try {
            await api.post('/query', { sql: createForm.sql });
            setTestStatus({ type: 'success', message: 'Query verified successfully!' });
            setIsVerified(true);
        } catch (err) {
            setTestStatus({ type: 'error', message: err.response?.data?.error || 'Query failed' });
            setIsVerified(false);
        } finally {
            setTesting(false);
        }
    };

    const handleEdit = (report, e) => {
        e.stopPropagation();
        setCreateForm({
            name: report.name,
            description: report.description || '',
            sql: report.sql_query
        });
        setIsEditing(true);
        setEditingId(report.id);
        // Assume existing saved query is valid, or force re-test?
        // Let's force re-test if they change it, but initially we need to allow saving if they just change name
        // For simplicity, we'll mark as Verified initially, but if sql changes, verify becomes false.
        setIsVerified(true);
        setShowCreateModal(true);
    };

    const handleSaveReport = async () => {
        if (!isVerified) return;

        try {
            if (isEditing) {
                await api.put(`/reports/${editingId}`, {
                    name: createForm.name,
                    description: createForm.description,
                    sql_query: createForm.sql
                });
            } else {
                await api.post('/reports', {
                    name: createForm.name,
                    description: createForm.description,
                    sql_query: createForm.sql
                });
            }

            setShowCreateModal(false);
            setCreateForm({ name: '', description: '', sql: '' });
            setIsVerified(false);
            setTestStatus(null);
            setIsEditing(false);
            setEditingId(null);
            fetchReports();
        } catch (err) {
            alert(isEditing ? 'Failed to update view' : 'Failed to create view');
        }
    };

    const openScheduleModal = (report, e) => {
        e.stopPropagation();
        setScheduleTarget(report);
        setSchedulePreset({ type: 'daily', time: '08:00', weekday: 1, interval: 3, day_interval: 1, times_per_day: 1, weekdays: [1, 4] });
        setShowScheduleModal(true);
    };

    const handleMaterialize = async () => {
        if (!scheduleTarget) return;
        setTogglingId(scheduleTarget.id);
        try {
            await materializeReport(scheduleTarget.id, schedulePreset);
            setShowScheduleModal(false);
            setScheduleTarget(null);
            await fetchReports();
        } catch (err) {
            alert(err.response?.data?.error || 'Falha ao materializar a view');
        } finally {
            setTogglingId(null);
        }
    };

    const handleUnmaterialize = async (report, e) => {
        e.stopPropagation();
        if (!window.confirm(`Desmaterializar "${report.name}"? Ela volta a ser uma view comum e o agendamento é removido.`)) return;
        setTogglingId(report.id);
        try {
            await unmaterializeReport(report.id);
            await fetchReports();
        } catch (err) {
            alert(err.response?.data?.error || 'Falha ao desmaterializar a view');
        } finally {
            setTogglingId(null);
        }
    };

    const handleRefreshNow = async (report, e) => {
        e.stopPropagation();
        setTogglingId(report.id);
        try {
            await refreshReport(report.id);
            await fetchReports();
        } catch (err) {
            alert(err.response?.data?.error || 'Falha ao atualizar a view');
        } finally {
            setTogglingId(null);
        }
    };

    const insertFunctionCall = (fn) => {
        const call = fn.call_example || fn.function_name;
        setCreateForm(prev => ({
            ...prev,
            sql: prev.sql ? `${prev.sql}\n${call}` : call,
        }));
        setIsVerified(false);
        setTestStatus(null);
    };

    return (
        <div className="flex flex-col h-full gap-6">
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                    <FileText className="w-6 h-6 text-violet-600 dark:text-violet-400" />
                    <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100">Saved Views</h2>
                </div>
                {canManage && (
                    <button
                        onClick={() => {
                            setIsEditing(false);
                            setEditingId(null);
                            setCreateForm({ name: '', description: '', sql: '' });
                            setIsVerified(false);
                            setShowCreateModal(true);
                        }}
                        className="bg-violet-600 text-white px-4 py-2 rounded-md hover:bg-violet-700 flex items-center gap-2"
                    >
                        <Plus className="w-4 h-4" /> Create View
                    </button>
                )}
            </div>

            <div
                ref={reportsLayoutRef}
                className="flex flex-col lg:flex-row gap-4 lg:gap-0 h-[calc(100vh-140px)]"
                style={{ '--reports-list-width': `${reportsListWidth}px` }}
            >
                {/* Reports List */}
                <div className="w-full lg:w-(--reports-list-width) bg-white dark:bg-slate-800 rounded-lg shadow-md overflow-hidden flex flex-col transition-colors duration-200">
                    <div className="p-4 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-700/50 font-medium text-slate-700 dark:text-slate-200 flex items-center justify-between gap-2">
                        <span>Available Views</span>
                        <button
                            onClick={toggleSearch}
                            className={`p-1 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-sm transition-colors ${searchOpen ? 'text-violet-600 dark:text-violet-400' : 'text-slate-400 dark:text-slate-500 hover:text-violet-600 dark:hover:text-violet-400'}`}
                            title={searchOpen ? 'Fechar pesquisa' : 'Pesquisar'}
                        >
                            <Search className="w-4 h-4" />
                        </button>
                    </div>
                    {searchOpen && (
                        <div className="px-2 py-2 border-b border-slate-200 dark:border-slate-800 bg-slate-100 dark:bg-slate-800/50">
                            <div className="relative">
                                <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                                <input
                                    ref={searchInputRef}
                                    type="text"
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                    onKeyDown={(e) => { if (e.key === 'Escape') toggleSearch(); }}
                                    placeholder="Pesquisar..."
                                    className="w-full pl-7 pr-7 py-1 text-sm rounded-sm border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 placeholder:text-slate-400 focus:outline-hidden focus:ring-1 focus:ring-violet-500/40 focus:border-violet-500"
                                />
                                {searchTerm && (
                                    <button
                                        onClick={() => setSearchTerm('')}
                                        className="absolute right-1 top-1/2 -translate-y-1/2 p-0.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-sm"
                                        title="Limpar"
                                    >
                                        <X className="w-3 h-3" />
                                    </button>
                                )}
                            </div>
                        </div>
                    )}
                    <div className="overflow-y-auto flex-1 p-2 space-y-2">
                        {loading && <div className="text-center p-4 text-slate-500">Loading...</div>}

                        {!loading && reports.length === 0 && (
                            <div className="text-center p-8 text-slate-400 italic">
                                No views saved yet.
                                <br />
                                <span className="text-xs">Create one or save from Query tab.</span>
                            </div>
                        )}

                        {!loading && reports.length > 0 && filteredReports.length === 0 && (
                            <div className="text-center p-8 text-slate-400 italic">
                                Nenhuma view encontrada.
                            </div>
                        )}

                        {filteredReports.map(report => (
                            <div
                                key={report.id}
                                onClick={() => handleSelect(report)}
                                className={`p-3 rounded-lg border cursor-pointer transition-all hover:shadow-md group relative
                                    ${activeReport?.id === report.id
                                        ? 'border-violet-500 bg-violet-50 dark:bg-violet-900/20'
                                        : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:border-violet-300 dark:hover:border-violet-500/50'}
                                `}
                            >
                                <div className="flex items-start gap-2">
                                    <div className="min-w-0 flex-1">
                                        <h3 className="font-semibold text-slate-800 dark:text-slate-200 truncate" title={report.name}>
                                            <span className="text-violet-500 dark:text-violet-400 font-mono mr-2">#{report.id}</span>
                                            {report.name}
                                        </h3>
                                        {report.description && (
                                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 line-clamp-2">{report.description}</p>
                                        )}
                                        {report.view_name && (
                                            <div className="mt-1 max-w-full truncate text-[10px] font-mono text-violet-600 bg-violet-50 px-1.5 py-0.5 rounded-sm w-fit border border-violet-100" title={`Use this name in SQL queries: ${report.view_name}`}>
                                                SQL: {report.view_name}
                                            </div>
                                        )}
                                    </div>
                                    {canManage && (
                                        <div className="flex shrink-0 gap-1">
                                            {report.is_materialized ? (
                                                <>
                                                    <button
                                                        onClick={(e) => handleRefreshNow(report, e)}
                                                        disabled={togglingId === report.id || ['building', 'refreshing'].includes(report.materialization?.last_status)}
                                                        className="text-slate-400 hover:text-violet-500 opacity-0 group-hover:opacity-100 transition-opacity p-1 disabled:opacity-40"
                                                        title="Atualizar agora"
                                                    >
                                                        <RefreshCw className={`w-4 h-4 ${['building', 'refreshing'].includes(report.materialization?.last_status) ? 'animate-spin' : ''}`} />
                                                    </button>
                                                    <button
                                                        onClick={(e) => handleUnmaterialize(report, e)}
                                                        disabled={togglingId === report.id}
                                                        className="text-violet-500 hover:text-amber-500 opacity-0 group-hover:opacity-100 transition-opacity p-1 disabled:opacity-40"
                                                        title="Desmaterializar (voltar a view comum)"
                                                    >
                                                        <Database className="w-4 h-4" />
                                                    </button>
                                                </>
                                            ) : (
                                                <button
                                                    onClick={(e) => openScheduleModal(report, e)}
                                                    disabled={togglingId === report.id}
                                                    className="text-slate-400 hover:text-violet-500 opacity-0 group-hover:opacity-100 transition-opacity p-1 disabled:opacity-40"
                                                    title="Materializar com refresh agendado"
                                                >
                                                    <Database className="w-4 h-4" />
                                                </button>
                                            )}
                                            <button
                                                onClick={(e) => handleEdit(report, e)}
                                                className="text-slate-400 hover:text-blue-500 opacity-0 group-hover:opacity-100 transition-opacity p-1"
                                                title="Edit View"
                                            >
                                                <Pencil className="w-4 h-4" />
                                            </button>
                                            <button
                                                onClick={(e) => handleDelete(report.id, e)}
                                                className="text-slate-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity p-1"
                                                title="Delete Report"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                    )}
                                </div>
                                {report.is_materialized && (
                                    <div className="mt-2">
                                        <div className="flex items-center gap-1 text-[10px] font-medium text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-100 dark:border-emerald-800 px-1.5 py-0.5 rounded-sm w-fit">
                                            <Database className="w-3 h-3" />
                                            Materializada · {buildScheduleLabel(report.materialization?.preset)}
                                        </div>
                                        <div className="mt-1 text-[10px] text-slate-400">
                                            {report.materialization?.last_status === 'building'
                                                ? 'Construindo…'
                                                : report.materialization?.last_status === 'refreshing'
                                                    ? 'Atualizando…'
                                                    : report.materialization?.last_status === 'error'
                                                        ? <span className="text-red-500" title={report.materialization?.last_error || ''}>Falha no refresh</span>
                                                        : report.materialization?.last_refreshed_at
                                                            ? `Atualizada em ${formatTimestamp(report.materialization.last_refreshed_at)}`
                                                            : 'Aguardando 1ª carga'}
                                        </div>
                                    </div>
                                )}
                                <div className="mt-2 flex items-center gap-2 text-xs text-slate-400">
                                    <span>{new Date(report.created_at).toLocaleDateString()}</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                <div
                    onMouseDown={startResizing}
                    className="hidden lg:flex w-6 shrink-0 cursor-col-resize items-stretch justify-center group"
                    title="Redimensionar lista de views"
                >
                    <div className="my-2 w-1 rounded-full bg-transparent group-hover:bg-violet-400/70 transition-colors" />
                </div>

                {/* Report Results */}
                <div className="min-w-0 flex-1 bg-white dark:bg-slate-800 rounded-lg shadow-md overflow-hidden flex flex-col transition-colors duration-200">
                    {activeReport ? (
                        <>
                            <div className="p-4 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-700/50 flex justify-between items-center">
                                <div>
                                    <h3 className="font-bold text-lg text-slate-800 dark:text-slate-200">{activeReport.name}</h3>
                                    <code className="text-xs text-slate-500 dark:text-slate-400 font-mono mt-1 block bg-slate-100 dark:bg-slate-900 p-1 rounded-sm max-w-2xl truncate">
                                        {activeReport.sql_query}
                                    </code>
                                </div>
                                <button
                                    onClick={() => handleExecute(activeReport)}
                                    disabled={executingId === activeReport.id}
                                    className="bg-violet-600 text-white px-4 py-2 rounded-md hover:bg-violet-700 disabled:opacity-50 flex items-center gap-2 text-sm"
                                >
                                    {executingId === activeReport.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                                    {results ? 'Run Again' : 'Run'}
                                </button>
                            </div>

                            <div className="flex-1 overflow-auto p-4">
                                {error ? (
                                    <div className="bg-red-50 text-red-700 p-4 rounded-lg flex items-center gap-2">
                                        <AlertCircle className="w-5 h-5" />
                                        {error}
                                    </div>
                                ) : results ? (
                                    <ResultsTable data={results} />
                                ) : executingId === activeReport.id ? (
                                    <div className="h-full flex items-center justify-center text-slate-400">
                                        <Loader2 className="w-8 h-8 animate-spin text-violet-300" />
                                    </div>
                                ) : (
                                    <div className="h-full flex flex-col items-center justify-center text-slate-400 p-8 gap-2">
                                        <Play className="w-12 h-12 opacity-20" />
                                        <p className="text-sm">Clique em <span className="font-semibold text-violet-600 dark:text-violet-400">Run</span> para executar a view.</p>
                                    </div>
                                )}
                            </div>
                        </>
                    ) : (
                        <div className="h-full flex flex-col items-center justify-center text-slate-400 p-8">
                            <FileText className="w-16 h-16 mb-4 opacity-20" />
                            <p className="text-lg">Select a report to view results</p>
                        </div>
                    )}
                </div>
            </div>

            {/* Create Report Modal */}
            {showCreateModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-2xl p-6 max-h-[90vh] overflow-y-auto border dark:border-slate-700">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="text-xl font-bold text-slate-800 dark:text-slate-100">{isEditing ? 'Edit View' : 'Create New View'}</h3>
                            <button onClick={() => setShowCreateModal(false)} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
                                <X className="w-6 h-6" />
                            </button>
                        </div>

                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">View Name</label>
                                <input
                                    type="text"
                                    className="w-full p-2 border rounded-md focus:ring-2 focus:ring-violet-500 bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                    placeholder="e.g., Quarterly Revenue"
                                    value={createForm.name}
                                    onChange={e => setCreateForm({ ...createForm, name: e.target.value })}
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Description</label>
                                <textarea
                                    className="w-full p-2 border rounded-md focus:ring-2 focus:ring-violet-500 bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                    placeholder="Describe the purpose of this report..."
                                    rows={2}
                                    value={createForm.description}
                                    onChange={e => setCreateForm({ ...createForm, description: e.target.value })}
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">SQL Query</label>
                                <div className="relative">
                                    <textarea
                                        className="w-full p-3 border rounded-md font-mono text-sm focus:ring-2 focus:ring-violet-500 h-48 bg-slate-50 dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                        placeholder="SELECT * FROM table_name WHERE..."
                                        value={createForm.sql}
                                        onChange={e => {
                                            setCreateForm({ ...createForm, sql: e.target.value });
                                            setIsVerified(false);
                                            setTestStatus(null);
                                        }}
                                    />
                                    <button
                                        onClick={handleTestQuery}
                                        disabled={!createForm.sql || testing}
                                        className="absolute bottom-3 right-3 bg-slate-800 text-white px-3 py-1.5 rounded-sm text-xs hover:bg-slate-700 disabled:opacity-50 flex items-center gap-1"
                                    >
                                        {testing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                                        Test Query
                                    </button>
                                </div>
                                {managedFunctions.length > 0 && (
                                    <div className="mt-2 flex flex-wrap gap-2">
                                        {managedFunctions.map(fn => (
                                            <button
                                                key={fn.id}
                                                type="button"
                                                onClick={() => insertFunctionCall(fn)}
                                                className="px-2 py-1 text-xs rounded-sm border border-violet-200 dark:border-violet-800 text-violet-700 dark:text-violet-300 bg-violet-50 dark:bg-violet-900/20 hover:bg-violet-100 dark:hover:bg-violet-900/40 font-mono"
                                                title={fn.signature}
                                            >
                                                {fn.function_name}
                                            </button>
                                        ))}
                                    </div>
                                )}
                                <p className="text-xs text-slate-500 mt-1">You must successfully test the query before saving.</p>
                            </div>

                            {testStatus && (
                                <div className={`p-3 rounded-md flex items-center gap-2 text-sm ${testStatus.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                                    }`}>
                                    {testStatus.type === 'success' ? <CheckCircle className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
                                    {testStatus.message}
                                </div>
                            )}

                            <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-slate-200 dark:border-slate-700">
                                <button
                                    onClick={() => setShowCreateModal(false)}
                                    className="px-4 py-2 text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700 rounded-md"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleSaveReport}
                                    disabled={!isVerified || !createForm.name}
                                    className="bg-violet-600 text-white px-6 py-2 rounded-md hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                                >
                                    {isEditing ? 'Update View' : 'Save View'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Schedule / Materialize Modal */}
            {showScheduleModal && scheduleTarget && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
                    <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-md p-6 border dark:border-slate-700">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="text-xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
                                <Database className="w-5 h-5 text-violet-600 dark:text-violet-400" />
                                Materializar view
                            </h3>
                            <button onClick={() => setShowScheduleModal(false)} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
                                <X className="w-6 h-6" />
                            </button>
                        </div>

                        <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
                            "{scheduleTarget.name}" será convertida em uma <span className="font-medium">materialized view</span> e
                            atualizada automaticamente na frequência abaixo. As consultas ficam instantâneas; a 1ª carga roda em segundo plano.
                        </p>

                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Frequência</label>
                                <select
                                    value={schedulePreset.type}
                                    onChange={e => setSchedulePreset({ ...schedulePreset, type: e.target.value })}
                                    className="w-full p-2 border rounded-md focus:ring-2 focus:ring-violet-500 bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                >
                                    <option value="hourly">A cada hora</option>
                                    <option value="every_n_hours">A cada X horas</option>
                                    <option value="every_n_days">A cada X dias</option>
                                    <option value="daily">Diário</option>
                                    <option value="weekly">Semanal</option>
                                    <option value="weekdays">Dias da semana</option>
                                </select>
                            </div>

                            {schedulePreset.type === 'every_n_hours' && (
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">A cada quantas horas</label>
                                    <input
                                        type="number"
                                        min={1}
                                        max={23}
                                        value={schedulePreset.interval}
                                        onChange={e => setSchedulePreset({ ...schedulePreset, interval: Math.min(23, Math.max(1, Number(e.target.value) || 1)) })}
                                        className="w-full p-2 border rounded-md focus:ring-2 focus:ring-violet-500 bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                    />
                                    <p className="text-xs text-slate-500 mt-1">Entre 1 e 23 horas. Roda nos minutos 0 (ex.: a cada 3h → 00:00, 03:00, 06:00…).</p>
                                </div>
                            )}

                            {schedulePreset.type === 'every_n_days' && (
                                <div className="grid grid-cols-2 gap-3">
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">A cada quantos dias</label>
                                        <input
                                            type="number"
                                            min={1}
                                            max={31}
                                            value={schedulePreset.day_interval}
                                            onChange={e => setSchedulePreset({ ...schedulePreset, day_interval: Math.min(31, Math.max(1, Number(e.target.value) || 1)) })}
                                            className="w-full p-2 border rounded-md focus:ring-2 focus:ring-violet-500 bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Vezes ao dia</label>
                                        <input
                                            type="number"
                                            min={1}
                                            max={24}
                                            value={schedulePreset.times_per_day}
                                            onChange={e => setSchedulePreset({ ...schedulePreset, times_per_day: Math.min(24, Math.max(1, Number(e.target.value) || 1)) })}
                                            className="w-full p-2 border rounded-md focus:ring-2 focus:ring-violet-500 bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                        />
                                    </div>
                                    <p className="col-span-2 text-xs text-slate-500 mt-1">As atualizações são distribuídas igualmente nas 24h (ex.: 2x/dia → 00:00 e 12:00).</p>
                                </div>
                            )}

                            {schedulePreset.type === 'weekly' && (
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Dia da semana</label>
                                    <select
                                        value={schedulePreset.weekday}
                                        onChange={e => setSchedulePreset({ ...schedulePreset, weekday: Number(e.target.value) })}
                                        className="w-full p-2 border rounded-md focus:ring-2 focus:ring-violet-500 bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                    >
                                        {WEEKDAY_LABELS.map((label, idx) => (
                                            <option key={idx} value={idx}>{label}</option>
                                        ))}
                                    </select>
                                </div>
                            )}

                            {schedulePreset.type === 'weekdays' && (
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Dias da semana</label>
                                    <div className="flex flex-wrap gap-1.5">
                                        {WEEKDAY_LABELS.map((label, idx) => {
                                            const selected = (schedulePreset.weekdays || []).includes(idx);
                                            return (
                                                <button
                                                    key={idx}
                                                    type="button"
                                                    onClick={() => setSchedulePreset(prev => {
                                                        const set = new Set(prev.weekdays || []);
                                                        set.has(idx) ? set.delete(idx) : set.add(idx);
                                                        return { ...prev, weekdays: [...set].sort((a, b) => a - b) };
                                                    })}
                                                    className={`px-3 py-1.5 text-sm rounded-md border transition-colors ${selected
                                                        ? 'bg-violet-600 text-white border-violet-600'
                                                        : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 border-slate-300 dark:border-slate-600 hover:border-violet-400'}`}
                                                >
                                                    {label}
                                                </button>
                                            );
                                        })}
                                    </div>
                                    {(!schedulePreset.weekdays || schedulePreset.weekdays.length === 0) && (
                                        <p className="text-xs text-red-500 mt-1">Selecione ao menos um dia.</p>
                                    )}
                                </div>
                            )}

                            {(schedulePreset.type === 'daily' || schedulePreset.type === 'weekly' || schedulePreset.type === 'weekdays') && (
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Horário</label>
                                    <input
                                        type="time"
                                        value={schedulePreset.time}
                                        onChange={e => setSchedulePreset({ ...schedulePreset, time: e.target.value })}
                                        className="w-full p-2 border rounded-md focus:ring-2 focus:ring-violet-500 bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                    />
                                </div>
                            )}

                            <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900/50 rounded-md p-2">
                                <CalendarClock className="w-4 h-4 shrink-0" />
                                <span>Atualização: <span className="font-medium text-slate-700 dark:text-slate-300">{buildScheduleLabel(schedulePreset)}</span> (horário de Brasília)</span>
                            </div>

                            <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-slate-200 dark:border-slate-700">
                                <button
                                    onClick={() => setShowScheduleModal(false)}
                                    className="px-4 py-2 text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700 rounded-md"
                                >
                                    Cancelar
                                </button>
                                <button
                                    onClick={handleMaterialize}
                                    disabled={togglingId === scheduleTarget.id || (schedulePreset.type === 'weekdays' && (schedulePreset.weekdays || []).length === 0)}
                                    className="bg-violet-600 text-white px-6 py-2 rounded-md hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                                >
                                    {togglingId === scheduleTarget.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Database className="w-4 h-4" />}
                                    Ativar materialização
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default ReportsPage;
