import React, { useEffect, useMemo, useState } from 'react';
import { AlertCircle, Loader2 } from 'lucide-react';

const MAX_BYTES = 63;

const byteLength = (s) => new TextEncoder().encode(s || '').length;

/**
 * Modal that asks the user to shorten column names whose UTF-8 byte length
 * exceeds the Postgres identifier limit. Prevents submitting any value that
 * still breaks the limit.
 *
 * Props:
 *  - oversized: [{ name, bytes, suggestion }]
 *  - onConfirm(renames: { [originalName]: newName })
 *  - onCancel()
 *  - loading: bool
 */
const ColumnRenameModal = ({ oversized, onConfirm, onCancel, loading = false }) => {
    const [values, setValues] = useState({});

    useEffect(() => {
        const initial = {};
        for (const col of oversized || []) {
            initial[col.name] = col.suggestion ?? col.name;
        }
        setValues(initial);
    }, [oversized]);

    const errors = useMemo(() => {
        const errs = {};
        const seen = new Map();
        for (const col of oversized || []) {
            const v = values[col.name] ?? '';
            const b = byteLength(v);
            if (!v.trim()) {
                errs[col.name] = 'Nome não pode ficar em branco.';
            } else if (b > MAX_BYTES) {
                errs[col.name] = `Tamanho ${b} bytes — máximo ${MAX_BYTES}.`;
            } else if (seen.has(v)) {
                errs[col.name] = `Nome colide com outro rename ("${seen.get(v)}").`;
            } else {
                seen.set(v, col.name);
            }
        }
        return errs;
    }, [oversized, values]);

    const canSubmit = Object.keys(errors).length === 0 && !loading;

    const handleSubmit = () => {
        if (!canSubmit) return;
        // Only emit renames where the final name differs from the original.
        const renames = {};
        for (const col of oversized || []) {
            const v = values[col.name];
            if (v && v !== col.name) renames[col.name] = v;
        }
        onConfirm(renames);
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-60">
            <div className="bg-white dark:bg-slate-800 p-6 rounded-lg shadow-xl w-full max-w-2xl border dark:border-slate-700 max-h-[90vh] overflow-y-auto">
                <h3 className="text-lg font-semibold mb-2 text-slate-900 dark:text-slate-100 flex items-center gap-2">
                    <AlertCircle className="w-5 h-5 text-amber-500" />
                    Ajustar nomes de coluna
                </h3>
                <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
                    O Postgres limita nomes de identificador a <strong>{MAX_BYTES} bytes</strong>{' '}
                    (acentos contam 2). As colunas abaixo estão acima do limite — ajuste o nome
                    curto que será gravado. O nome original completo fica salvo como apelido e o
                    sistema usa essa associação automaticamente em uploads futuros.
                </p>

                <div className="space-y-4">
                    {(oversized || []).map((col) => {
                        const v = values[col.name] ?? '';
                        const b = byteLength(v);
                        const err = errors[col.name];
                        const isOk = !err;
                        return (
                            <div key={col.name} className="border dark:border-slate-700 rounded-md p-3 bg-slate-50 dark:bg-slate-900/30">
                                <div className="text-xs text-slate-500 dark:text-slate-400 mb-1">Original ({col.bytes} bytes)</div>
                                <div className="font-mono text-sm text-slate-800 dark:text-slate-200 mb-2 break-all">{col.name}</div>
                                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                                    Nome curto que será gravado
                                </label>
                                <input
                                    type="text"
                                    value={v}
                                    onChange={(e) => setValues({ ...values, [col.name]: e.target.value })}
                                    className={`block w-full rounded-md shadow-xs font-mono text-sm p-2 border bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 ${
                                        isOk
                                            ? 'border-slate-300 dark:border-slate-600 focus:border-violet-500 focus:ring-violet-500'
                                            : 'border-red-400 dark:border-red-500 focus:border-red-500 focus:ring-red-500'
                                    }`}
                                />
                                <div className="flex items-center justify-between mt-1">
                                    <div className={`text-xs ${b > MAX_BYTES ? 'text-red-600 dark:text-red-400 font-medium' : 'text-slate-500 dark:text-slate-400'}`}>
                                        {b} / {MAX_BYTES} bytes
                                    </div>
                                    {err && (
                                        <div className="text-xs text-red-600 dark:text-red-400">{err}</div>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>

                <div className="flex justify-end gap-2 mt-6">
                    <button
                        type="button"
                        onClick={onCancel}
                        disabled={loading}
                        className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 rounded-md hover:bg-slate-200 dark:hover:bg-slate-600 disabled:opacity-50"
                    >
                        Cancelar
                    </button>
                    <button
                        type="button"
                        onClick={handleSubmit}
                        disabled={!canSubmit}
                        className="px-4 py-2 text-sm font-medium text-white bg-violet-600 rounded-md hover:bg-violet-700 disabled:opacity-50 flex items-center gap-2"
                    >
                        {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                        Confirmar e Enviar
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ColumnRenameModal;
