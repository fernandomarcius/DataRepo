import React from 'react';
import { Download } from 'lucide-react';

const ResultsTable = ({ data }) => {
    const [currentPage, setCurrentPage] = React.useState(1);
    const [itemsPerPage, setItemsPerPage] = React.useState(10);

    // Reset to page 1 when data changes
    React.useEffect(() => {
        setCurrentPage(1);
    }, [data]);

    if (!data || data.length === 0) {
        return <div className="text-gray-500 dark:text-gray-400 italic p-4">No results to display</div>;
    }

    const columns = Object.keys(data[0]);
    const totalPages = Math.ceil(data.length / itemsPerPage);
    const startIndex = (currentPage - 1) * itemsPerPage;
    const currentData = data.slice(startIndex, startIndex + itemsPerPage);

    const handleExportCSV = () => {
        if (!data || data.length === 0) return;

        const headers = Object.keys(data[0]);
        const csvContent = [
            headers.join(','),
            ...data.map(row => headers.map(header => {
                const cell = row[header] === null || row[header] === undefined ? '' : row[header];
                // Escape quotes and wrap in quotes if necessary
                const stringCell = String(cell);
                return `"${stringCell.replace(/"/g, '""')}"`;
            }).join(','))
        ].join('\n');

        const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', 'query_results.csv');
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    return (
        <div className="flex flex-col gap-4 w-full max-w-full">
            <div className="flex justify-end px-2">
                <button
                    onClick={handleExportCSV}
                    className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-violet-600 dark:text-violet-300 bg-violet-50 dark:bg-violet-900/30 hover:bg-violet-100 dark:hover:bg-violet-900/50 rounded-md transition-colors"
                    title="Export all rows to CSV"
                >
                    <Download className="w-4 h-4" />
                    Export CSV ({data.length} rows)
                </button>
            </div>

            <div className="overflow-x-auto border border-gray-200 dark:border-slate-700 rounded-lg w-full">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-slate-700">
                    <thead className="bg-gray-50 dark:bg-slate-700/50">
                        <tr>
                            {columns.map((col) => (
                                <th key={col} className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-slate-300 uppercase tracking-wider whitespace-nowrap">
                                    {col}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="bg-white dark:bg-slate-800 divide-y divide-gray-200 dark:divide-slate-700">
                        {currentData.map((row, idx) => (
                            <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-slate-700/50 transition-colors">
                                {columns.map((col) => (
                                    <td key={`${idx}-${col}`} className="px-4 py-2 text-sm text-gray-900 dark:text-slate-200 min-w-[150px] whitespace-nowrap">
                                        {row[col]}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Pagination Controls */}
            <div className="flex items-center justify-between px-2 text-gray-600 dark:text-gray-400">
                <div className="flex items-center gap-4 text-sm">
                    <span>
                        Showing {startIndex + 1} to {Math.min(startIndex + itemsPerPage, data.length)} of {data.length} results
                    </span>
                    <div className="flex items-center gap-2">
                        <span>Rows per page:</span>
                        <select
                            value={itemsPerPage}
                            onChange={(e) => {
                                setItemsPerPage(Number(e.target.value));
                                setCurrentPage(1);
                            }}
                            className="border border-gray-300 dark:border-slate-600 rounded-sm p-1 text-sm bg-white dark:bg-slate-800 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-violet-500"
                        >
                            <option value={10}>10</option>
                            <option value={25}>25</option>
                            <option value={50}>50</option>
                            <option value={100}>100</option>
                        </select>
                    </div>
                </div>

                {totalPages > 1 && (
                    <div className="flex gap-2">
                        <button
                            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                            disabled={currentPage === 1}
                            className="px-3 py-1 border border-gray-300 dark:border-slate-600 rounded-sm hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
                        >
                            Previous
                        </button>
                        <span className="flex items-center px-2 text-sm font-medium text-gray-600 dark:text-gray-400">
                            Page {currentPage} of {totalPages}
                        </span>
                        <button
                            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                            disabled={currentPage === totalPages}
                            className="px-3 py-1 border border-gray-300 dark:border-slate-600 rounded-sm hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
                        >
                            Next
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
};

export default ResultsTable;
