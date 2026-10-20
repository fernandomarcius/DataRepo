import React, { useState, useEffect, useCallback } from 'react';
import { Plus, Trash2, Play, RefreshCw, ChevronDown, ChevronRight, ArrowUpDown, Filter, Columns, Table2, Save, FolderOpen, Bookmark, Copy, Keyboard, AlertTriangle, AlertCircle, CheckCircle } from 'lucide-react';
import api from '../api/client';

// Aggregation options
const AGGREGATIONS = [
    { value: '', label: 'Nenhum' },
    { value: 'COUNT', label: 'CONTAGEM (COUNT)' },
    { value: 'SUM', label: 'SOMA (SUM)' },
    { value: 'AVG', label: 'MÉDIA (AVG)' },
    { value: 'MIN', label: 'MÍNIMO (MIN)' },
    { value: 'MAX', label: 'MÁXIMO (MAX)' },
    { value: 'COUNT_DISTINCT', label: 'CONTAGEM ÚNICA' },
];

// Enhanced operators
const OPERATORS = [
    { value: '=', label: 'Igual (=)', needsValue: true },
    { value: '!=', label: 'Diferente (!=)', needsValue: true },
    { value: '>', label: 'Maior que (>)', needsValue: true },
    { value: '<', label: 'Menor que (<)', needsValue: true },
    { value: '>=', label: 'Maior ou Igual (>=)', needsValue: true },
    { value: '<=', label: 'Menor ou Igual (<=)', needsValue: true },
    { value: 'LIKE', label: 'Contém (LIKE)', needsValue: true },
    { value: 'NOT LIKE', label: 'Não Contém', needsValue: true },
    { value: 'STARTS_WITH', label: 'Começa com', needsValue: true },
    { value: 'ENDS_WITH', label: 'Termina com', needsValue: true },
    { value: 'IS NULL', label: 'É Nulo', needsValue: false },
    { value: 'IS NOT NULL', label: 'Não é Nulo', needsValue: false },
    { value: 'IN', label: 'Está em (lista)', needsValue: true },
    { value: 'NOT IN', label: 'Não está em (lista)', needsValue: true },
    { value: 'BETWEEN', label: 'Entre (BETWEEN)', needsValue: true },
    // Date-specific operators
    { value: 'DATE_TODAY', label: '📅 Hoje', needsValue: false },
    { value: 'DATE_YESTERDAY', label: '📅 Ontem', needsValue: false },
    { value: 'DATE_LAST_7_DAYS', label: '📅 Últimos 7 dias', needsValue: false },
    { value: 'DATE_LAST_30_DAYS', label: '📅 Últimos 30 dias', needsValue: false },
    { value: 'DATE_THIS_MONTH', label: '📅 Este mês', needsValue: false },
    { value: 'DATE_THIS_YEAR', label: '📅 Este ano', needsValue: false },
];

// Sort direction options
const SORT_DIRECTIONS = [
    { value: 'ASC', label: '↑ Crescente (A-Z)' },
    { value: 'DESC', label: '↓ Decrescente (Z-A)' },
];

// JOIN types
const JOIN_TYPES = [
    { value: 'INNER JOIN', label: 'INNER JOIN (apenas correspondentes)' },
    { value: 'LEFT JOIN', label: 'LEFT JOIN (todos da esquerda)' },
    { value: 'RIGHT JOIN', label: 'RIGHT JOIN (todos da direita)' },
    { value: 'FULL OUTER JOIN', label: 'FULL OUTER JOIN (todos)' },
];

// Query Templates
const QUERY_TEMPLATES = [
    {
        name: 'Top 10 Registros',
        description: 'Primeiros 10 registros da tabela',
        apply: (_table) => ({ sortColumns: [], limit: 10 })
    },
    {
        name: 'Contagem por Coluna',
        description: 'Conta registros agrupados por uma coluna',
        apply: (table, columns) => columns.length > 0 ? ({
            selectedColumns: [{ name: columns[0].column_name, aggregation: 'COUNT' }],
        }) : {}
    },
    {
        name: 'Soma Total',
        description: 'Soma de uma coluna numérica',
        requiresNumericColumn: true,
        apply: (table, columns) => {
            const numCol = columns.find(c => ['integer', 'numeric', 'decimal', 'double precision', 'real', 'bigint'].includes(c.data_type));
            return numCol ? { selectedColumns: [{ name: numCol.column_name, aggregation: 'SUM' }] } : {};
        }
    },
    {
        name: 'Registros Recentes',
        description: 'Ordenado por data mais recente',
        apply: (table, columns) => {
            const dateCol = columns.find(c => ['timestamp', 'date', 'timestamptz', 'timestamp without time zone'].includes(c.data_type));
            return dateCol ? { sortColumns: [{ column: dateCol.column_name, direction: 'DESC' }] } : {};
        }
    },
    {
        name: 'Valores Únicos',
        description: 'Lista valores únicos de uma coluna',
        apply: () => ({ isDistinct: true })
    },
];

