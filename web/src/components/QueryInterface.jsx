import React, { useState, useEffect, useRef } from 'react';
import { Code, Play, Layout, Loader2 } from 'lucide-react';
import ResultsTable from './ResultsTable';
import SchemaBrowser from './SchemaBrowser';
import VisualQueryBuilder from './VisualQueryBuilder';
import DataEntryForm from './DataEntryForm';
import api from '../api/client';
import { useAuth } from '../context/AuthContext';

const QueryInterface = () => {
    const { hasPermission } = useAuth();
    const [mode, setMode] = useState('sql'); // 'sql' | 'visual'
    const [query, setQuery] = useState('');
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [tables, setTables] = useState([]);
    const [managedFunctions, setManagedFunctions] = useState([]);
    const [connections, setConnections] = useState([]);

    // Data Entry State
    const [showDataEntry, setShowDataEntry] = useState(false);
    const [dataEntryTable, setDataEntryTable] = useState(null);

    // Report Saving State
    const [showSaveReport, setShowSaveReport] = useState(false);
    const [reportForm, setReportForm] = useState({ name: '', description: '' });

    const handleSaveReport = async () => {
        try {
            await api.post('/reports', {
                name: reportForm.name,
                description: reportForm.description,
                sql_query: query
            });
            setShowSaveReport(false);
            setReportForm({ name: '', description: '' });
            alert('Report saved successfully!');
        } catch (err) {
            alert('Failed to save report');
        }
    };

    const textareaRef = useRef(null);

    useEffect(() => {
        fetchTables();
        fetchFunctions();
        fetchConnections();
    }, []);

    const fetchTables = async () => {
        try {
            const res = await api.get('/tables');
            setTables(res.data.tables);
        } catch (err) {
            console.error("Failed to fetch tables", err);
        }
    };

    const fetchFunctions = async () => {
        try {
            const res = await api.get('/functions');
            setManagedFunctions(res.data.functions || []);
        } catch (err) {
            console.error("Failed to fetch functions", err);
        }
    };

    const fetchConnections = async () => {
        try {
            const res = await api.get('/connections');
            setConnections(res.data.connections || []);
        } catch (err) {
            console.error("Failed to fetch connections", err);
        }
    };

    const handleInsert = (text) => {
        if (mode === 'visual') return;

        const textarea = textareaRef.current;
        if (!textarea) return;

        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const currentText = query;
        const newText = currentText.substring(0, start) + text + currentText.substring(end);

        setQuery(newText);

        // Restore focus and move cursor
        setTimeout(() => {
            textarea.focus();
            textarea.setSelectionRange(start + text.length, start + text.length);
        }, 0);
    };

    const [limit, setLimit] = useState(200);

    // ... (keep existing state)

    // ...

    const handleRun = async (sqlOverride) => {
        let sqlToRun = typeof sqlOverride === 'string' ? sqlOverride : query;

        // Append limit if not present and not infinite
        if (limit !== 'ALL' && !/LIMIT\s+\d+/i.test(sqlToRun)) {
            // Remove trailing semicolon if exists
            sqlToRun = sqlToRun.trim().replace(/;$/, '');
            sqlToRun += ` LIMIT ${limit}`;
        }

        setLoading(true);
        setError(null);
        setResults([]);

        try {
            const res = await api.post('/query', { sql: sqlToRun });
            setResults(res.data.results);
        } catch (err) {
            setError(err.response?.data?.error || 'Query failed');
        } finally {
            setLoading(false);
        }
    };

    const handlePreview = async (tableName) => {
        // Sem ORDER BY o Postgres nao garante a ordem das linhas, e o LIMIT que
        // handleRun anexa muda ate quais linhas voltam. Ordena pela ordem
        // original do arquivo sempre que a tabela tiver a coluna.
        let sql = `SELECT * FROM ${tableName}`;
        try {
            const schemaRes = await api.get(`/tables/${tableName}/schema`);
            const hasRowOrder = (schemaRes.data.schema || []).some(
                col => col.column_name === 'ordem_arquivo'
            );
            if (hasRowOrder) {
                sql += ' ORDER BY ordem_arquivo';
            }
        } catch (err) {
            // Sem schema disponivel, mantem o preview sem ordenacao explicita
        }

        setQuery(sql);
        setMode('sql');

        // Trigger run immediately
        handleRun(sql);
    };

    const handleOpenDataEntry = (tableName) => {
        setDataEntryTable(tableName);
        setShowDataEntry(true);
    };

    const handleDataEntrySuccess = () => {
        // Refresh preview if we are looking at that table
        if (mode === 'sql' && query.includes(dataEntryTable)) {
            handleRun();
        }
    };

    return (
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-md overflow-hidden flex flex-col md:flex-row min-h-[600px] relative transition-colors duration-200">
            {/* Sidebar always visible */}
            <SchemaBrowser
                tables={tables}
                functions={managedFunctions}
                connections={connections}
                onInsert={handleInsert}
                onPreview={handlePreview}
                onInsertData={handleOpenDataEntry}
                onRefreshTables={fetchTables}
            />

            <div className="flex-1 p-4 flex flex-col min-w-0">
                <div className="flex gap-4 mb-4 border-b border-slate-200 dark:border-slate-700 pb-2">
                    <button
                        onClick={() => setMode('sql')}
                        className={`flex items-center gap-2 px-4 py-2 rounded-md transition-colors ${mode === 'sql'
                            ? 'bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 font-medium'
                            : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                            }`}
                    >
                        <Code className="w-4 h-4" /> Editor SQL
                    </button>
                    <button
                        onClick={() => setMode('visual')}
                        className={`flex items-center gap-2 px-4 py-2 rounded-md transition-colors ${mode === 'visual'
                            ? 'bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 font-medium'
                            : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                            }`}
                    >
                        <Layout className="w-4 h-4" /> Construtor Visual
                    </button>
                </div>

                <div className={`mb-4 flex flex-col ${mode === 'visual' ? 'flex-1' : ''}`}>
                    {mode === 'visual' ? (
                        <VisualQueryBuilder
                            tables={tables}
                            onRun={(sql) => {
                                setQuery(sql);
                                handleRun(sql);
                            }}
                            limit={limit}
                            setLimit={setLimit}
                        />
                    ) : (
                        <div className="flex-1 flex flex-col">
                            <div className="text-xs text-slate-500 dark:text-slate-400 mb-2 flex justify-between">
                                <span>Escreva sua consulta SQL abaixo. Clique nos itens da barra lateral para inserir.</span>
                            </div>
                            <textarea
                                ref={textareaRef}
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                placeholder="SELECT * FROM nome_tabela..."
                                className="w-full p-3 border rounded-md font-mono text-sm bg-slate-50 dark:bg-slate-900 border-slate-300 dark:border-slate-700 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-violet-500 h-64 resize-y"
                            />
                        </div>
                    )}
                </div>

                {mode !== 'visual' && (
                    <div className="flex justify-end items-center mb-6 gap-4">
                        <div className="flex items-center gap-2">
                            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Limite:</label>
                            <select
                                value={limit}
                                onChange={(e) => setLimit(e.target.value === 'ALL' ? 'ALL' : Number(e.target.value))}
                                className="p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700 text-slate-900 dark:text-slate-100 text-sm focus:ring-2 focus:ring-violet-500"
                            >
                                <option value={10}>10</option>
                                <option value={50}>50</option>
                                <option value={100}>100</option>
                                <option value={200}>200</option>
                                <option value={500}>500</option>
                                <option value={1000}>1000</option>
                                <option value="ALL">Infinito</option>
                            </select>
                        </div>
                        {hasPermission('can_manage_views') && (
                            <button
                                onClick={() => setShowSaveReport(true)}
                                disabled={!query}
                                className="text-violet-600 bg-violet-50 px-4 py-2 rounded-md hover:bg-violet-100 disabled:opacity-50 font-medium"
                            >
                                Salvar como Relatório
                            </button>
                        )}
                        <button
                            onClick={() => handleRun()}
                            disabled={loading || !query}
                            className="bg-violet-600 text-white px-6 py-2 rounded-md hover:bg-violet-700 disabled:opacity-50 flex items-center gap-2"
                        >
                            {loading ? 'Executando...' : <><Play className="w-4 h-4" /> Executar Consulta</>}
                        </button>
                    </div>
                )}

                {error && (
                    <div className="bg-red-50 text-red-700 p-4 rounded-md mb-6">
                        Error: {error}
                    </div>
                )}

                <div className="flex-1 overflow-auto">
                    <ResultsTable data={results} />
                </div>

                {/* Loading Overlay */}
                {loading && (
                    <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center z-40 rounded-lg">
                        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl p-8 flex flex-col items-center gap-4 border border-slate-200 dark:border-slate-700">
                            <Loader2 className="w-12 h-12 text-violet-600 animate-spin" />
                            <div className="text-center">
                                <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                                    Executando Consulta...
                                </h3>
                                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                                    A consulta está sendo processada. Por favor, aguarde.
                                </p>
                            </div>
                            <div className="flex items-center gap-2 text-xs text-slate-400">
                                <div className="w-2 h-2 bg-violet-500 rounded-full animate-pulse"></div>
                                Processando dados...
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* Data Entry Modal */}
            {showDataEntry && (
                <DataEntryForm
                    tableName={dataEntryTable}
                    onClose={() => setShowDataEntry(false)}
                    onSuccess={handleDataEntrySuccess}
                />
            )}

            {/* Save Report Modal */}
            {showSaveReport && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-md p-6 border dark:border-slate-700">
                        <h3 className="text-lg font-bold mb-4 text-slate-900 dark:text-slate-100">Save Query as Report</h3>
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Report Name</label>
                                <input
                                    type="text"
                                    className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                    placeholder="e.g., Monthly Sales"
                                    value={reportForm.name}
                                    onChange={e => setReportForm({ ...reportForm, name: e.target.value })}
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Description (Optional)</label>
                                <textarea
                                    className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                    placeholder="What does this report show?"
                                    value={reportForm.description}
                                    onChange={e => setReportForm({ ...reportForm, description: e.target.value })}
                                />
                            </div>
                            <div className="flex justify-end gap-3 mt-6">
                                <button
                                    onClick={() => setShowSaveReport(false)}
                                    className="px-4 py-2 text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-700 rounded-md"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleSaveReport}
                                    disabled={!reportForm.name}
                                    className="bg-violet-600 text-white px-4 py-2 rounded-md hover:bg-violet-700 disabled:opacity-50"
                                >
                                    Save Report
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default QueryInterface;
