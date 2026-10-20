import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Upload, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import api from '../api/client';
import UploadProgressOverlay from './UploadProgressOverlay';
import ColumnRenameModal from './ColumnRenameModal';

const UploadSection = ({ onUploadSuccess }) => {
    const [file, setFile] = useState(null);
    const [tableName, setTableName] = useState('');
    const [headerMode, setHeaderMode] = useState('generic');
    const [loading, setLoading] = useState(false);
    const [status, setStatus] = useState(null); // { type: 'success' | 'error', message: '' }
    const [showModal, setShowModal] = useState(false);
    const [isDragging, setIsDragging] = useState(false);
    const [uploadPercent, setUploadPercent] = useState(0);
    const [isProcessing, setIsProcessing] = useState(false);
    const [startTime, setStartTime] = useState(null);
    const [oversizedCols, setOversizedCols] = useState(null); // null or array
    const [inspecting, setInspecting] = useState(false);

    const suggestTableName = (filename) => {
        // Remove extension
        let name = filename.split('.').slice(0, -1).join('.');

        // Convert to lowercase and replace non-alphanumeric chars with underscores
        name = name.toLowerCase()
            .replace(/[^a-z0-9]+/g, '_')
            .replace(/^_+|_+$/g, ''); // Trim leading/trailing underscores

        // Fallback if name becomes empty
        if (!name) name = 'table_upload';

        // Ensure it doesn't start with a number (Postgres doesn't like that usually, though quotes handle it, cleaner to avoid)
        if (/^\d/.test(name)) name = 't_' + name;

        return name;
    };

    const processFile = (selectedFile) => {
        if (!selectedFile) return;

        setFile(selectedFile);
        const suggestedName = suggestTableName(selectedFile.name);
        setTableName(suggestedName);
        setHeaderMode('generic');
        setStatus(null);

        // Immediate modal open
        setShowModal(true);
    };

    const handleFileChange = (e) => {
        const selectedFile = e.target.files[0];
        processFile(selectedFile);
    };

    const handleDragOver = (e) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const handleDragLeave = (e) => {
        e.preventDefault();
        setIsDragging(false);
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setIsDragging(false);

        const droppedFiles = e.dataTransfer.files;
        if (droppedFiles && droppedFiles.length > 0) {
            processFile(droppedFiles[0]);
        }
    };

    const doUpload = async (columnRenames) => {
        setLoading(true);
        setShowModal(false);
        setOversizedCols(null);
        setUploadPercent(0);
        setIsProcessing(false);
        setStartTime(Date.now());

        const formData = new FormData();
        formData.append('file', file);
        if (tableName) {
            formData.append('table_name', tableName);
        }
        formData.append('header_mode', headerMode);
        if (columnRenames && Object.keys(columnRenames).length > 0) {
            formData.append('column_renames', JSON.stringify(columnRenames));
        }

        try {
            await api.post('/upload', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
                onUploadProgress: (e) => {
                    if (!e.total) return;
                    const pct = Math.round((e.loaded * 100) / e.total);
                    setUploadPercent(pct);
                    if (pct >= 100) setIsProcessing(true);
                },
            });
            setStatus({ type: 'success', message: 'Arquivo carregado com sucesso!' });
            setFile(null);
            if (onUploadSuccess) onUploadSuccess();
        } catch (error) {
            setStatus({ type: 'error', message: error.response?.data?.error || 'Falha no envio' });
        } finally {
            setLoading(false);
            setIsProcessing(false);
            setUploadPercent(0);
        }
    };

    const confirmUpload = async () => {
        setInspecting(true);
        setShowModal(false);

        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('header_mode', headerMode);
            const res = await api.post('/inspect-headers', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
            });
            const oversized = res.data?.oversized || [];
            if (oversized.length === 0) {
                await doUpload({});
            } else {
                setOversizedCols(oversized);
            }
        } catch (error) {
            setStatus({ type: 'error', message: error.response?.data?.error || 'Falha ao inspecionar o arquivo' });
        } finally {
            setInspecting(false);
        }
    };

    const handleRenameConfirm = (renames) => {
        doUpload(renames);
    };

    const handleRenameCancel = () => {
        setOversizedCols(null);
    };

    return (
        <div className="bg-white dark:bg-slate-800 p-6 rounded-lg shadow-md mb-6 relative transition-colors duration-200">
            <h2 className="text-xl font-semibold mb-4 flex items-center gap-2 text-slate-800 dark:text-slate-100">
                <Upload className="w-5 h-5" /> Carregar Dados
            </h2>

            <div
                className={`
                    border-2 border-dashed rounded-lg p-8 flex flex-col items-center justify-center transition-all cursor-pointer
                    ${isDragging
                        ? 'border-violet-500 bg-violet-50 dark:bg-violet-900/20'
                        : 'border-slate-300 dark:border-slate-600 hover:border-violet-400 dark:hover:border-violet-500 hover:bg-slate-50 dark:hover:bg-slate-700/50'
                    }
                `}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
            >
                <input
                    type="file"
                    id="file-upload"
                    accept=".xlsx, .xls, .csv, .pdf"
                    onChange={handleFileChange}
                    className="hidden"
                />

                <label htmlFor="file-upload" className="cursor-pointer flex flex-col items-center">
                    <div className="bg-violet-100 dark:bg-violet-900/50 p-3 rounded-full mb-3 text-violet-600 dark:text-violet-300">
                        <Upload className="w-6 h-6" />
                    </div>
                    <p className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                        Clique para selecionar ou arraste um arquivo
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                        Suporta Excel (.xlsx, .xls), CSV e PDF
                    </p>
                </label>
            </div>

            {/* Modal Popup */}
            {showModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 animate-in fade-in duration-200">
                    <div className="bg-white dark:bg-slate-800 p-6 rounded-lg shadow-xl w-96 border dark:border-slate-700 scale-100">
                        <h3 className="text-lg font-semibold mb-4 text-slate-900 dark:text-slate-100">Confirmar Nome da Tabela</h3>
                        <div className="mb-4">
                            <p className="text-sm text-slate-600 dark:text-slate-400 mb-2">
                                Arquivo: <span className="font-medium">{file?.name}</span>
                            </p>
                            <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">
                                Nome da Tabela (Sugerido)
                            </label>
                            <input
                                type="text"
                                value={tableName}
                                onChange={(e) => setTableName(e.target.value)}
                                className="block w-full rounded-md border-slate-300 dark:border-slate-600 shadow-xs focus:border-violet-500 focus:ring-violet-500 sm:text-sm p-2 border bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100"
                                autoFocus
                            />
                            <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">
                                Ajuste o nome se necessário (apenas letras, números e _).
                            </p>
                        </div>
                        <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-2">
                                Como interpretar o cabeçalho?
                            </label>
                            <div className="space-y-2">
                                <label className="flex items-start gap-2 cursor-pointer">
                                    <input
                                        type="radio"
                                        name="header-mode"
                                        value="generic"
                                        checked={headerMode === 'generic'}
                                        onChange={() => setHeaderMode('generic')}
                                        className="mt-1 text-violet-600 focus:ring-violet-500"
                                    />
                                    <div className="text-sm">
                                        <div className="font-medium text-slate-800 dark:text-slate-200">Cabeçalho genérico (Unnamed: 0, 1, 2…)</div>
                                        <div className="text-xs text-slate-500 dark:text-slate-400">Mantém os dados brutos, sem interpretação. Todas as linhas viram dados.</div>
                                    </div>
                                </label>
                                <label className="flex items-start gap-2 cursor-pointer">
                                    <input
                                        type="radio"
                                        name="header-mode"
                                        value="first_row"
                                        checked={headerMode === 'first_row'}
                                        onChange={() => setHeaderMode('first_row')}
                                        className="mt-1 text-violet-600 focus:ring-violet-500"
                                    />
                                    <div className="text-sm">
                                        <div className="font-medium text-slate-800 dark:text-slate-200">Primeira linha do arquivo é o cabeçalho</div>
                                        <div className="text-xs text-slate-500 dark:text-slate-400">Usa os textos da linha 1 como nomes das colunas.</div>
                                    </div>
                                </label>
                            </div>
                        </div>
                        <div className="flex justify-end gap-2">
                            <button
                                onClick={() => { setShowModal(false); setFile(null); }}
                                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-slate-300 bg-gray-100 dark:bg-slate-700 rounded-md hover:bg-gray-200 dark:hover:bg-slate-600"
                            >
                                Cancelar
                            </button>
                            <button
                                onClick={confirmUpload}
                                disabled={loading || inspecting}
                                className="px-4 py-2 text-sm font-medium text-white bg-violet-600 rounded-md hover:bg-violet-700 flex items-center gap-2"
                            >
                                {(loading || inspecting) && <Loader2 className="w-4 h-4 animate-spin" />}
                                {inspecting ? 'Verificando…' : 'Confirmar e Enviar'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {oversizedCols && (
                <ColumnRenameModal
                    oversized={oversizedCols}
                    onConfirm={handleRenameConfirm}
                    onCancel={handleRenameCancel}
                    loading={loading}
                />
            )}

            {loading && file && startTime && (
                <UploadProgressOverlay
                    filename={file.name}
                    uploadPercent={uploadPercent}
                    isProcessing={isProcessing}
                    startTime={startTime}
                />
            )}

            {status && (
                <div className={`mt-4 p-3 rounded-md flex items-center justify-between gap-2 ${status.type === 'success' ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400' : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'
                    }`}>
                    <div className="flex items-center gap-2">
                        {status.type === 'success' ? <CheckCircle className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
                        {status.message}
                    </div>
                    {status.type === 'success' && (
                        <Link to="/" className="text-sm font-semibold underline hover:text-green-900">
                            Ir para Consultas
                        </Link>
                    )}
                </div>
            )}
        </div>
    );
};


export default UploadSection;