// Collapsible Section Component
const Section = ({ title, icon: Icon, children, defaultOpen = true, badge = null }) => {
    const [isOpen, setIsOpen] = useState(defaultOpen);

    return (
        <div className="bg-slate-50 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden transition-all">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="w-full p-3 flex items-center justify-between hover:bg-slate-100 dark:hover:bg-slate-700/50 transition-colors"
            >
                <div className="flex items-center gap-2">
                    {Icon && <Icon className="w-4 h-4 text-violet-500" />}
                    <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{title}</span>
                    {badge && (
                        <span className="px-1.5 py-0.5 text-xs bg-violet-100 dark:bg-violet-900/50 text-violet-600 dark:text-violet-300 rounded-sm">
                            {badge}
                        </span>
                    )}
                </div>
                {isOpen ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
            </button>
            <div className={`transition-all duration-200 ${isOpen ? 'max-h-[2000px] opacity-100' : 'max-h-0 opacity-0 overflow-hidden'}`}>
                <div className="p-4 pt-0 border-t border-slate-200 dark:border-slate-700">
                    {children}
                </div>
            </div>
        </div>
    );
};

const VisualQueryBuilder = ({ tables, onRun, limit, setLimit }) => {
    // Core state
    const [selectedTable, setSelectedTable] = useState('');
    const [columns, setColumns] = useState([]);
    const [selectedColumns, setSelectedColumns] = useState([]);
    const [filters, setFilters] = useState([]);
    const [havingFilters, setHavingFilters] = useState([]);
    const [sortColumns, setSortColumns] = useState([]);
    const [isDistinct, setIsDistinct] = useState(false);

    // JOIN state
    const [joins, setJoins] = useState([]);
    const [joinColumns, setJoinColumns] = useState({}); // { tableName: [columns] }

    // UI state
    const [generatedSQL, setGeneratedSQL] = useState('');
    const [loadingColumns, setLoadingColumns] = useState(false);
    const [error, setError] = useState(null);
    const [showTemplates, setShowTemplates] = useState(false);
    const [savedQueries, setSavedQueries] = useState([]);
    const [showSavedQueries, setShowSavedQueries] = useState(false);
    const [copySuccess, setCopySuccess] = useState(false);

    // Validation state
    const [validationErrors, setValidationErrors] = useState([]);
    const [validationWarnings, setValidationWarnings] = useState([]);

    // Validate query and return errors/warnings
    const validateQuery = useCallback(() => {
        const errors = [];
        const warnings = [];

        if (!selectedTable) {
            return { errors, warnings };
        }

        // Check for incomplete filters
        filters.forEach((f, idx) => {
            const op = OPERATORS.find(o => o.value === f.operator);
            if (f.column && op?.needsValue && !f.value) {
                errors.push(`Filtro ${idx + 1}: valor obrigatório para operador "${f.operator}"`);
            }
            if (f.operator === 'BETWEEN' && f.value && !f.value2) {
                errors.push(`Filtro ${idx + 1}: BETWEEN requer dois valores`);
            }
            if (f.operator === 'IN' || f.operator === 'NOT IN') {
                if (f.value && !f.value.includes(',')) {
                    warnings.push(`Filtro ${idx + 1}: ${f.operator} geralmente usa lista de valores separados por vírgula`);
                }
            }
        });

        // Check for incomplete HAVING filters
        havingFilters.forEach((h, idx) => {
            if (h.column && !h.value) {
                errors.push(`HAVING ${idx + 1}: valor obrigatório`);
            }
        });

        // Check HAVING without aggregations
        if (havingFilters.length > 0 && !selectedColumns.some(c => c.aggregation)) {
            errors.push('HAVING requer pelo menos uma coluna com agregação');
        }

        // Check for incomplete JOINs
        joins.forEach((j, idx) => {
            if (j.table) {
                const hasValidCondition = j.conditions?.some(c => c.leftColumn && c.rightColumn);
                if (!hasValidCondition) {
                    errors.push(`JOIN ${idx + 1} (${j.table}): defina pelo menos uma condição de relacionamento`);
                }
            }
        });

        // Check for ORDER BY without column
        sortColumns.forEach((s, idx) => {
            if (!s.column) {
                warnings.push(`Ordenação ${idx + 1}: selecione uma coluna`);
            }
        });

        // Check for aggregation without GROUP BY columns
        const hasAggregation = selectedColumns.some(c => c.aggregation);
        const nonAggregatedCols = selectedColumns.filter(c => c.name && !c.aggregation);
        if (hasAggregation && nonAggregatedCols.length === 0 && selectedColumns.length > 1) {
            warnings.push('Apenas colunas agregadas selecionadas - resultará em uma única linha');
        }

        // Check for DISTINCT with aggregations (usually not needed)
        if (isDistinct && hasAggregation) {
            warnings.push('DISTINCT com agregações geralmente não é necessário (agregações já retornam valores únicos por grupo)');
        }

        // Check for empty selected columns
        if (selectedColumns.length > 0 && !selectedColumns.some(c => c.name)) {
            warnings.push('Adicione pelo menos uma coluna ou remova as colunas vazias');
        }

        return { errors, warnings };
    }, [selectedTable, filters, havingFilters, selectedColumns, joins, sortColumns, isDistinct]);

    // Load saved queries from localStorage on mount
    useEffect(() => {
        const saved = localStorage.getItem('vqb_saved_queries');
        if (saved) {
            try {
                setSavedQueries(JSON.parse(saved));
            } catch (e) {
                console.error('Failed to parse saved queries');
            }
        }
    }, []);

    // Keyboard shortcuts
    useEffect(() => {
        const handleKeyDown = (e) => {
            // Ctrl/Cmd + Enter to execute query
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                if (generatedSQL) {
                    onRun(generatedSQL);
                }
            }
            // Ctrl/Cmd + S to save query
            if ((e.ctrlKey || e.metaKey) && e.key === 's') {
                e.preventDefault();
                handleSaveQuery();
            }
            // Escape to close modals
            if (e.key === 'Escape') {
                setShowTemplates(false);
                setShowSavedQueries(false);
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [generatedSQL, onRun]);

    // Save current query state
    const handleSaveQuery = () => {
        if (!selectedTable) return;

        const queryName = prompt('Nome para salvar a consulta:');
        if (!queryName) return;

        const queryState = {
            id: Date.now(),
            name: queryName,
            table: selectedTable,
            selectedColumns,
            filters,
            havingFilters,
            sortColumns,
            isDistinct,
            joins,
            savedAt: new Date().toISOString()
        };

        const newSavedQueries = [...savedQueries, queryState];
        setSavedQueries(newSavedQueries);
        localStorage.setItem('vqb_saved_queries', JSON.stringify(newSavedQueries));
    };

    // Load a saved query
    const handleLoadQuery = (query) => {
        setSelectedTable(query.table);
        setTimeout(() => {
            setSelectedColumns(query.selectedColumns || []);
            setFilters(query.filters || []);
            setHavingFilters(query.havingFilters || []);
            setSortColumns(query.sortColumns || []);
            setIsDistinct(query.isDistinct || false);
            setJoins(query.joins || []);
        }, 100);
        setShowSavedQueries(false);
    };

    // Delete a saved query
    const handleDeleteSavedQuery = (id) => {
        const newSavedQueries = savedQueries.filter(q => q.id !== id);
        setSavedQueries(newSavedQueries);
        localStorage.setItem('vqb_saved_queries', JSON.stringify(newSavedQueries));
    };

    // Apply a template
    const handleApplyTemplate = (template) => {
        const result = template.apply(selectedTable, columns);
        if (result.selectedColumns) setSelectedColumns(result.selectedColumns);
        if (result.sortColumns) setSortColumns(result.sortColumns);
        if (result.isDistinct !== undefined) setIsDistinct(result.isDistinct);
        if (result.limit) setLimit(result.limit);
        setShowTemplates(false);
    };

    // Copy SQL to clipboard
    const handleCopySQL = async () => {
        if (!generatedSQL) return;
        try {
            await navigator.clipboard.writeText(generatedSQL);
            setCopySuccess(true);
            setTimeout(() => setCopySuccess(false), 2000);
        } catch (err) {
            console.error('Failed to copy SQL');
        }
    };

    useEffect(() => {
        if (selectedTable) {
            fetchColumnsForTable(selectedTable);
            setSelectedColumns([]);
            setFilters([]);
            setHavingFilters([]);
            setSortColumns([]);
            setJoins([]);
            setJoinColumns({});
            setError(null);
        }
    }, [selectedTable]);

    useEffect(() => {
        generateSQL();
    }, [selectedTable, selectedColumns, filters, havingFilters, sortColumns, isDistinct, joins]);

    // Run validation whenever query changes
    useEffect(() => {
        const { errors, warnings } = validateQuery();
        setValidationErrors(errors);
        setValidationWarnings(warnings);
    }, [validateQuery]);

    const fetchColumnsForTable = async (tableName, isJoin = false) => {
        if (!isJoin) setLoadingColumns(true);
        try {
            const res = await api.get(`/tables/${tableName}/schema`);
            const cols = res.data.schema.map(c => ({
                ...c,
                table: tableName,
                fullName: `${tableName}.${c.column_name}`
            }));

            if (isJoin) {
                setJoinColumns(prev => ({ ...prev, [tableName]: cols }));
            } else {
                setColumns(cols);
                setJoinColumns(prev => ({ ...prev, [tableName]: cols }));
            }
        } catch (err) {
            console.error("Failed to fetch columns", err);
            setError("Falha ao carregar colunas.");
        } finally {
            if (!isJoin) setLoadingColumns(false);
        }
    };

    // Column handlers
    const handleAddColumn = () => {
        setSelectedColumns([...selectedColumns, { name: '', aggregation: '', alias: '' }]);
    };

    const handleRemoveColumn = (index) => {
        setSelectedColumns(selectedColumns.filter((_, i) => i !== index));
    };

    const handleColumnChange = (index, field, value) => {
        const newCols = [...selectedColumns];
        newCols[index] = { ...newCols[index], [field]: value };
        setSelectedColumns(newCols);
    };

    // Filter handlers
    const handleAddFilter = () => {
        setFilters([...filters, { column: '', operator: '=', value: '', value2: '', logic: 'AND' }]);
    };

    const handleRemoveFilter = (index) => {
        setFilters(filters.filter((_, i) => i !== index));
    };

    const handleFilterChange = (index, field, value) => {
        const newFilters = [...filters];
        newFilters[index] = { ...newFilters[index], [field]: value };
        setFilters(newFilters);
    };

    // HAVING filter handlers
    const handleAddHavingFilter = () => {
        setHavingFilters([...havingFilters, { aggregation: 'COUNT', column: '*', operator: '>', value: '' }]);
    };

    const handleRemoveHavingFilter = (index) => {
        setHavingFilters(havingFilters.filter((_, i) => i !== index));
    };

    const handleHavingFilterChange = (index, field, value) => {
        const newFilters = [...havingFilters];
        newFilters[index] = { ...newFilters[index], [field]: value };
        setHavingFilters(newFilters);
    };

    // Sort handlers
    const handleAddSort = () => {
        setSortColumns([...sortColumns, { column: '', direction: 'ASC' }]);
    };

    const handleRemoveSort = (index) => {
        setSortColumns(sortColumns.filter((_, i) => i !== index));
    };

    const handleSortChange = (index, field, value) => {
        const newSorts = [...sortColumns];
        newSorts[index] = { ...newSorts[index], [field]: value };
        setSortColumns(newSorts);
    };

    // JOIN handlers
    const handleAddJoin = () => {
        setJoins([...joins, {
            table: '',
            type: 'INNER JOIN',
            conditions: [{ leftColumn: '', rightColumn: '' }] // Array of conditions
        }]);
    };

    const handleRemoveJoin = (index) => {
        const removedTable = joins[index]?.table;
        setJoins(joins.filter((_, i) => i !== index));
        if (removedTable) {
            setJoinColumns(prev => {
                const newCols = { ...prev };
                delete newCols[removedTable];
                return newCols;
            });
        }
    };

    const handleJoinChange = async (index, field, value) => {
        const newJoins = [...joins];
        newJoins[index] = { ...newJoins[index], [field]: value };
        setJoins(newJoins);

        // If table was selected, fetch its columns
        if (field === 'table' && value) {
            await fetchColumnsForTable(value, true);
        }
    };

    // Add a new condition to a join
    const handleAddJoinCondition = (joinIndex) => {
        const newJoins = [...joins];
        newJoins[joinIndex].conditions.push({ leftColumn: '', rightColumn: '' });
        setJoins(newJoins);
    };

    // Remove a condition from a join
    const handleRemoveJoinCondition = (joinIndex, conditionIndex) => {
        const newJoins = [...joins];
        newJoins[joinIndex].conditions = newJoins[joinIndex].conditions.filter((_, i) => i !== conditionIndex);
        setJoins(newJoins);
    };

    // Update a specific condition
    const handleJoinConditionChange = (joinIndex, conditionIndex, field, value) => {
        const newJoins = [...joins];
        newJoins[joinIndex].conditions[conditionIndex] = {
            ...newJoins[joinIndex].conditions[conditionIndex],
            [field]: value
        };
        setJoins(newJoins);
    };

    // SQL Generation
    const generateSQL = () => {
        if (!selectedTable) {
            setGeneratedSQL('');
            return;
        }

        // SELECT clause
        let selectPart = '*';
        let groupByPart = '';

        if (selectedColumns.length > 0 && selectedColumns.some(c => c.name)) {
            const validCols = selectedColumns.filter(c => c.name);

            if (validCols.length > 0) {
                const selectItems = validCols.map(c => {
                    if (c.aggregation) {
                        if (c.aggregation === 'COUNT_DISTINCT') {
                            return `COUNT(DISTINCT ${c.name}) AS contagem_unica_${c.name}`;
                        }
                        return `${c.aggregation}(${c.name}) AS ${c.aggregation.toLowerCase()}_${c.name}`;
                    }
                    return c.name;
                });
                selectPart = selectItems.join(', ');

                // GROUP BY for aggregations
                const hasAggregation = validCols.some(c => c.aggregation);
                if (hasAggregation) {
                    const nonAggregated = validCols.filter(c => !c.aggregation).map(c => c.name);
                    if (nonAggregated.length > 0) {
                        groupByPart = `\nGROUP BY ${nonAggregated.join(', ')}`;
                    }
                }
            }
        }

        // DISTINCT
        const distinctPart = isDistinct ? 'DISTINCT ' : '';

        // WHERE clause
        let wherePart = '';
        const validFilters = filters.filter(f => f.column && (
            f.operator === 'IS NULL' ||
            f.operator === 'IS NOT NULL' ||
            f.operator.startsWith('DATE_') ||
            f.value
        ));

        if (validFilters.length > 0) {
            const conditions = validFilters.map(f => {
                const col = f.column;

                switch (f.operator) {
                    case 'IS NULL':
                        return `${col} IS NULL`;
                    case 'IS NOT NULL':
                        return `${col} IS NOT NULL`;
                    case 'LIKE':
                        return `${col} LIKE '%${f.value}%'`;
                    case 'NOT LIKE':
                        return `${col} NOT LIKE '%${f.value}%'`;
                    case 'STARTS_WITH':
                        return `${col} LIKE '${f.value}%'`;
                    case 'ENDS_WITH':
                        return `${col} LIKE '%${f.value}'`;
                    case 'IN':
                    case 'NOT IN': {
                        const values = f.value.split(',').map(v => {
                            const trimmed = v.trim();
                            return isNaN(trimmed) ? `'${trimmed}'` : trimmed;
                        }).join(', ');
                        return `${col} ${f.operator} (${values})`;
                    }
                    case 'BETWEEN': {
                        const val1 = isNaN(f.value) ? `'${f.value}'` : f.value;
                        const val2 = isNaN(f.value2) ? `'${f.value2}'` : f.value2;
                        return `${col} BETWEEN ${val1} AND ${val2}`;
                    }
                    // Date-specific operators
                    case 'DATE_TODAY':
                        return `${col}::date = CURRENT_DATE`;
                    case 'DATE_YESTERDAY':
                        return `${col}::date = CURRENT_DATE - INTERVAL '1 day'`;
                    case 'DATE_LAST_7_DAYS':
                        return `${col}::date >= CURRENT_DATE - INTERVAL '7 days'`;
                    case 'DATE_LAST_30_DAYS':
                        return `${col}::date >= CURRENT_DATE - INTERVAL '30 days'`;
                    case 'DATE_THIS_MONTH':
                        return `DATE_TRUNC('month', ${col}) = DATE_TRUNC('month', CURRENT_DATE)`;
                    case 'DATE_THIS_YEAR':
                        return `DATE_TRUNC('year', ${col}) = DATE_TRUNC('year', CURRENT_DATE)`;
                    default: {
                        const val = isNaN(f.value) ? `'${f.value}'` : f.value;
                        return `${col} ${f.operator} ${val}`;
                    }
                }
            });

            // Join conditions using the logic defined in each filter (for index > 0)
            let whereSql = '';
            conditions.forEach((cond, idx) => {
                if (idx === 0) {
                    whereSql = cond;
                } else {
                    const logic = validFilters[idx].logic || 'AND';
                    whereSql += `\n  ${logic} ${cond}`;
                }
            });
            wherePart = `\nWHERE ${whereSql}`;
        }

        // HAVING clause
        let havingPart = '';
        const validHaving = havingFilters.filter(h => h.column && h.value);
        if (validHaving.length > 0) {
            const conditions = validHaving.map(h => {
                const agg = h.aggregation === 'COUNT_DISTINCT'
                    ? `COUNT(DISTINCT ${h.column})`
                    : `${h.aggregation}(${h.column})`;
                const val = isNaN(h.value) ? `'${h.value}'` : h.value;
                return `${agg} ${h.operator} ${val}`;
            });
            havingPart = `\nHAVING ${conditions.join(' AND ')}`;
        }

        // ORDER BY clause
        let orderByPart = '';
        const validSorts = sortColumns.filter(s => s.column);
        if (validSorts.length > 0) {
            const sortItems = validSorts.map(s => `${s.column} ${s.direction}`);
            orderByPart = `\nORDER BY ${sortItems.join(', ')}`;
        }

        // JOIN clause
        let joinPart = '';
        const validJoins = joins.filter(j => j.table && j.conditions?.some(c => c.leftColumn && c.rightColumn));
        if (validJoins.length > 0) {
            joinPart = validJoins.map(j => {
                const validConditions = j.conditions.filter(c => c.leftColumn && c.rightColumn);
                const onClause = validConditions
                    .map(c => `${c.leftColumn} = ${c.rightColumn}`)
                    .join(' AND ');
                return `\n${j.type} ${j.table} ON ${onClause}`;
            }).join('');
        }

        const sql = `SELECT ${distinctPart}${selectPart}\nFROM ${selectedTable}${joinPart}${wherePart}${groupByPart}${havingPart}${orderByPart}`;
        setGeneratedSQL(sql);
    };

    const hasAggregations = selectedColumns.some(c => c.aggregation);
    const operatorNeedsValue = (op) => OPERATORS.find(o => o.value === op)?.needsValue !== false;

    return (
        <div className="flex flex-col lg:flex-row h-full gap-4 overflow-y-auto pr-2 pb-4 w-full max-w-full min-w-0">
            {/* Left Panel - Configuration */}
            <div className="flex flex-col gap-3 w-full lg:w-5/12 xl:w-1/3 min-w-0">

                {/* Toolbar */}
                <div className="flex items-center gap-2 flex-wrap">
                    <button
                        onClick={() => setShowTemplates(!showTemplates)}
                        className="text-xs flex items-center gap-1 px-2 py-1.5 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 rounded-sm hover:bg-amber-200 dark:hover:bg-amber-900/50 transition-colors"
                        title="Modelos de consulta"
                    >
                        <Bookmark className="w-3 h-3" /> Templates
                    </button>
                    <button
                        onClick={handleSaveQuery}
                        disabled={!selectedTable}
                        className="text-xs flex items-center gap-1 px-2 py-1.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded-sm hover:bg-green-200 dark:hover:bg-green-900/50 disabled:opacity-50 transition-colors"
                        title="Salvar consulta (Ctrl+S)"
                    >
                        <Save className="w-3 h-3" /> Salvar
                    </button>
                    <button
                        onClick={() => setShowSavedQueries(!showSavedQueries)}
                        className="text-xs flex items-center gap-1 px-2 py-1.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-sm hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors"
                        title="Carregar consulta salva"
                    >
                        <FolderOpen className="w-3 h-3" /> Carregar {savedQueries.length > 0 && `(${savedQueries.length})`}
                    </button>
                    <div className="ml-auto flex items-center gap-1 text-xs text-slate-400">
                        <Keyboard className="w-3 h-3" />
                        <span>Ctrl+Enter = Executar</span>
                    </div>
                </div>

                {/* Templates Dropdown */}
                {showTemplates && selectedTable && (
                    <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg p-3 animate-in slide-in-from-top-2 duration-200">
                        <h4 className="text-sm font-medium text-amber-800 dark:text-amber-200 mb-2">Modelos de Consulta</h4>
                        <div className="space-y-1">
                            {QUERY_TEMPLATES.map((template, idx) => (
                                <button
                                    key={idx}
                                    onClick={() => handleApplyTemplate(template)}
                                    className="w-full text-left px-2 py-1.5 text-sm rounded-sm hover:bg-amber-100 dark:hover:bg-amber-800/30 text-amber-900 dark:text-amber-100 transition-colors"
                                >
                                    <span className="font-medium">{template.name}</span>
                                    <span className="text-xs text-amber-600 dark:text-amber-400 ml-2">— {template.description}</span>
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {/* Saved Queries List */}
                {showSavedQueries && (
                    <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-lg p-3 animate-in slide-in-from-top-2 duration-200">
                        <h4 className="text-sm font-medium text-blue-800 dark:text-blue-200 mb-2">Consultas Salvas</h4>
                        {savedQueries.length === 0 ? (
                            <p className="text-xs text-blue-600 dark:text-blue-400 italic">Nenhuma consulta salva ainda.</p>
                        ) : (
                            <div className="space-y-1 max-h-40 overflow-y-auto">
                                {savedQueries.map((query) => (
                                    <div key={query.id} className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-sm hover:bg-blue-100 dark:hover:bg-blue-800/30">
                                        <button
                                            onClick={() => handleLoadQuery(query)}
                                            className="flex-1 text-left text-sm text-blue-900 dark:text-blue-100"
                                        >
                                            <span className="font-medium">{query.name}</span>
                                            <span className="text-xs text-blue-600 dark:text-blue-400 ml-2">({query.table})</span>
                                        </button>
                                        <button
                                            onClick={() => handleDeleteSavedQuery(query.id)}
                                            className="text-red-400 hover:text-red-600 p-1"
                                            title="Excluir"
                                        >
                                            <Trash2 className="w-3 h-3" />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* 1. Table Selection */}
                <Section title="1. Selecione a Tabela" icon={Table2} defaultOpen={true}>
                    <select
                        value={selectedTable}
                        onChange={(e) => setSelectedTable(e.target.value)}
                        className="w-full p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 text-sm"
                    >
                        <option value="">-- Escolha uma tabela --</option>
                        {tables.map(t => (
                            <option key={t} value={t}>{t}</option>
                        ))}
                    </select>

                    {/* DISTINCT checkbox */}
                    <label className="flex items-center gap-2 mt-3 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={isDistinct}
                            onChange={(e) => setIsDistinct(e.target.checked)}
                            className="w-4 h-4 rounded-sm border-slate-300 text-violet-600 focus:ring-violet-500"
                        />
                        <span className="text-sm text-slate-600 dark:text-slate-400">Resultados únicos (DISTINCT)</span>
                    </label>
                </Section>

                {/* 1.B JOINs - Only show if a table is selected */}
                {selectedTable && (
                    <Section
                        title="1.B Tabelas Relacionadas (JOINs)"
                        icon={Table2}
                        badge={joins.length > 0 ? joins.length : null}
                        defaultOpen={false}
                    >
                        <div className="flex justify-end mb-3">
                            <button
                                onClick={handleAddJoin}
                                className="text-xs flex items-center gap-1 text-violet-600 hover:text-violet-700 dark:text-violet-400 font-medium"
                            >
                                <Plus className="w-3 h-3" /> Adicionar JOIN
                            </button>
                        </div>

                        {joins.length === 0 && (
                            <p className="text-xs text-slate-500 dark:text-slate-400 italic">
                                Adicione JOINs para combinar dados de outras tabelas
                            </p>
                        )}

                        <div className="space-y-3">
                            {joins.map((join, idx) => (
                                <div key={idx} className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg space-y-2 animate-in slide-in-from-left-2 duration-200">
                                    <div className="flex gap-2 items-center">
                                        <select
                                            value={join.type}
                                            onChange={(e) => handleJoinChange(idx, 'type', e.target.value)}
                                            className="w-full p-2 border rounded-md text-sm bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                        >
                                            {JOIN_TYPES.map(jt => (
                                                <option key={jt.value} value={jt.value}>{jt.label}</option>
                                            ))}
                                        </select>
                                        <button onClick={() => handleRemoveJoin(idx)} className="text-red-400 hover:text-red-600 p-1">
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>

                                    <select
                                        value={join.table}
                                        onChange={(e) => handleJoinChange(idx, 'table', e.target.value)}
                                        className="w-full p-2 border rounded-md text-sm bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                    >
                                        <option value="">-- Tabela para juntar --</option>
                                        {tables.filter(t => t !== selectedTable).map(t => (
                                            <option key={t} value={t}>{t}</option>
                                        ))}
                                    </select>

                                    {join.table && (
                                        <div className="space-y-2">
                                            <div className="flex justify-between items-center">
                                                <span className="text-xs text-slate-500 dark:text-slate-400">Condições ON:</span>
                                                <button
                                                    onClick={() => handleAddJoinCondition(idx)}
                                                    className="text-xs flex items-center gap-1 text-blue-600 hover:text-blue-700 dark:text-blue-400 font-medium"
                                                >
                                                    <Plus className="w-3 h-3" /> Adicionar Condição
                                                </button>
                                            </div>
                                            {(join.conditions || []).map((cond, condIdx) => (
                                                <div key={condIdx} className="flex gap-2 items-center text-sm">
                                                    <select
                                                        value={cond.leftColumn}
                                                        onChange={(e) => handleJoinConditionChange(idx, condIdx, 'leftColumn', e.target.value)}
                                                        className="flex-1 p-2 border rounded-md text-sm bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                                    >
                                                        <option value="">Coluna {selectedTable}</option>
                                                        {columns.map(c => (
                                                            <option key={c.column_name} value={`${selectedTable}.${c.column_name}`}>
                                                                {selectedTable}.{c.column_name}
                                                            </option>
                                                        ))}
                                                    </select>
                                                    <span className="text-slate-400">=</span>
                                                    <select
                                                        value={cond.rightColumn}
                                                        onChange={(e) => handleJoinConditionChange(idx, condIdx, 'rightColumn', e.target.value)}
                                                        className="flex-1 p-2 border rounded-md text-sm bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                                    >
                                                        <option value="">Coluna {join.table}</option>
                                                        {(joinColumns[join.table] || []).map(c => (
                                                            <option key={c.column_name} value={`${join.table}.${c.column_name}`}>
                                                                {join.table}.{c.column_name}
                                                            </option>
                                                        ))}
                                                    </select>
                                                    {join.conditions.length > 1 && (
                                                        <button
                                                            onClick={() => handleRemoveJoinCondition(idx, condIdx)}
                                                            className="text-red-400 hover:text-red-600 p-1"
                                                            title="Remover condição"
                                                        >
                                                            <Trash2 className="w-3 h-3" />
                                                        </button>
                                                    )}
                                                </div>
                                            ))}
                                            {join.conditions?.length > 1 && (
                                                <p className="text-xs text-blue-600 dark:text-blue-400 italic">
                                                    Condições combinadas com AND
                                                </p>
                                            )}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </Section>
                )}

                {/* 2. Columns Selection */}
                <Section
                    title="2. Selecione Colunas"
                    icon={Columns}
                    badge={selectedColumns.length > 0 ? selectedColumns.length : null}
                >
                    <div className="flex justify-between items-center mb-3">
                        <span className="text-xs text-slate-500 dark:text-slate-400">
                            {selectedColumns.length === 0 ? 'Todas (*) por padrão' : ''}
                        </span>
                        <button
                            onClick={handleAddColumn}
                            disabled={!selectedTable || loadingColumns}
                            className="text-xs flex items-center gap-1 text-violet-600 hover:text-violet-700 dark:text-violet-400 font-medium disabled:opacity-50"
                        >
                            <Plus className="w-3 h-3" /> Adicionar
                        </button>
                    </div>

                    {loadingColumns && (
                        <div className="text-xs text-violet-600 animate-pulse">Carregando...</div>
                    )}

                    <div className="space-y-2">
                        {selectedColumns.map((col, idx) => (
                            <div key={idx} className="flex gap-2 items-center animate-in slide-in-from-left-2 duration-200">
                                <select
                                    value={col.name}
                                    onChange={(e) => handleColumnChange(idx, 'name', e.target.value)}
                                    className="flex-1 p-2 border rounded-md text-sm bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                >
                                    <option value="">Campo</option>
                                    {columns.map(c => (
                                        <option key={c.column_name} value={c.column_name}>
                                            {c.column_name} ({c.data_type})
                                        </option>
                                    ))}
                                </select>
                                <select
                                    value={col.aggregation}
                                    onChange={(e) => handleColumnChange(idx, 'aggregation', e.target.value)}
                                    className="w-28 p-2 border rounded-md text-sm bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                >
                                    {AGGREGATIONS.map(agg => (
                                        <option key={agg.value} value={agg.value}>{agg.label}</option>
                                    ))}
                                </select>
                                <button onClick={() => handleRemoveColumn(idx)} className="text-red-400 hover:text-red-600 p-1">
                                    <Trash2 className="w-4 h-4" />
                                </button>
                            </div>
                        ))}
                    </div>
                </Section>

                {/* 3. Filters (WHERE) */}
                <Section
                    title="3. Filtros (WHERE)"
                    icon={Filter}
                    badge={filters.length > 0 ? filters.length : null}
                >
                    <div className="mb-3 flex justify-end">
                        <button
                            onClick={handleAddFilter}
                            disabled={!selectedTable}
                            className="text-xs flex items-center gap-1.5 bg-violet-50 dark:bg-violet-900/30 text-violet-600 dark:text-violet-300 px-3 py-1.5 rounded-full hover:bg-violet-100 dark:hover:bg-violet-900/50 transition-colors font-medium disabled:opacity-50"
                        >
                            <Plus className="w-3.5 h-3.5" /> Adicionar Filtro
                        </button>
                    </div>

                    <div className="space-y-3">
                        {filters.length === 0 && (
                            <div className="text-center p-8 border-2 border-dashed border-slate-200 dark:border-slate-700 rounded-lg text-slate-400 text-sm">
                                Nenhum filtro definido
                            </div>
                        )}

                        {filters.map((filter, idx) => (
                            <div key={idx} className="group relative bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-3 shadow-xs hover:shadow-md transition-all animate-in slide-in-from-left-2 duration-200">

                                {/* Logic Connector for items > 0 */}
                                {idx > 0 && (
                                    <div className="absolute -top-3 left-4">
                                        <select
                                            value={filter.logic}
                                            onChange={(e) => handleFilterChange(idx, 'logic', e.target.value)}
                                            className="text-[10px] font-bold uppercase tracking-wider bg-slate-100 dark:bg-slate-900 border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-400 rounded-sm px-2 py-0.5 focus:outline-hidden focus:border-violet-500 cursor-pointer hover:bg-slate-200 dark:hover:bg-slate-800"
                                        >
                                            <option value="AND">E (AND)</option>
                                            <option value="OR">OU (OR)</option>
                                        </select>
                                    </div>
                                )}

                                <div className="flex flex-wrap gap-3 items-center mt-1">
                                    <div className="flex-1 min-w-[150px]">
                                        <select
                                            value={filter.column}
                                            onChange={(e) => handleFilterChange(idx, 'column', e.target.value)}
                                            className="w-full p-2 border rounded-md text-sm bg-slate-50 dark:bg-slate-900/50 border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 transition-all outline-hidden"
                                        >
                                            <option value="">Selecione o campo...</option>
                                            {columns.map(c => (
                                                <option key={c.column_name} value={c.column_name}>{c.column_name}</option>
                                            ))}
                                        </select>
                                    </div>

                                    <div className="w-[140px]">
                                        <select
                                            value={filter.operator}
                                            onChange={(e) => handleFilterChange(idx, 'operator', e.target.value)}
                                            className="w-full p-2 border rounded-md text-sm bg-slate-50 dark:bg-slate-900/50 border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 transition-all outline-hidden"
                                        >
                                            {OPERATORS.map(op => (
                                                <option key={op.value} value={op.value}>{op.label}</option>
                                            ))}
                                        </select>
                                    </div>

                                    {operatorNeedsValue(filter.operator) && (
                                        <div className="flex-1 flex gap-2 min-w-[200px]">
                                            <input
                                                type="text"
                                                value={filter.value}
                                                onChange={(e) => handleFilterChange(idx, 'value', e.target.value)}
                                                placeholder={filter.operator === 'IN' || filter.operator === 'NOT IN' ? 'Ex: 1, 2, 3' : 'Valor'}
                                                className="flex-1 p-2 border rounded-md text-sm bg-slate-50 dark:bg-slate-900/50 border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 transition-all outline-hidden placeholder:text-slate-400"
                                            />
                                            {filter.operator === 'BETWEEN' && (
                                                <>
                                                    <span className="self-center text-slate-400 text-sm">e</span>
                                                    <input
                                                        type="text"
                                                        value={filter.value2 || ''}
                                                        onChange={(e) => handleFilterChange(idx, 'value2', e.target.value)}
                                                        placeholder="Valor 2"
                                                        className="flex-1 p-2 border rounded-md text-sm bg-slate-50 dark:bg-slate-900/50 border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 transition-all outline-hidden placeholder:text-slate-400"
                                                    />
                                                </>
                                            )}
                                        </div>
                                    )}

                                    <button
                                        onClick={() => handleRemoveFilter(idx)}
                                        className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md transition-colors opacity-0 group-hover:opacity-100"
                                        title="Remover filtro"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                </Section>

                {/* 4. HAVING (only show if aggregations exist) */}
                {hasAggregations && (
                    <Section
                        title="4. Filtros Pós-Agregação (HAVING)"
                        icon={Filter}
                        badge={havingFilters.length > 0 ? havingFilters.length : null}
                        defaultOpen={false}
                    >
                        <div className="flex justify-end mb-3">
                            <button
                                onClick={handleAddHavingFilter}
                                className="text-xs flex items-center gap-1 text-violet-600 hover:text-violet-700 dark:text-violet-400 font-medium"
                            >
                                <Plus className="w-3 h-3" /> Adicionar
                            </button>
                        </div>

                        <div className="space-y-2">
                            {havingFilters.map((filter, idx) => (
                                <div key={idx} className="flex flex-wrap gap-2 items-center p-2 bg-amber-50 dark:bg-amber-900/20 rounded-sm animate-in slide-in-from-left-2 duration-200">
                                    <select
                                        value={filter.aggregation}
                                        onChange={(e) => handleHavingFilterChange(idx, 'aggregation', e.target.value)}
                                        className="w-24 p-2 border rounded-md text-sm bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                    >
                                        {AGGREGATIONS.filter(a => a.value).map(agg => (
                                            <option key={agg.value} value={agg.value}>{agg.value}</option>
                                        ))}
                                    </select>
                                    <span className="text-slate-500">(</span>
                                    <select
                                        value={filter.column}
                                        onChange={(e) => handleHavingFilterChange(idx, 'column', e.target.value)}
                                        className="flex-1 min-w-[100px] p-2 border rounded-md text-sm bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                    >
                                        <option value="*">*</option>
                                        {columns.map(c => (
                                            <option key={c.column_name} value={c.column_name}>{c.column_name}</option>
                                        ))}
                                    </select>
                                    <span className="text-slate-500">)</span>
                                    <select
                                        value={filter.operator}
                                        onChange={(e) => handleHavingFilterChange(idx, 'operator', e.target.value)}
                                        className="w-20 p-2 border rounded-md text-sm bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                    >
                                        <option value=">">&gt;</option>
                                        <option value=">=">&gt;=</option>
                                        <option value="<">&lt;</option>
                                        <option value="<=">&lt;=</option>
                                        <option value="=">=</option>
                                        <option value="!=">!=</option>
                                    </select>
                                    <input
                                        type="text"
                                        value={filter.value}
                                        onChange={(e) => handleHavingFilterChange(idx, 'value', e.target.value)}
                                        placeholder="Valor"
                                        className="w-20 p-2 border rounded-md text-sm bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                    />
                                    <button onClick={() => handleRemoveHavingFilter(idx)} className="text-red-400 hover:text-red-600 p-1">
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            ))}
                        </div>
                    </Section>
                )}

                {/* 5. ORDER BY */}
                <Section
                    title={hasAggregations ? "5. Ordenação (ORDER BY)" : "4. Ordenação (ORDER BY)"}
                    icon={ArrowUpDown}
                    badge={sortColumns.length > 0 ? sortColumns.length : null}
                    defaultOpen={false}
                >
                    <div className="flex justify-end mb-3">
                        <button
                            onClick={handleAddSort}
                            disabled={!selectedTable}
                            className="text-xs flex items-center gap-1 text-violet-600 hover:text-violet-700 dark:text-violet-400 font-medium disabled:opacity-50"
                        >
                            <Plus className="w-3 h-3" /> Adicionar
                        </button>
                    </div>

                    <div className="space-y-2">
                        {sortColumns.map((sort, idx) => (
                            <div key={idx} className="flex gap-2 items-center animate-in slide-in-from-left-2 duration-200">
                                <select
                                    value={sort.column}
                                    onChange={(e) => handleSortChange(idx, 'column', e.target.value)}
                                    className="flex-1 p-2 border rounded-md text-sm bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                >
                                    <option value="">Campo</option>
                                    {columns.map(c => (
                                        <option key={c.column_name} value={c.column_name}>{c.column_name}</option>
                                    ))}
                                </select>
                                <select
                                    value={sort.direction}
                                    onChange={(e) => handleSortChange(idx, 'direction', e.target.value)}
                                    className="w-40 p-2 border rounded-md text-sm bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100"
                                >
                                    {SORT_DIRECTIONS.map(dir => (
                                        <option key={dir.value} value={dir.value}>{dir.label}</option>
                                    ))}
                                </select>
                                <button onClick={() => handleRemoveSort(idx)} className="text-red-400 hover:text-red-600 p-1">
                                    <Trash2 className="w-4 h-4" />
                                </button>
                            </div>
                        ))}
                    </div>
                </Section>
            </div>

            {/* Right Panel - SQL Preview & Execute */}
            <div className="flex flex-col gap-4 flex-1 min-w-0">
                {/* SQL Preview */}
                <div className="bg-slate-900 text-slate-200 p-4 rounded-lg flex-1 font-mono text-sm overflow-auto relative group min-h-[200px]">
                    <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                            onClick={handleCopySQL}
                            disabled={!generatedSQL}
                            className={`p-1.5 rounded-sm text-white transition-colors ${copySuccess ? 'bg-green-600' : 'bg-slate-700 hover:bg-slate-600'}`}
                            title={copySuccess ? 'Copiado!' : 'Copiar SQL'}
                        >
                            <Copy className="w-4 h-4" />
                        </button>
                        <button
                            onClick={generateSQL}
                            className="p-1.5 bg-slate-700 rounded-sm hover:bg-slate-600 text-white"
                            title="Atualizar SQL"
                        >
                            <RefreshCw className="w-4 h-4" />
                        </button>
                    </div>
                    <pre className="whitespace-pre-wrap text-sm leading-relaxed">
                        {generatedSQL ? (
                            <code>
                                {generatedSQL.split('\n').map((line, i) => (
                                    <div key={i}>
                                        {line.split(/(\b(?:SELECT|DISTINCT|FROM|WHERE|AND|OR|GROUP BY|HAVING|ORDER BY|ASC|DESC|LIKE|BETWEEN|IN|IS NULL|IS NOT NULL|COUNT|SUM|AVG|MIN|MAX)\b)/gi).map((part, j) => {
                                            const keywords = ['SELECT', 'DISTINCT', 'FROM', 'WHERE', 'AND', 'OR', 'GROUP BY', 'HAVING', 'ORDER BY', 'ASC', 'DESC', 'LIKE', 'BETWEEN', 'IN', 'IS NULL', 'IS NOT NULL'];
                                            const aggregates = ['COUNT', 'SUM', 'AVG', 'MIN', 'MAX'];

                                            if (keywords.includes(part.toUpperCase())) {
                                                return <span key={j} className="text-violet-400 font-semibold">{part}</span>;
                                            }
                                            if (aggregates.includes(part.toUpperCase())) {
                                                return <span key={j} className="text-amber-400">{part}</span>;
                                            }
                                            return <span key={j}>{part}</span>;
                                        })}
                                    </div>
                                ))}
                            </code>
                        ) : (
                            <span className="text-slate-500">-- Selecione uma tabela para gerar SQL</span>
                        )}
                    </pre>
                </div>

                {/* Validation Panel */}
                {(validationErrors.length > 0 || validationWarnings.length > 0) && (
                    <div className="space-y-2 animate-in slide-in-from-top-2 duration-200">
                        {validationErrors.length > 0 && (
                            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
                                <div className="flex items-center gap-2 text-red-600 dark:text-red-400 font-medium text-sm mb-2">
                                    <AlertCircle className="w-4 h-4" />
                                    <span>Erros que impedem a execução</span>
                                </div>
                                <ul className="text-sm text-red-600 dark:text-red-400 space-y-1">
                                    {validationErrors.map((err, idx) => (
                                        <li key={idx} className="flex items-start gap-2">
                                            <span className="text-red-400">•</span>
                                            <span>{err}</span>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}
                        {validationWarnings.length > 0 && (
                            <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3">
                                <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400 font-medium text-sm mb-2">
                                    <AlertTriangle className="w-4 h-4" />
                                    <span>Avisos (não bloqueantes)</span>
                                </div>
                                <ul className="text-sm text-amber-600 dark:text-amber-400 space-y-1">
                                    {validationWarnings.map((warn, idx) => (
                                        <li key={idx} className="flex items-start gap-2">
                                            <span className="text-amber-400">•</span>
                                            <span>{warn}</span>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </div>
                )}

                {/* Validation Success Indicator */}
                {selectedTable && validationErrors.length === 0 && validationWarnings.length === 0 && generatedSQL && (
                    <div className="flex items-center gap-2 text-green-600 dark:text-green-400 text-sm bg-green-50 dark:bg-green-900/20 px-3 py-2 rounded-lg">
                        <CheckCircle className="w-4 h-4" />
                        <span>Consulta válida e pronta para executar</span>
                    </div>
                )}

                {/* Action Bar */}
                <div className="flex items-center gap-4 bg-slate-50 dark:bg-slate-800 p-4 rounded-lg border border-slate-200 dark:border-slate-700">
                    <div className="flex items-center gap-2">
                        <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Limite:</label>
                        <select
                            value={limit}
                            onChange={(e) => setLimit(e.target.value === 'ALL' ? 'ALL' : Number(e.target.value))}
                            className="p-2 border rounded-md bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-slate-100 text-sm focus:ring-2 focus:ring-violet-500"
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
                    <button
                        onClick={() => onRun(generatedSQL)}
                        disabled={!generatedSQL || validationErrors.length > 0}
                        className={`flex-1 px-6 py-3 rounded-md flex items-center justify-center gap-2 font-medium shadow-xs transition-all hover:shadow-md ${validationErrors.length > 0
                            ? 'bg-red-400 text-white cursor-not-allowed opacity-60'
                            : 'bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-50'
                            }`}
                        title={validationErrors.length > 0 ? 'Corrija os erros antes de executar' : ''}
                    >
                        {validationErrors.length > 0 ? (
                            <>
                                <AlertCircle className="w-4 h-4" /> Corrija os erros
                            </>
                        ) : (
                            <>
                                <Play className="w-4 h-4" /> Executar Consulta
                            </>
                        )}
                    </button>
                </div>

                {error && (
                    <div className="bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 p-3 rounded-md text-sm">
                        {error}
                    </div>
                )}
            </div>
        </div>
    );
};

export default VisualQueryBuilder;
