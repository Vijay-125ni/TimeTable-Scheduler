import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ingestionAPI } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import {
  FileText, Cpu, Search, CheckCircle2, Loader2,
  ChevronRight, AlertCircle
} from 'lucide-react';

const STAGES = [
  { key: 'parsing',       label: 'Document Parsing',       icon: FileText,     color: 'violet' },
  { key: 'ai_extraction', label: 'AI Entity Extraction',   icon: Cpu,          color: 'indigo' },
  { key: 'merging',       label: 'Cross-Doc Merging',       icon: Search,       color: 'blue' },
  { key: 'deduplication', label: 'Duplicate Detection',    icon: Search,       color: 'cyan' },
  { key: 'ready',         label: 'Review Ready',           icon: CheckCircle2, color: 'emerald' },
];

const STAGE_INDEX = Object.fromEntries(STAGES.map((s, i) => [s.key, i]));

const colorMap = {
  violet: { bg: 'bg-violet-500', text: 'text-violet-600', ring: 'ring-violet-200', light: 'bg-violet-50' },
  indigo: { bg: 'bg-indigo-500', text: 'text-indigo-600', ring: 'ring-indigo-200', light: 'bg-indigo-50' },
  blue:   { bg: 'bg-blue-500',   text: 'text-blue-600',   ring: 'ring-blue-200',   light: 'bg-blue-50' },
  cyan:   { bg: 'bg-cyan-500',   text: 'text-cyan-600',   ring: 'ring-cyan-200',   light: 'bg-cyan-50' },
  emerald:{ bg: 'bg-emerald-500',text: 'text-emerald-600',ring: 'ring-emerald-200',light: 'bg-emerald-50' },
};

