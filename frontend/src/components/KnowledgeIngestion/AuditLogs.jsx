import React, { useEffect, useState } from 'react';
import { ingestionAPI } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import { ClipboardList, Loader2, Filter, Search } from 'lucide-react';

const ACTION_COLORS = {
  insert:   'emerald',
  update:   'blue',
  merge:    'violet',
  ignore:   'slate',
  rollback: 'red',
  auto_merge: 'cyan',
};

function formatDate(dt) {
  if (!dt) return '–';
  return new Date(dt).toLocaleString('en-IN', {
    day: '2-digit', month: 'short',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
}

export default function AuditLogs() {
  const { showToast } = useToast();
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState('');
  const [search, setSearch] = useState('');

  useEffect(() => { loadLogs(); }, [filterType]);

  const loadLogs = async () => {
    setLoading(true);
    try {
      const params = { limit: 200 };
      if (filterType) params.entity_type = filterType;
      const res = await ingestionAPI.getAuditLogs(params);
      setLogs(res.data || []);
    } catch {
      showToast('Failed to load audit logs', 'error');
    } finally {
      setLoading(false);
    }
  };

  const filtered = search
    ? logs.filter((l) =>
        l.entity_type?.includes(search.toLowerCase()) ||
        l.action?.includes(search.toLowerCase()) ||
        l.user?.includes(search.toLowerCase()) ||
        l.entity_id?.includes(search)
      )
    : logs;

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      <header>
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 bg-gradient-to-br from-slate-700 to-slate-900 rounded-xl flex items-center justify-center shadow-lg">
            <ClipboardList size={22} className="text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-black text-slate-800">Audit Logs</h1>
            <p className="text-slate-500 text-sm">Complete trail of all knowledge ingestion actions</p>
          </div>
        </div>
        <div className="h-1 w-24 bg-gradient-to-r from-slate-600 to-slate-800 rounded-full mt-3" />
      </header>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="flex items-center gap-2 bg-white rounded-xl px-4 py-2 shadow-sm border border-slate-100 flex-1 min-w-48">
          <Search size={16} className="text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search logs..."
            className="bg-transparent text-sm text-slate-700 outline-none flex-1 placeholder:text-slate-300"
          />
        </div>
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="bg-white rounded-xl px-4 py-2 shadow-sm border border-slate-100 text-sm text-slate-700 outline-none cursor-pointer"
        >
          <option value="">All Types</option>
          {['departments', 'faculty', 'subjects', 'rooms', 'classes', 'batches', 'session'].map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <div className="flex justify-center py-20"><Loader2 size={32} className="animate-spin text-slate-400" /></div>
      ) : (
        <div className="bg-white rounded-3xl shadow-xl border border-slate-100 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  {['Timestamp', 'Entity Type', 'Action', 'Confidence', 'User', 'Decision', 'Reason'].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-black text-slate-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {filtered.length === 0 ? (
                  <tr><td colSpan={7} className="text-center py-12 text-slate-400">No audit logs found</td></tr>
                ) : filtered.map((log, idx) => {
                  const color = ACTION_COLORS[log.action] || 'slate';
                  return (
                    <tr key={idx} className="hover:bg-slate-50/60 transition-colors">
                      <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">{formatDate(log.timestamp)}</td>
                      <td className="px-4 py-3">
                        <span className="text-xs font-bold text-slate-700 capitalize">{log.entity_type}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`text-xs font-black px-2 py-1 bg-${color}-100 text-${color}-700 rounded-full capitalize`}>
                          {log.action}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs font-black text-slate-700">
                        {log.confidence_score ? `${Number(log.confidence_score).toFixed(1)}%` : '–'}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500">{log.user || '–'}</td>
                      <td className="px-4 py-3 text-xs text-slate-600">{log.user_decision || '–'}</td>
                      <td className="px-4 py-3 text-xs text-slate-400 max-w-xs truncate">{log.reason || '–'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="px-4 py-3 bg-slate-50 border-t border-slate-100 text-xs text-slate-400 font-bold">
            Showing {filtered.length} of {logs.length} entries
          </div>
        </div>
      )}
    </div>
  );
}
