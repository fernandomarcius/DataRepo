import React, { useState, useEffect } from 'react';
import { X, Upload, Loader2, CheckCircle, AlertCircle } from 'lucide-react';
import api from '../api/client';
import UploadProgressOverlay from './UploadProgressOverlay';
import ColumnRenameModal from './ColumnRenameModal';

const GENERIC_COL_RE = /^Unnamed: \d+$/;
// Colunas geradas pelo sistema — nao entram na deteccao de formato do cabecalho.
const SYSTEM_COLS = ['data_registro_sistema', 'ordem_arquivo'];

const DataEntryForm = ({ tableName, onClose, onSuccess }) => {
    const [file, setFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [successMsg, setSuccessMsg] = useState(null);
    const [uploadPercent, setUploadPercent] = useState(0);
    const [isProcessing, setIsProcessing] = useState(false);
    const [startTime, setStartTime] = useState(null);
    const [headerMode, setHeaderMode] = useState('generic');
    const [tableShape, setTableShape] = useState(null); // 'generic' | 'semantic' | null
    const [oversizedCols, setOversizedCols] = useState(null);
    const [inspecting, setInspecting] = useState(false);

    useEffect(() => {
        let cancelled = false;
        api.get(`/tables/${tableName}/schema`)
            .then((res) => {
                if (cancelled) return;
                const cols = (res.data?.schema || [])
                    .map((c) => c.column_name)
                    .filter((c) => !SYSTEM_COLS.includes(c));
                if (cols.length === 0) {
                    setTableShape(null);
                    return;
                }
                const allGeneric = cols.every((c) => GENERIC_COL_RE.test(c));
                const shape = allGeneric ? 'generic' : 'semantic';
                setTableShape(shape);
                setHeaderMode(shape === 'generic' ? 'generic' : 'first_row');
            })
            .catch(() => {
                if (!cancelled) setTableShape(null);
            });
        return () => { cancelled = true; };
    }, [tableName]);

    const handleFileChange = (e) => {
        setFile(e.target.files[0]);
        setError(null);
        setSuccessMsg(null);
    };

    const doAppend = async (columnRenames) => {
        setLoading(true);
        setOversizedCols(null);
        setError(null);
        setUploadPercent(0);
        setIsProcessing(false);
        setStartTime(Date.now());

        const formData = new FormData();
        formData.append('file', file);
        formData.append('header_mode', headerMode);
        if (columnRenames && Object.keys(columnRenames).length > 0) {
            formData.append('column_renames', JSON.stringify(columnRenames));
        }

        try {
            const res = await api.post(`/tables/${tableName}/data`, formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
                onUploadProgress: (e) => {
                    if (!e.total) return;
                    const pct = Math.round((e.loaded * 100) / e.total);
                    setUploadPercent(pct);
                    if (pct >= 100) setIsProcessing(true);
                },
            });
            setSuccessMsg(`Dados inseridos com sucesso! ${res.data.rows} linhas adicionadas.`);
            setTimeout(() => {
                onSuccess();
                onClose();
            }, 2000);
        } catch (err) {
            setError(err.response?.data?.error || "Falha ao inserir dados.");
        } finally {
            setLoading(false);
            setIsProcessing(false);
            setUploadPercent(0);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!file) {
            setError("Por favor, selecione um arquivo.");
            return;
        }

        setInspecting(true);
        setError(null);

        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('header_mode', headerMode);
            formData.append('table_name', tableName);
            const res = await api.post('/inspect-headers', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            const oversized = res.data?.oversized || [];
            if (oversized.length === 0) {
                await doAppend({});
            } else {
                setOversizedCols(oversized);
            }
        } catch (err) {
            setError(err.response?.data?.error || "Falha ao inspecionar o arquivo.");
        } finally {
            setInspecting(false);
        }
    };

    const genericDisabled = tableShape === 'semantic';
    const firstRowDisabled = tableShape === 'generic';
    const disabledTooltip = (mode) => {
        if (mode === 'generic' && genericDisabled) {
            return 'A tabela tem colunas com nomes semânticos — use "Primeira linha do arquivo é o cabeçalho".';
        }
        if (mode === 'first_row' && firstRowDisabled) {
            return 'A tabela foi criada com cabeçalho genérico — use "Cabeçalho genérico".';
        }
        return '';
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            {loading && file && startTime && (
                <UploadProgressOverlay
                    filename={file.name}
                    uploadPercent={uploadPercent}
                    isProcessing={isProcessing}
                    startTime={startTime}
                />
            )}
            <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-md flex flex-col border dark:border-slate-700">
                <div className="flex justify-between items-center p-4 border-b border-slate-200 dark:border-slate-700">
                    <h3 className="font-semibold text-lg text-slate-800 dark:text-slate-100">Inserir Dados em {tableName}</h3>
                    <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <div className="p-6">
                    {error && (
                        <div className="bg-red-50 text-red-600 p-3 rounded-md mb-4 text-sm flex items-center gap-2">
                            <AlertCircle className="w-4 h-4" />
                            {error}
                        </div>
                    )}
                    {successMsg && (
                        <div className="bg-green-50 text-green-600 p-3 rounded-md mb-4 text-sm flex items-center gap-2">
                            <CheckCircle className="w-4 h-4" />
                            {successMsg}
                        </div>
                    )}

                    <form id="data-entry-form" onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                                Como interpretar o cabeçalho?
                            </label>
                            <div className="space-y-2">
                                <label
                                    title={disabledTooltip('generic')}
                                    className={`flex items-start gap-2 ${genericDisabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
                                >
                                    <input
                                        type="radio"
                                        name="header-mode"
                                        value="generic"
                                        checked={headerMode === 'generic'}
                                        onChange={() => setHeaderMode('generic')}
                                        disabled={genericDisabled}
                                        className="mt-1 text-violet-600 focus:ring-violet-500"
                                    />
                                    <div className="text-sm">
                                        <div className="font-medium text-slate-800 dark:text-slate-200">Cabeçalho genérico (Unnamed: 0, 1, 2…)</div>
                                        <div className="text-xs text-slate-500 dark:text-slate-400">Mantém os dados brutos. Todas as linhas viram dados.</div>
                                    </div>
                                </label>
                                <label
                                    title={disabledTooltip('first_row')}
                                    className={`flex items-start gap-2 ${firstRowDisabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
                                >
                                    <input
                                        type="radio"
                                        name="header-mode"
                                        value="first_row"
                                        checked={headerMode === 'first_row'}
                                        onChange={() => setHeaderMode('first_row')}
                                        disabled={firstRowDisabled}
                                        className="mt-1 text-violet-600 focus:ring-violet-500"
                                    />
                                    <div className="text-sm">
                                        <div className="font-medium text-slate-800 dark:text-slate-200">Primeira linha do arquivo é o cabeçalho</div>
                                        <div className="text-xs text-slate-500 dark:text-slate-400">Usa os textos da linha 1 como nomes das colunas.</div>
                                    </div>
                                </label>
                            </div>
                            {tableShape && (
                                <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
                                    {tableShape === 'generic'
                                        ? 'Tabela criada com cabeçalho genérico — modo travado em "Cabeçalho genérico".'
                                        : 'Tabela tem colunas com nomes semânticos — modo travado em "Primeira linha".'}
                                </p>
                            )}
                        </div>
                        <div className="border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-lg p-8 text-center hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors">
                            <input
                                type="file"
                                id="file-upload"
                                accept=".xlsx, .xls, .csv, .pdf"
                                onChange={handleFileChange}
                                className="hidden"
                            />
                            <label htmlFor="file-upload" className="cursor-pointer flex flex-col items-center gap-2">
                                <Upload className="w-8 h-8 text-violet-500" />
                                <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                                    {file ? file.name : "Clique para selecionar um arquivo"}
                                </span>
                                <span className="text-xs text-slate-400">
                                    Excel (.xlsx), CSV ou PDF
                                </span>
                            </label>
                        </div>
                        <p className="text-xs text-slate-500 dark:text-slate-400 text-center">
                            O arquivo será anexado à tabela existente. A coluna de data será gerada automaticamente.
                        </p>
                    </form>
                </div>

                <div className="p-4 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 flex justify-end gap-3 rounded-b-lg">
                    <button
                        type="button"
                        onClick={onClose}
                        className="px-4 py-2 text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700 rounded-md"
                    >
                        Cancelar
                    </button>
                    <button
                        type="submit"
                        form="data-entry-form"
                        disabled={loading || inspecting || !file}
                        className="bg-violet-600 text-white px-4 py-2 rounded-md hover:bg-violet-700 disabled:opacity-50 flex items-center gap-2"
                    >
                        {(loading || inspecting) ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                        {inspecting ? 'Verificando…' : 'Enviar Arquivo'}
                    </button>
                </div>
                {oversizedCols && (
                    <ColumnRenameModal
                        oversized={oversizedCols}
                        onConfirm={(renames) => doAppend(renames)}
                        onCancel={() => setOversizedCols(null)}
                        loading={loading}
                    />
                )}
            </div>
        </div>
    );
};

export default DataEntryForm;
