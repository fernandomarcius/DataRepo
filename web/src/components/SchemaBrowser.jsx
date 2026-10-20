import React, { useState, useRef, useCallback, useMemo } from 'react';
import { ChevronRight, ChevronDown, Table, Columns, Plus, Eye, ArrowUpAZ, ArrowDownAZ, Pencil, Trash2, X, AlertCircle, Loader2, Code, Network, Search } from 'lucide-react';
import api, { getConnectionTables, getConnectionTableSchema } from '../api/client';
import { useAuth } from '../context/AuthContext';

const SchemaBrowser = ({ tables, functions = [], connections = [], onInsert, onPreview, onInsertData, onRefreshTables }) => {
    const { hasPermission } = useAuth();
    const [expandedTables, setExpandedTables] = useState({});
    const [schemas, setSchemas] = useState({});
    const [loadingSchema, setLoadingSchema] = useState({});
    const [expandedConnections, setExpandedConnections] = useState({});
    const [connectionTables, setConnectionTables] = useState({});
    const [loadingConnectionTables, setLoadingConnectionTables] = useState({});
    const [expandedExtTables, setExpandedExtTables] = useState({});
    const [extSchemas, setExtSchemas] = useState({});
    const [loadingExtSchema, setLoadingExtSchema] = useState({});
    const [isOpen, setIsOpen] = useState(false); // Mobile toggle state
    const [isDesktopOpen, setIsDesktopOpen] = useState(true); // Desktop toggle state
    const [sortOrder, setSortOrder] = useState('asc'); // 'asc' or 'desc'
    const [sidebarWidth, setSidebarWidth] = useState(280); // Default width (increased ~25%)
    const [objectModal, setObjectModal] = useState(null); // { type: 'rename' | 'delete', tableName }
    const [renameValue, setRenameValue] = useState('');
    const [modalError, setModalError] = useState(null);
    const [modalSaving, setModalSaving] = useState(false);
    const [searchOpen, setSearchOpen] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const isResizing = useRef(false);
    const sidebarRef = useRef(null);
    const searchInputRef = useRef(null);

    const quoteIdentifier = (value) => `"${String(value).replaceAll('"', '""')}"`;
    const quoteQualifiedIdentifier = (...parts) => parts.map(quoteIdentifier).join('.');

    const connectionTitle = (conn) => {
        const name = conn.display_name || conn.name;
        if (conn.host && conn.port && conn.database) {
            const endpoint = `${conn.host}:${conn.port}/${conn.database}`;
            return conn.schema_name ? `${name} — ${endpoint} (schema local: ${conn.schema_name})` : `${name} — ${endpoint}`;
        }
        return conn.schema_name ? `${name} — schema local: ${conn.schema_name}` : name;
    };

    // Sorted tables based on current sort order
    const sortedTables = useMemo(() => {
        const sorted = [...tables].sort((a, b) =>
            a.toLowerCase().localeCompare(b.toLowerCase())
        );
        return sortOrder === 'desc' ? sorted.reverse() : sorted;
    }, [tables, sortOrder]);

    // Filtered lists based on search term
    const normalizedSearch = searchTerm.trim().toLowerCase();
    const filteredTables = useMemo(() => {
        if (!normalizedSearch) return sortedTables;
        return sortedTables.filter(t => t.toLowerCase().includes(normalizedSearch));
    }, [sortedTables, normalizedSearch]);

    const filteredFunctions = useMemo(() => {
        if (!normalizedSearch) return functions;
        return functions.filter(fn => (fn.function_name || '').toLowerCase().includes(normalizedSearch));
    }, [functions, normalizedSearch]);

    // Toggle sort order
    const toggleSortOrder = () => {
        setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
    };

    const toggleSearch = () => {
        setSearchOpen(prev => {
            if (prev) setSearchTerm('');
            return !prev;
        });
    };

    React.useEffect(() => {
        if (searchOpen) {
            searchInputRef.current?.focus();
        }
    }, [searchOpen]);

    const clearObjectCache = (tableName) => {
        setExpandedTables(prev => {
            const next = { ...prev };
            delete next[tableName];
            return next;
        });
        setSchemas(prev => {
            const next = { ...prev };
            delete next[tableName];
            return next;
        });
    };

    const openRenameModal = (tableName) => {
        setObjectModal({ type: 'rename', tableName });
        setRenameValue(tableName);
        setModalError(null);
    };

    const openDeleteModal = (tableName) => {
        setObjectModal({ type: 'delete', tableName });
        setRenameValue('');
        setModalError(null);
    };

    const closeObjectModal = () => {
        if (modalSaving) return;
        setObjectModal(null);
        setRenameValue('');
        setModalError(null);
    };

    const submitRename = async (e) => {
        e?.preventDefault();
        if (!objectModal) return;
        const newName = renameValue.trim();
        if (!newName) {
            setModalError('Informe um novo nome.');
            return;
        }
        if (newName === objectModal.tableName) {
            closeObjectModal();
            return;
        }

        setModalSaving(true);
        setModalError(null);
        try {
            await api.put(`/tables/${objectModal.tableName}`, { new_name: newName });
            clearObjectCache(objectModal.tableName);
            onRefreshTables?.();
            closeObjectModal();
        } catch (err) {
            setModalError(err.response?.data?.error || 'Falha ao renomear tabela/view');
        } finally {
            setModalSaving(false);
        }
    };

    const submitDelete = async () => {
        if (!objectModal) return;

        setModalSaving(true);
        setModalError(null);
        try {
            await api.delete(`/tables/${objectModal.tableName}`);
            clearObjectCache(objectModal.tableName);
            onRefreshTables?.();
            closeObjectModal();
        } catch (err) {
            setModalError(err.response?.data?.error || 'Falha ao excluir tabela/view');
        } finally {
            setModalSaving(false);
        }
    };

    // Resize handlers
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

    const resize = useCallback((e) => {
        if (!isResizing.current || !sidebarRef.current) return;
        const rect = sidebarRef.current.getBoundingClientRect();
        const newWidth = Math.min(500, Math.max(180, e.clientX - rect.left));
        setSidebarWidth(newWidth);
    }, []);

    // Add/remove mouse event listeners for resize
    React.useEffect(() => {
        window.addEventListener('mousemove', resize);
        window.addEventListener('mouseup', stopResizing);
        return () => {
            window.removeEventListener('mousemove', resize);
            window.removeEventListener('mouseup', stopResizing);
        };
    }, [resize, stopResizing]);

    const toggleConnection = async (conn) => {
        const id = conn.id;
        setExpandedConnections(prev => ({ ...prev, [id]: !prev[id] }));
        if (!connectionTables[id] && !loadingConnectionTables[id]) {
            setLoadingConnectionTables(prev => ({ ...prev, [id]: true }));
            try {
                const res = await getConnectionTables(id);
                setConnectionTables(prev => ({ ...prev, [id]: res.data.tables || [] }));
            } catch (err) {
                console.error(`Failed to fetch tables for connection ${id}`, err);
                setConnectionTables(prev => ({ ...prev, [id]: [] }));
            } finally {
                setLoadingConnectionTables(prev => ({ ...prev, [id]: false }));
            }
        }
    };

    const toggleExternalTable = async (conn, tableName) => {
        const key = `${conn.id}:${tableName}`;
        setExpandedExtTables(prev => ({ ...prev, [key]: !prev[key] }));
        if (!extSchemas[key] && !loadingExtSchema[key]) {
            setLoadingExtSchema(prev => ({ ...prev, [key]: true }));
            try {
                const res = await getConnectionTableSchema(conn.id, tableName);
                setExtSchemas(prev => ({ ...prev, [key]: res.data.schema || [] }));
            } catch (err) {
                console.error(`Failed to fetch schema for ${conn.name}.${tableName}`, err);
            } finally {
                setLoadingExtSchema(prev => ({ ...prev, [key]: false }));
            }
        }
    };

    const toggleTable = async (tableName) => {
        setExpandedTables(prev => ({
            ...prev,
            [tableName]: !prev[tableName]
        }));

        if (!schemas[tableName] && !loadingSchema[tableName]) {
            setLoadingSchema(prev => ({ ...prev, [tableName]: true }));
            try {
                const res = await api.get(`/tables/${tableName}/schema`);
                setSchemas(prev => ({ ...prev, [tableName]: res.data.schema }));
            } catch (err) {
                console.error(`Failed to fetch schema for ${tableName}`, err);
            } finally {
                setLoadingSchema(prev => ({ ...prev, [tableName]: false }));
            }
        }
    };

    return (
        <>
            {/* Mobile Toggle Button */}
            <button
                className="md:hidden fixed bottom-4 right-4 z-50 bg-violet-600 text-white p-3 rounded-full shadow-lg"
                onClick={() => setIsOpen(!isOpen)}
            >
                <Table className="w-6 h-6" />
            </button>

            {/* Desktop Toggle Button (Floating when closed) */}
            {!isDesktopOpen && (
                <div className="hidden md:block fixed left-0 top-24 z-30 group">
                    <button
                        onClick={() => setIsDesktopOpen(true)}
                        className="bg-white dark:bg-slate-800 border border-l-0 border-slate-200 dark:border-slate-700 p-3 rounded-r-lg shadow-md text-slate-500 dark:text-slate-400 hover:text-violet-600 dark:hover:text-violet-400 hover:bg-slate-50 dark:hover:bg-slate-700 transition-all transform hover:translate-x-1"
                        title="Open Sidebar"
                    >
                        <ChevronRight className="w-5 h-5" />
                    </button>
                    <div className="absolute left-full top-1/2 -translate-y-1/2 ml-2 px-2 py-1 bg-slate-800 text-white text-xs rounded-sm opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none">
                        Open Schema
                    </div>
                </div>
            )}

            {/* Sidebar Container */}
            <div
                ref={sidebarRef}
                className={`
                    bg-slate-50 dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 shrink-0 flex flex-col h-screen sticky top-0
                    fixed md:sticky inset-y-0 left-0 z-40 transform transition-transform duration-300 ease-in-out relative
                    ${isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
                    ${isDesktopOpen ? '' : 'md:w-0! md:border-r-0 md:overflow-hidden'}
                `}
                style={{ width: isDesktopOpen ? `${sidebarWidth}px` : undefined }}
            >
                <div className="p-3 border-b border-slate-200 dark:border-slate-800 bg-slate-100 dark:bg-slate-800/50 whitespace-nowrap overflow-hidden">
                    <div className="flex justify-between items-center">
                        <h3 className="font-semibold text-slate-700 dark:text-slate-200 flex items-center gap-2">
                            <Table className="w-4 h-4" /> Catálogo
                        </h3>
                        <div className="flex items-center gap-1">
                            {/* Sort Order Toggle Button */}
                            <button
                                onClick={toggleSortOrder}
                                className="p-1 text-slate-400 dark:text-slate-500 hover:text-violet-600 dark:hover:text-violet-400 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-sm transition-colors"
                                title={sortOrder === 'asc' ? 'Ordenar Z-A' : 'Ordenar A-Z'}
                            >
                                {sortOrder === 'asc' ? (
                                    <ArrowUpAZ className="w-4 h-4" />
                                ) : (
                                    <ArrowDownAZ className="w-4 h-4" />
                                )}
                            </button>
                            {/* Search Toggle Button */}
                            <button
                                onClick={toggleSearch}
                                className={`p-1 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-sm transition-colors ${searchOpen ? 'text-violet-600 dark:text-violet-400' : 'text-slate-400 dark:text-slate-500 hover:text-violet-600 dark:hover:text-violet-400'}`}
                                title={searchOpen ? 'Fechar pesquisa' : 'Pesquisar'}
                            >
                                <Search className="w-4 h-4" />
                            </button>
                            <button className="md:hidden text-slate-500 dark:text-slate-400" onClick={() => setIsOpen(false)}>
                                <ChevronRight className="w-5 h-5 rotate-180" />
                            </button>
                            <button
                                className="hidden md:block text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300"
                                onClick={() => setIsDesktopOpen(false)}
                                title="Recolher Menu"
                            >
                                <ChevronRight className="w-4 h-4 rotate-180" />
                            </button>
                        </div>
                    </div>
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
                <div className={`overflow-y-auto overscroll-contain min-h-0 flex-1 p-2 mr-2 ${!isDesktopOpen ? 'hidden' : ''}`}>
                    {filteredFunctions.length > 0 && (
                        <div className="mb-3 border-b border-slate-200 dark:border-slate-800 pb-3">
                            <div className="px-1.5 py-1 text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 flex items-center gap-1">
                                <Code className="w-3 h-3" /> Funções
                            </div>
                            <ul className="space-y-1 mt-1">
                                {filteredFunctions.map(fn => (
                                    <li key={fn.id} className="group">
                                        <div className="flex items-center gap-1">
                                            <button
                                                onClick={() => onInsert(fn.call_example || fn.function_name)}
                                                className="text-sm font-medium text-slate-700 dark:text-slate-300 flex-1 cursor-pointer hover:text-violet-600 dark:hover:text-violet-400 truncate text-left"
                                                title={fn.signature}
                                            >
                                                {fn.function_name}
                                            </button>
                                            <button
                                                onClick={() => onInsert(fn.call_example || fn.function_name)}
                                                className="p-1 hover:bg-violet-100 text-violet-600 rounded-sm hidden group-hover:block"
                                                title="Inserir chamada"
                                            >
                                                <Code className="w-3 h-3" />
                                            </button>
                                        </div>
                                        <div className="ml-1 text-[10px] text-slate-400 truncate font-mono" title={fn.signature}>
                                            {fn.kind === 'table' ? 'TABLE' : fn.return_type}
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                    {connections.length > 0 && (
                        <div className="mb-3 border-b border-slate-200 dark:border-slate-800 pb-3">
                            <div className="px-1.5 py-1 text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 flex items-center gap-1">
                                <Network className="w-3 h-3" /> Conexões Externas
                            </div>
                            <ul className="space-y-1 mt-1">
                                {connections.map(conn => (
                                    <li key={conn.id} className="select-none">
                                        <div className="flex items-center gap-1 group">
                                            <button
                                                onClick={() => toggleConnection(conn)}
                                                className="p-1 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-sm text-slate-500 dark:text-slate-400"
                                            >
                                                {expandedConnections[conn.id] ? (
                                                    <ChevronDown className="w-4 h-4" />
                                                ) : (
                                                    <ChevronRight className="w-4 h-4" />
                                                )}
                                            </button>
                                            <span
                                                className="text-sm font-medium text-slate-700 dark:text-slate-300 flex-1 cursor-pointer hover:text-violet-600 dark:hover:text-violet-400 truncate"
                                                title={connectionTitle(conn)}
                                                onClick={() => onInsert(conn.schema_name)}
                                            >
                                                {conn.display_name || conn.name}
                                            </span>
                                            <span className="text-[10px] uppercase text-slate-400 mr-1">
                                                {conn.db_type === 'sqlserver' ? 'MSSQL' : 'PG'}
                                            </span>
                                        </div>

                                        {expandedConnections[conn.id] && (
                                            <div className="ml-6 mt-1 border-l-2 border-slate-200 dark:border-slate-700 pl-2">
                                                {loadingConnectionTables[conn.id] ? (
                                                    <div className="text-xs text-slate-400 py-1">Carregando tabelas remotas...</div>
                                                ) : (connectionTables[conn.id] || []).length === 0 ? (
                                                    <div className="text-xs text-slate-400 italic py-1">Nenhuma foreign table importada.</div>
                                                ) : (
                                                    <ul className="space-y-1">
                                                        {(connectionTables[conn.id] || []).map(extTable => {
                                                            const key = `${conn.id}:${extTable}`;
                                                            const qualified = quoteQualifiedIdentifier(conn.schema_name, extTable);
                                                            return (
                                                                <li key={key} className="select-none">
                                                                    <div className="flex items-center gap-1 group">
                                                                        <button
                                                                            onClick={() => toggleExternalTable(conn, extTable)}
                                                                            className="p-1 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-sm text-slate-500 dark:text-slate-400"
                                                                        >
                                                                            {expandedExtTables[key] ? (
                                                                                <ChevronDown className="w-3 h-3" />
                                                                            ) : (
                                                                                <ChevronRight className="w-3 h-3" />
                                                                            )}
                                                                        </button>
                                                                        <span
                                                                            className="text-xs text-slate-600 dark:text-slate-300 flex-1 cursor-pointer hover:text-violet-600 dark:hover:text-violet-400 truncate font-mono"
                                                                            title={qualified}
                                                                            onClick={() => onInsert(qualified)}
                                                                        >
                                                                            {extTable}
                                                                        </span>
                                                                        <button
                                                                            onClick={() => onPreview(qualified)}
                                                                            className="p-0.5 hover:bg-violet-100 text-violet-600 rounded-sm opacity-0 group-hover:opacity-100"
                                                                            title="Visualizar (Limite 200)"
                                                                        >
                                                                            <Eye className="w-3 h-3" />
                                                                        </button>
                                                                    </div>
                                                                    {expandedExtTables[key] && (
                                                                        <div className="ml-5 mt-1 border-l-2 border-slate-200 dark:border-slate-700 pl-2">
                                                                            {loadingExtSchema[key] ? (
                                                                                <div className="text-xs text-slate-400 py-1">Loading...</div>
                                                                            ) : extSchemas[key] ? (
                                                                                <ul className="space-y-1">
                                                                                    {extSchemas[key].map(col => (
                                                                                        <li key={col.column_name} className="flex items-center justify-between">
                                                                                            <div className="flex items-center gap-2 overflow-hidden">
                                                                                                <Columns className="w-3 h-3 text-slate-400 shrink-0" />
                                                                                                <span
                                                                                                    className="text-xs text-slate-600 dark:text-slate-400 cursor-pointer hover:text-violet-600 dark:hover:text-violet-400 truncate"
                                                                                                    title={`${col.column_name} (${col.data_type})`}
                                                                                                    onClick={() => onInsert(quoteIdentifier(col.column_name))}
                                                                                                >
                                                                                                    {col.column_name}
                                                                                                </span>
                                                                                            </div>
                                                                                            <span className="text-[10px] text-slate-400 ml-2 shrink-0">
                                                                                                {col.data_type}
                                                                                            </span>
                                                                                        </li>
                                                                                    ))}
                                                                                </ul>
                                                                            ) : (
                                                                                <div className="text-xs text-red-400">Failed to load</div>
                                                                            )}
                                                                        </div>
                                                                    )}
                                                                </li>
                                                            );
                                                        })}
                                                    </ul>
                                                )}
                                            </div>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                    {filteredTables.length === 0 ? (
                        <div className="text-sm text-slate-400 p-2 text-center">
                            {normalizedSearch ? 'Nenhum resultado' : 'Nenhuma tabela encontrada'}
                        </div>
                    ) : (
                        <ul className="space-y-1">
                            {filteredTables.map(table => (
                                <li key={table} className="select-none">
                                    <div className="flex items-center gap-1 group">
                                        <button
                                            onClick={() => toggleTable(table)}
                                            className="p-1 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-sm text-slate-500 dark:text-slate-400"
                                        >
                                            {expandedTables[table] ? (
                                                <ChevronDown className="w-4 h-4" />
                                            ) : (
                                                <ChevronRight className="w-4 h-4" />
                                            )}
                                        </button>
                                        <span
                                            className="text-sm font-medium text-slate-700 dark:text-slate-300 flex-1 cursor-pointer hover:text-violet-600 dark:hover:text-violet-400 truncate"
                                            title={table}
                                            onClick={() => onInsert(table)}
                                        >
                                            {table}
                                        </span>
                                        <div className="hidden group-hover:flex">
                                            <button
                                                onClick={() => onPreview(table)}
                                                className="p-1 hover:bg-violet-100 text-violet-600 rounded-sm mr-1"
                                                title="Visualizar (Limite 200)"
                                            >
                                                <Eye className="w-3 h-3" />
                                            </button>
                                            {hasPermission('can_upload') && (
                                                <button
                                                    onClick={() => onInsertData(table)}
                                                    className="p-1 hover:bg-violet-100 text-violet-600 rounded-sm mr-1"
                                                    title="Inserir Dados"
                                                >
                                                    <Plus className="w-3 h-3" />
                                                </button>
                                            )}
                                            {hasPermission('can_manage_views') && (
                                                <>
                                                    <button
                                                        onClick={() => openRenameModal(table)}
                                                        className="p-1 hover:bg-blue-100 text-blue-600 rounded-sm mr-1"
                                                        title="Renomear tabela/view"
                                                    >
                                                        <Pencil className="w-3 h-3" />
                                                    </button>
                                                    <button
                                                        onClick={() => openDeleteModal(table)}
                                                        className="p-1 hover:bg-red-100 text-red-600 rounded-sm mr-1"
                                                        title="Excluir tabela/view"
                                                    >
                                                        <Trash2 className="w-3 h-3" />
                                                    </button>
                                                </>
                                            )}
                                            <button
                                                onClick={() => onInsert(table)}
                                                className="p-1 hover:bg-violet-100 text-violet-600 rounded-sm"
                                                title="Inserir nome da tabela"
                                            >
                                                <Table className="w-3 h-3" />
                                            </button>
                                        </div>
                                    </div>

                                    {expandedTables[table] && (
                                        <div className="ml-6 mt-1 border-l-2 border-slate-200 pl-2">
                                            {loadingSchema[table] ? (
                                                <div className="text-xs text-slate-400 py-1">Loading columns...</div>
                                            ) : schemas[table] ? (
                                                <ul className="space-y-1">
                                                    {schemas[table].map(col => (
                                                        <li key={col.column_name} className="flex items-center justify-between group/col">
                                                            <div className="flex items-center gap-2 overflow-hidden">
                                                                <Columns className="w-3 h-3 text-slate-400 shrink-0" />
                                                                <span
                                                                    className="text-xs text-slate-600 dark:text-slate-400 cursor-pointer hover:text-violet-600 dark:hover:text-violet-400 truncate"
                                                                    title={`${col.column_name} (${col.data_type})`}
                                                                    onClick={() => onInsert(col.column_name)}
                                                                >
                                                                    {col.column_name}
                                                                </span>
                                                            </div>
                                                            <span className="text-[10px] text-slate-400 ml-2 shrink-0">
                                                                {col.data_type}
                                                            </span>
                                                        </li>
                                                    ))}
                                                </ul>
                                            ) : (
                                                <div className="text-xs text-red-400">Failed to load</div>
                                            )}
                                        </div>
                                    )}
                                </li>
                            ))}
                        </ul>
                    )}
                </div>

                {/* Resize Handle */}
                {isDesktopOpen && (
                    <div
                        onMouseDown={startResizing}
                        className="hidden md:flex absolute top-0 right-0 w-2 h-full cursor-col-resize bg-slate-600/30 hover:bg-violet-500/70 transition-colors z-50 items-center justify-center group"
                        style={{ touchAction: 'none' }}
                    >
                        {/* Visual indicator lines */}
                        <div className="flex flex-col gap-0.5 opacity-50 group-hover:opacity-100">
                            <div className="w-0.5 h-4 bg-slate-400 rounded-full"></div>
                        </div>
                    </div>
                )}
            </div>

            {/* Overlay for mobile */}
            {isOpen && (
                <div
                    className="fixed inset-0 bg-black bg-opacity-50 z-30 md:hidden"
                    onClick={() => setIsOpen(false)}
                />
            )}

            {objectModal && (
                <div
                    className="fixed inset-0 bg-black/50 flex items-center justify-center z-70 p-4"
                    onClick={(e) => e.target === e.currentTarget && closeObjectModal()}
                >
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="object-modal-title"
                        className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-md border border-slate-200 dark:border-slate-700"
                    >
                        <div className="flex items-center justify-between p-5 border-b border-slate-200 dark:border-slate-700">
                            <h3 id="object-modal-title" className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                                {objectModal.type === 'rename' ? 'Renomear tabela/view' : 'Excluir tabela/view'}
                            </h3>
                            <button
                                onClick={closeObjectModal}
                                disabled={modalSaving}
                                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 disabled:opacity-50"
                                title="Fechar"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        {objectModal.type === 'rename' ? (
                            <form onSubmit={submitRename} className="p-5 space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                                        Novo nome
                                    </label>
                                    <input
                                        autoFocus
                                        type="text"
                                        value={renameValue}
                                        onChange={(e) => setRenameValue(e.target.value)}
                                        disabled={modalSaving}
                                        className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-violet-500"
                                    />
                                </div>

                                {modalError && (
                                    <div className="p-3 rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm flex items-start gap-2">
                                        <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                                        <span>{modalError}</span>
                                    </div>
                                )}

                                <div className="flex justify-end gap-3 pt-2">
                                    <button
                                        type="button"
                                        onClick={closeObjectModal}
                                        disabled={modalSaving}
                                        className="px-4 py-2 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700 rounded-md disabled:opacity-50"
                                    >
                                        Cancelar
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={modalSaving || !renameValue.trim()}
                                        className="bg-violet-600 text-white px-4 py-2 rounded-md hover:bg-violet-700 disabled:opacity-50 flex items-center gap-2"
                                    >
                                        {modalSaving && <Loader2 className="w-4 h-4 animate-spin" />}
                                        Renomear
                                    </button>
                                </div>
                            </form>
                        ) : (
                            <div className="p-5 space-y-4">
                                <p className="text-sm text-slate-600 dark:text-slate-300">
                                    Excluir <span className="font-mono font-semibold text-slate-900 dark:text-slate-100">{objectModal.tableName}</span>?
                                </p>

                                {modalError && (
                                    <div className="p-3 rounded-md bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm flex items-start gap-2">
                                        <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                                        <span>{modalError}</span>
                                    </div>
                                )}

                                <div className="flex justify-end gap-3 pt-2">
                                    <button
                                        type="button"
                                        onClick={closeObjectModal}
                                        disabled={modalSaving}
                                        className="px-4 py-2 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700 rounded-md disabled:opacity-50"
                                    >
                                        Cancelar
                                    </button>
                                    <button
                                        type="button"
                                        onClick={submitDelete}
                                        disabled={modalSaving}
                                        className="bg-red-600 text-white px-4 py-2 rounded-md hover:bg-red-700 disabled:opacity-50 flex items-center gap-2"
                                    >
                                        {modalSaving && <Loader2 className="w-4 h-4 animate-spin" />}
                                        Excluir
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </>
    );
};

export default SchemaBrowser;
