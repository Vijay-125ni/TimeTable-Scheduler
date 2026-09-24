import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ingestionAPI } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import {
  CheckCircle2, XCircle, GitMerge, Plus, AlertTriangle,
  ChevronDown, ChevronUp, Filter, Loader2, Send, Zap
} from 'lucide-react';

const ACTION_CONFIG = {
  approve:    { label: 'Approve',    color: 'bg-emerald-500 text-white', icon: CheckCircle2 },
  merge:      { label: 'Merge',      color: 'bg-blue-500 text-white',    icon: GitMerge },
  replace:    { label: 'Replace',    color: 'bg-amber-500 text-white',   icon: Zap },
  ignore:     { label: 'Ignore',     color: 'bg-slate-300 text-slate-700', icon: XCircle },
  create_new: { label: 'Create New', color: 'bg-violet-500 text-white',  icon: Plus },
};

const ENTITY_COLORS = {
  departments: 'violet', faculty: 'blue', subjects: 'emerald',
  rooms: 'amber', classes: 'cyan', batches: 'rose',
};

function ScoreBadge({ score }) {
  const color = score >= 99 ? 'emerald' : score >= 95 ? 'blue' : score >= 85 ? 'amber' : 'red';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-black bg-${color}-100 text-${color}-700`}>
      {score.toFixed(1)}%
    </span>
  );
}

function EntityCard({ entry, onDecision, decisions }) {
  const [expanded, setExpanded] = useState(false);
  const entityType = entry.entity_type;
  const newEntity = entry.new_entity || {};
  const existingEntity = entry.existing_entity;
  const conflicts = entry.conflicting_fields || [];
  const missing = entry.missing_fields || [];
  const score = entry.score || 0;
  const action = entry.action;
  const decision = decisions[entry._key] || (action === 'auto_merge' ? 'merge' : action === 'new_record' ? 'approve' : null);
  const color = ENTITY_COLORS[entityType] || 'slate';

  const primaryLabel = newEntity.name || newEntity.email || newEntity.code || '(unnamed)';

  return (
    <div className={`bg-white rounded-2xl border-2 transition-all duration-200
      ${decision === 'ignore' ? 'border-slate-100 opacity-60' : `border-${color}-100`}
      shadow-sm hover:shadow-md`}>
      {/* Card Header */}
      <div className="flex items-center gap-3 p-4">
        <div className={`shrink-0 px-2.5 py-1 bg-${color}-50 text-${color}-700 rounded-lg text-xs font-black uppercase tracking-wide`}>
          {entityType}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-black text-slate-800 text-sm truncate">{primaryLabel}</p>
          {newEntity.code && newEntity.code !== primaryLabel && (
            <p className="text-xs text-slate-400">{newEntity.code}</p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {score > 0 && <ScoreBadge score={score} />}
          {conflicts.length > 0 && (
            <span className="text-xs font-bold px-2 py-0.5 bg-red-100 text-red-700 rounded-full">
              {conflicts.length} conflict{conflicts.length > 1 ? 's' : ''}
            </span>
          )}
          {missing.length > 0 && (
            <span className="text-xs font-bold px-2 py-0.5 bg-amber-100 text-amber-700 rounded-full">
              {missing.length} missing
            </span>
          )}
          <button onClick={() => setExpanded(!expanded)} className="text-slate-400 hover:text-slate-600 transition-colors p-1">
            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="border-t border-slate-50 px-4 pb-4 space-y-3">
          {/* Fields comparison */}
          {existingEntity && (
            <div className="mt-3">
              <p className="text-xs font-black text-slate-500 uppercase tracking-wider mb-2">Field Comparison</p>
              <div className="grid grid-cols-2 gap-2">
                <div className="bg-slate-50 rounded-xl p-3">
                  <p className="text-xs font-bold text-slate-400 mb-2">In Database</p>
                  {Object.entries(existingEntity).filter(([k]) => !['_id', 'id', 'created_at', 'updated_at'].includes(k)).slice(0, 6).map(([k, v]) => (
                    <div key={k} className={`text-xs py-0.5 ${conflicts.find(c => c.field === k) ? 'text-red-600 font-bold' : 'text-slate-600'}`}>
                      <span className="text-slate-400">{k}: </span>{String(v || '–')}
                    </div>
                  ))}
                </div>
                <div className="bg-violet-50 rounded-xl p-3">
                  <p className="text-xs font-bold text-violet-400 mb-2">From Document</p>
                  {Object.entries(newEntity).filter(([k]) => !['_id', 'id'].includes(k)).slice(0, 6).map(([k, v]) => (
                    <div key={k} className={`text-xs py-0.5 ${conflicts.find(c => c.field === k) ? 'text-red-600 font-bold' : 'text-violet-700'}`}>
                      <span className="text-violet-400">{k}: </span>{String(v || '–')}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Missing fields */}
          {missing.length > 0 && (
            <div className="bg-amber-50 rounded-xl p-3">
              <p className="text-xs font-black text-amber-700 mb-1 flex items-center gap-1">
                <AlertTriangle size={12} /> Missing Fields
              </p>
              {missing.map((m, i) => (
                <p key={i} className="text-xs text-amber-600">{m}</p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2 flex-wrap px-4 pb-4">
        {Object.entries(ACTION_CONFIG).map(([act, { label, color: btnColor, icon: Icon }]) => {
          // Only show relevant actions
          if (act === 'replace' && !existingEntity) return null;
          if (act === 'merge' && !existingEntity) return null;
          return (
            <button
              key={act}
              onClick={() => onDecision(entry._key, act)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-black transition-all
                ${decision === act ? btnColor + ' shadow-md scale-105' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}
            >
              <Icon size={12} />
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function DuplicateReview() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [review, setReview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [decisions, setDecisions] = useState({});
  const [filter, setFilter] = useState('all');
  const [autoApplying, setAutoApplying] = useState(false);

  useEffect(() => {
    loadReview();
  }, [sessionId]);

  const loadReview = async () => {
    try {
      const res = await ingestionAPI.getReview(sessionId);
      const data = res.data;
      // Assign _key to each entry for tracking
      const allEntries = [
        ...data.auto_merged.map((e, i) => ({ ...e, _key: `auto_${i}`, _section: 'auto_merged' })),
        ...data.needs_review.map((e, i) => ({ ...e, _key: `review_${i}`, _section: 'needs_review' })),
        ...data.conflicts.map((e, i) => ({ ...e, _key: `conflict_${i}`, _section: 'conflicts' })),
        ...data.missing_fields.map((e, i) => ({ ...e, _key: `missing_${i}`, _section: 'missing_fields' })),
        ...data.new_records.map((e, i) => ({ ...e, _key: `new_${i}`, _section: 'new_records' })),
      ];

      // Initialize default decisions
      const defaultDecisions = {};
      allEntries.forEach((e) => {
        if (e._section === 'auto_merged') defaultDecisions[e._key] = 'merge';
        else if (e._section === 'new_records') defaultDecisions[e._key] = 'approve';
        else if (e._section === 'conflicts') defaultDecisions[e._key] = null;
        else if (e._section === 'needs_review') defaultDecisions[e._key] = 'merge';
        else defaultDecisions[e._key] = 'approve';
      });

      setDecisions(defaultDecisions);
      setReview({ ...data, _allEntries: allEntries });
    } catch (err) {
      showToast('Failed to load review data', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDecision = useCallback((key, action) => {
    setDecisions((prev) => ({ ...prev, [key]: action }));
  }, []);

  const handleAutoApply = async () => {
    setAutoApplying(true);
    try {
      const res = await ingestionAPI.applyAutoMerges(sessionId);
      showToast(`Auto-merged ${res.data.stats?.updated || 0} records`, 'success');
      loadReview();
    } catch (err) {
      showToast('Auto-merge failed', 'error');
    } finally {
      setAutoApplying(false);
    }
  };

  const handleBulkAction = (section, action) => {
    if (!review) return;
    const entries = review._allEntries.filter((e) => e._section === section);
    setDecisions((prev) => {
      const next = { ...prev };
      entries.forEach((e) => { next[e._key] = action; });
      return next;
    });
  };

  const handleSubmitAll = async () => {
    if (!review) return;
    setSubmitting(true);
    try {
      const decisionList = review._allEntries
        .filter((e) => decisions[e._key] && decisions[e._key] !== 'ignore')
        .map((e) => ({
          entity_type: e.entity_type,
          entity: e.new_entity,
          action: decisions[e._key] || 'approve',
          score: e.score,
          existing_id: e.existing_entity?.id || e.existing_entity?._id,
        }));

      await ingestionAPI.applyDecisions(sessionId, decisionList);
      showToast('All decisions applied successfully!', 'success');
      navigate('/knowledge/history');
    } catch (err) {
      showToast(err.response?.data?.detail || 'Failed to apply decisions', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={36} className="animate-spin text-violet-500" />
      </div>
    );
  }
  if (!review) return null;

  const allEntries = review._allEntries || [];
  const filtered = filter === 'all' ? allEntries : allEntries.filter((e) => e._section === filter);

  const sections = [
    { key: 'all',           label: 'All',           count: allEntries.length },
    { key: 'new_records',   label: 'New',           count: review.new_records?.length || 0 },
    { key: 'auto_merged',   label: 'Auto-Merge',    count: review.auto_merged?.length || 0 },
    { key: 'needs_review',  label: 'Review',        count: review.needs_review?.length || 0 },
    { key: 'conflicts',     label: 'Conflicts',     count: review.conflicts?.length || 0 },
    { key: 'missing_fields',label: 'Missing',       count: review.missing_fields?.length || 0 },
  ];

  const pendingCount = allEntries.filter((e) => !decisions[e._key]).length;
  const decidedCount = allEntries.length - pendingCount;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <header>
        <h1 className="text-3xl font-black text-slate-800">Review Dashboard</h1>
        <p className="text-slate-500 text-sm mt-1">
          {decidedCount}/{allEntries.length} decisions made · Session: <code className="bg-slate-100 px-1.5 py-0.5 rounded text-xs">{sessionId}</code>
        </p>
        <div className="h-1 w-24 bg-gradient-to-r from-violet-500 to-indigo-500 rounded-full mt-3" />
      </header>

      {/* Summary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {sections.slice(1).map(({ key, label, count }) => {
          const colors = { new_records: 'emerald', auto_merged: 'blue', needs_review: 'amber', conflicts: 'red', missing_fields: 'orange' };
          const c = colors[key] || 'slate';
          return (
            <button key={key} onClick={() => setFilter(key === filter ? 'all' : key)}
              className={`p-4 rounded-2xl text-center transition-all border-2 ${filter === key ? `border-${c}-400 bg-${c}-50` : 'border-transparent bg-white'} shadow-sm hover:shadow-md`}>
              <p className={`text-3xl font-black text-${c}-600`}>{count}</p>
              <p className="text-xs text-slate-500 font-bold">{label}</p>
            </button>
          );
        })}
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-white rounded-2xl p-4 shadow-sm border border-slate-100">
        <div className="flex flex-wrap gap-2">
          <button onClick={() => setFilter('all')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${filter === 'all' ? 'bg-violet-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
            All ({allEntries.length})
          </button>
          {review.auto_merged?.length > 0 && (
            <button
              onClick={handleAutoApply}
              disabled={autoApplying}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-xs font-bold rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-60"
            >
              {autoApplying ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
              Auto-Apply Merges ({review.auto_merged.length})
            </button>
          )}
        </div>

        <button
          onClick={handleSubmitAll}
          disabled={submitting || pendingCount > 0}
          className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-black rounded-xl disabled:opacity-60 disabled:cursor-not-allowed hover:from-violet-700 hover:to-indigo-700 transition-all shadow-lg shadow-violet-500/20"
        >
          {submitting ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          {pendingCount > 0 ? `${pendingCount} pending` : 'Apply All Decisions'}
        </button>
      </div>

      {/* Constraints from documents */}
      {review.constraints?.length > 0 && (
        <div className="bg-amber-50 rounded-2xl p-5 border border-amber-100">
          <h3 className="font-black text-amber-800 text-sm mb-3">📋 Extracted Timetable Constraints</h3>
          <ul className="space-y-1">
            {review.constraints.map((c, i) => (
              <li key={i} className="text-sm text-amber-700 flex items-start gap-2">
                <span className="text-amber-400 shrink-0">•</span>{c}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Entities */}
      {filtered.length === 0 ? (
        <div className="text-center py-20 text-slate-400">
          <CheckCircle2 size={48} className="mx-auto mb-3 text-emerald-300" />
          <p className="font-bold">No items in this category</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((entry) => (
            <EntityCard
              key={entry._key}
              entry={entry}
              onDecision={handleDecision}
              decisions={decisions}
            />
          ))}
        </div>
      )}
    </div>
  );
}
