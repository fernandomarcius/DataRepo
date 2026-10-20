import React, { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

const formatElapsed = (ms) => {
    const total = Math.floor(ms / 1000);
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
};

const UploadProgressOverlay = ({ filename, uploadPercent, isProcessing, startTime }) => {
    const [now, setNow] = useState(Date.now());

    useEffect(() => {
        const id = setInterval(() => setNow(Date.now()), 500);
        return () => clearInterval(id);
    }, []);

    const elapsed = now - startTime;
    const isPdf = filename?.toLowerCase().endsWith('.pdf');
    const showLongHint = elapsed > 15000;

    let stage;
    if (!isProcessing && uploadPercent < 100) {
        stage = `Enviando arquivo… ${uploadPercent}%`;
    } else if (isPdf) {
        stage = 'Processando PDF (extraindo tabelas)…';
    } else {
        stage = 'Processando arquivo no servidor…';
    }

    return (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-60">
            <div className="bg-white dark:bg-slate-800 p-6 rounded-lg shadow-xl w-96 border dark:border-slate-700">
                <div className="flex items-center gap-3 mb-4">
                    <Loader2 className="w-6 h-6 animate-spin text-violet-600 shrink-0" />
                    <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-800 dark:text-slate-100 truncate">
                            {filename}
                        </p>
                        <p className="text-xs text-slate-500 dark:text-slate-400">
                            {stage}
                        </p>
                    </div>
                </div>

                {!isProcessing && uploadPercent < 100 && (
                    <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-2 mb-3 overflow-hidden">
                        <div
                            className="bg-violet-600 h-2 rounded-full transition-all"
                            style={{ width: `${uploadPercent}%` }}
                        />
                    </div>
                )}

                <div className="text-xs text-slate-500 dark:text-slate-400">
                    Tempo decorrido: {formatElapsed(elapsed)}
                </div>

                {showLongHint && (
                    <p className="mt-3 text-xs text-amber-600 dark:text-amber-400">
                        Documentos grandes podem levar alguns minutos. Não feche a página.
                    </p>
                )}
            </div>
        </div>
    );
};

export default UploadProgressOverlay;