export default function ProcessingPage() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [currentStage, setCurrentStage] = useState('parsing');
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('Starting processing pipeline...');
  const [stats, setStats] = useState(null);
  const [logs, setLogs] = useState([]);
  const [done, setDone] = useState(false);
  const esRef = useRef(null);
  const logsEndRef = useRef(null);

  useEffect(() => {
    if (!sessionId) return;
    const url = ingestionAPI.getProgress(sessionId);
    const token = localStorage.getItem('token');

    // SSE connection for live progress
    const es = new EventSource(`${url}?token=${token}`);
    esRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setCurrentStage(data.stage || 'parsing');
        setProgress(data.progress ?? 0);
        setMessage(data.message || '');
        setLogs((prev) => [...prev.slice(-49), { ...data, id: Date.now() }]);

        if (data.stage === 'ready') {
          setStats(data.stats || null);
          setDone(true);
          es.close();
        }
        if (data.stage === 'timeout') {
          showToast('Processing timed out. Check session status.', 'error');
          es.close();
        }
      } catch {}
    };

    es.onerror = () => {
      // Fallback: poll status
      es.close();
      pollStatus();
    };

    return () => { es.close(); };
  }, [sessionId]);

  const pollStatus = async () => {
    try {
      const res = await ingestionAPI.getSessionStatus(sessionId);
      const session = res.data;
      if (session.status === 'awaiting_review' || session.status === 'completed') {
        setDone(true);
        setProgress(100);
        setStats(session.stats);
      }
    } catch {}
  };

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const currentStageIdx = STAGE_INDEX[currentStage] ?? 0;

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <header>
        <h1 className="text-3xl font-black text-slate-800">AI Processing Pipeline</h1>
        <p className="text-slate-500 text-sm mt-1">Session: <code className="bg-slate-100 px-2 py-0.5 rounded text-xs">{sessionId}</code></p>
        <div className="h-1 w-24 bg-gradient-to-r from-violet-500 to-indigo-500 rounded-full mt-3" />
      </header>

      {/* Overall progress bar */}
      <div className="bg-white rounded-3xl p-6 shadow-xl border border-slate-100">
        <div className="flex justify-between items-center mb-3">
          <span className="font-black text-slate-700 text-sm">Overall Progress</span>
          <span className="text-violet-600 font-black text-lg">{progress}%</span>
        </div>
        <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-violet-500 to-indigo-500 rounded-full transition-all duration-700 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="text-sm text-slate-500 mt-3 flex items-center gap-2">
          {!done && <Loader2 size={14} className="animate-spin text-violet-500" />}
          {message}
        </p>
      </div>

      {/* Stage pipeline */}
      <div className="bg-white rounded-3xl p-6 shadow-xl border border-slate-100">
        <h3 className="font-black text-slate-700 mb-5 text-sm uppercase tracking-wider">Processing Stages</h3>
        <div className="space-y-3">
          {STAGES.map((stage, idx) => {
            const { icon: Icon, color } = stage;
            const c = colorMap[color];
            const isActive = idx === currentStageIdx;
            const isDone = idx < currentStageIdx || (done && idx <= currentStageIdx);
            const isPending = idx > currentStageIdx;

            return (
              <div
                key={stage.key}
                className={`flex items-center gap-4 p-4 rounded-2xl transition-all duration-500
                  ${isActive ? `${c.light} ring-2 ${c.ring}` : isDone ? 'bg-emerald-50' : 'bg-slate-50'}`}
              >
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 transition-all
                  ${isDone ? 'bg-emerald-500' : isActive ? c.bg : 'bg-slate-200'}`}>
                  {isDone ? (
                    <CheckCircle2 size={20} className="text-white" />
                  ) : isActive ? (
                    <Loader2 size={20} className="text-white animate-spin" />
                  ) : (
                    <Icon size={20} className="text-slate-400" />
                  )}
                </div>
                <div className="flex-1">
                  <p className={`font-black text-sm ${isDone ? 'text-emerald-700' : isActive ? c.text : 'text-slate-400'}`}>
                    {stage.label}
                  </p>
                  {isActive && (
                    <p className="text-xs text-slate-500 mt-0.5 animate-pulse">{message}</p>
                  )}
                  {isDone && (
                    <p className="text-xs text-emerald-600 mt-0.5">Completed</p>
                  )}
                </div>
                {(isDone || isActive) && (
                  <ChevronRight size={16} className={isDone ? 'text-emerald-400' : c.text} />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Stats (on completion) */}
      {done && stats && (
        <div className="bg-gradient-to-br from-emerald-50 to-teal-50 rounded-3xl p-6 border border-emerald-100 shadow-xl">
          <h3 className="font-black text-emerald-800 mb-4 flex items-center gap-2">
            <CheckCircle2 size={20} className="text-emerald-500" />
            Analysis Complete!
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
            {[
              { label: 'New Records', value: stats.new_records ?? 0, color: 'emerald' },
              { label: 'Auto-Merged', value: stats.auto_merged ?? 0, color: 'blue' },
              { label: 'Needs Review', value: (stats.needs_review ?? 0) + (stats.conflicts ?? 0), color: 'amber' },
              { label: 'Missing Data', value: stats.missing_fields ?? 0, color: 'red' },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-white rounded-2xl p-4 text-center shadow-sm">
                <p className={`text-3xl font-black text-${color}-600`}>{value}</p>
                <p className="text-xs text-slate-500 font-bold mt-1">{label}</p>
              </div>
            ))}
          </div>
          <button
            onClick={() => navigate(`/knowledge/review/${sessionId}`)}
            className="w-full py-3.5 bg-gradient-to-r from-emerald-600 to-teal-600 text-white font-black rounded-2xl hover:from-emerald-700 hover:to-teal-700 transition-all shadow-lg shadow-emerald-500/30 text-sm"
          >
            Go to Review Dashboard →
          </button>
        </div>
      )}

      {/* Live logs */}
      {logs.length > 0 && (
        <div className="bg-slate-900 rounded-3xl p-5 shadow-xl">
          <h3 className="font-black text-slate-400 text-xs uppercase tracking-wider mb-3">Live Processing Log</h3>
          <div className="space-y-1 max-h-40 overflow-y-auto visible-scrollbar font-mono text-xs">
            {logs.map((log) => (
              <div key={log.id} className="text-slate-300">
                <span className="text-slate-500">[{new Date(log.ts).toLocaleTimeString()}] </span>
                <span className={log.stage === 'ready' ? 'text-emerald-400' : 'text-slate-300'}>{log.message}</span>
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </div>
      )}
    </div>
  );
}
