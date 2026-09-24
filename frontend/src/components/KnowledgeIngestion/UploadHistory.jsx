import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ingestionAPI } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import {
  History, Clock, CheckCircle2, AlertCircle, RotateCcw,
  Loader2, FileText, ChevronRight, XCircle
} from 'lucide-react';

const STATUS_CONFIG = {
  processing:      { label: 'Processing',     color: 'blue',    icon: Loader2, spin: true },
  awaiting_review: { label: 'Awaiting Review',color: 'amber',   icon: Clock },
  completed:       { label: 'Completed',      color: 'emerald', icon: CheckCircle2 },
  rolled_back:     { label: 'Rolled Back',    color: 'red',     icon: RotateCcw },
  failed:          { label: 'Failed',         color: 'red',     icon: XCircle },
};

function formatDate(dt) {
  if (!dt) return '–';
  return new Date(dt).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}

export default function UploadHistory() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [rolling, setRolling] = useState(null);

  useEffect(() => { loadHistory(); }, []);

  const loadHistory = async () => {
    try {
      const res = await ingestionAPI.getHistory();
      setSessions(res.data || []);
    } catch {
      showToast('Failed to load upload history', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleRollback = async (sessionId) => {
    if (!window.confirm('Roll back all changes from this session? This cannot be undone.')) return;
    setRolling(sessionId);
    try {
      const res = await ingestionAPI.rollbackSession(sessionId);
      showToast(`Rolled back ${res.data.rolled_back} records`, 'success');
      loadHistory();
    } catch {
      showToast('Rollback failed', 'error');
    } finally {
      setRolling(null);
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Loader2 size={32} className="animate-spin text-violet-500" /></div>;
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <header>
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 bg-gradient-to-br from-indigo-600 to-blue-600 rounded-xl flex items-center justify-center shadow-lg">
            <History size={22} className="text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-black text-slate-800">Upload History</h1>
            <p className="text-slate-500 text-sm">All knowledge ingestion sessions with rollback support</p>
          </div>
        </div>
        <div className="h-1 w-24 bg-gradient-to-r from-indigo-500 to-blue-500 rounded-full mt-3" />
      </header>

      {sessions.length === 0 ? (
        <div className="bg-white rounded-3xl p-16 shadow-xl border border-slate-100 text-center">
          <History size={48} className="mx-auto text-slate-200 mb-4" />
          <p className="text-slate-400 font-bold">No upload sessions yet</p>
          <button onClick={() => navigate('/knowledge/upload')}
            className="mt-4 px-5 py-2.5 bg-violet-600 text-white text-sm font-bold rounded-xl hover:bg-violet-700 transition-colors">
            Start First Upload
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {sessions.map((session) => {
            const cfg = STATUS_CONFIG[session.status] || STATUS_CONFIG.failed;
            const { icon: Icon, color, spin } = cfg;

            return (
              <div key={session.session_id} className="bg-white rounded-2xl shadow-sm border border-slate-100 hover:shadow-md transition-all overflow-hidden">
                <div className="flex items-center gap-4 p-5">
                  {/* Status icon */}
                  <div className={`w-11 h-11 rounded-xl bg-${color}-50 flex items-center justify-center shrink-0`}>
                    <Icon size={22} className={`text-${color}-500 ${spin ? 'animate-spin' : ''}`} />
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-black text-slate-800 text-sm">
                        {session.file_names?.slice(0, 2).join(', ') || session.session_id}
                        {session.file_names?.length > 2 && ` +${session.file_names.length - 2} more`}
                      </p>
                      <span className={`text-xs font-bold px-2 py-0.5 bg-${color}-100 text-${color}-700 rounded-full`}>
                        {cfg.label}
                      </span>
                    </div>
                    <div className="flex gap-4 mt-1 text-xs text-slate-400">
                      <span>By {session.user}</span>
                      <span>{formatDate(session.started_at)}</span>
                      {session.file_names?.length && <span>{session.file_names.length} file{session.file_names.length > 1 ? 's' : ''}</span>}
                    </div>
                    {session.stats && (
                      <div className="flex gap-3 mt-2 text-xs">
                        {Object.entries(session.stats).map(([k, v]) => v > 0 && (
                          <span key={k} className="text-slate-500">
                            <span className="font-black text-slate-700">{v}</span> {k}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 shrink-0">
                    {session.status === 'awaiting_review' && (
                      <button
                        onClick={() => navigate(`/knowledge/review/${session.session_id}`)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-500 text-white text-xs font-bold rounded-xl hover:bg-amber-600 transition-colors"
                      >
                        Review <ChevronRight size={14} />
                      </button>
                    )}
                    {session.status === 'completed' && (
                      <button
                        onClick={() => handleRollback(session.session_id)}
                        disabled={rolling === session.session_id}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 text-slate-600 text-xs font-bold rounded-xl hover:bg-red-50 hover:text-red-600 transition-colors disabled:opacity-60"
                      >
                        {rolling === session.session_id ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <RotateCcw size={12} />
                        )}
                        Rollback
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
