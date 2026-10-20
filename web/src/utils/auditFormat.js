export const ACTION_BADGE = {
    CREATE:  'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
    UPDATE:  'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
    DELETE:  'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
    UPLOAD:  'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
    RENAME:  'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
    ANALYZE: 'bg-slate-100 text-slate-700 dark:bg-slate-700/60 dark:text-slate-300',
    INSERT:  'bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-300',
    SYNC:    'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300',
    LOGIN:   'bg-slate-100 text-slate-700 dark:bg-slate-700/60 dark:text-slate-300',
    PASSWORD_RESET_REQUEST: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
    PASSWORD_RESET: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
    PASSWORD_CHANGE: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
};

export const ACTION_LABELS = {
    CREATE: 'Criação', UPDATE: 'Atualização', DELETE: 'Exclusão',
    UPLOAD: 'Upload', RENAME: 'Renomear', ANALYZE: 'Análise',
    INSERT: 'Inserção', SYNC: 'Sincronização', LOGIN: 'Login',
    PASSWORD_RESET_REQUEST: 'Pedido de reset de senha',
    PASSWORD_RESET: 'Reset de senha', PASSWORD_CHANGE: 'Troca de senha',
};

export const ENTITY_LABELS = {
    user: 'Usuário', report: 'Relatório', view: 'View',
    table: 'Tabela', table_row: 'Linhas de tabela', file: 'Arquivo', session: 'Sessão',
    function: 'Função', connection: 'Conexão',
};

export const formatTs = (ts) => {
    if (!ts) return '—';
    try {
        return new Intl.DateTimeFormat('pt-BR', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
        }).format(new Date(ts));
    } catch {
        return ts;
    }
};
