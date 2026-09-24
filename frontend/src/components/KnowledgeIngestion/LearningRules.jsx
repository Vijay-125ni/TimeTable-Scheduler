import React, { useEffect, useState } from 'react';
import { ingestionAPI } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import { BookMarked, Plus, Trash2, Loader2, ArrowRight } from 'lucide-react';

export default function LearningRules() {
  const { showToast } = useToast();
  const [aliases, setAliases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ original: '', resolved: '', entity_type: 'departments' });
  const [saving, setSaving] = useState(false);

  useEffect(() => { loadAliases(); }, []);

  const loadAliases = async () => {
    try {
      const res = await ingestionAPI.getAliases();
      setAliases(res.data || []);
    } catch { showToast('Failed to load alias rules', 'error'); }
    finally { setLoading(false); }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!form.original || !form.resolved) return;
    setSaving(true);
    try {
      await ingestionAPI.createAlias(form);
      showToast('Alias rule created', 'success');
      setForm({ original: '', resolved: '', entity_type: 'departments' });
      loadAliases();
    } catch { showToast('Failed to create alias', 'error'); }
    finally { setSaving(false); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this alias rule?')) return;
    try {
      await ingestionAPI.deleteAlias(id);
      showToast('Alias deleted', 'success');
      loadAliases();
    } catch { showToast('Failed to delete alias', 'error'); }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <header>
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 bg-gradient-to-br from-teal-600 to-emerald-600 rounded-xl flex items-center justify-center shadow-lg">
            <BookMarked size={22} className="text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-black text-slate-800">Learning Rules</h1>
            <p className="text-slate-500 text-sm">Alias mappings the AI applies during future uploads</p>
          </div>
        </div>
        <div className="h-1 w-24 bg-gradient-to-r from-teal-500 to-emerald-500 rounded-full mt-3" />
      </header>

      {/* Create form */}
      <div className="bg-white rounded-3xl p-6 shadow-xl border border-slate-100">
        <h3 className="font-black text-slate-700 mb-4">Add New Alias Rule</h3>
        <form onSubmit={handleCreate} className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-36">
            <label className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5 block">Abbreviation / Alias</label>
            <input
              value={form.original}
              onChange={(e) => setForm((p) => ({ ...p, original: e.target.value }))}
              placeholder="ML"
              className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400"
            />
          </div>
          <div className="flex items-end pb-2.5 text-slate-400">
            <ArrowRight size={18} />
          </div>
          <div className="flex-1 min-w-36">
            <label className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5 block">Full Name</label>
            <input
              value={form.resolved}
              onChange={(e) => setForm((p) => ({ ...p, resolved: e.target.value }))}
              placeholder="Machine Learning"
              className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm font-semibold text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400"
            />
          </div>
          <div className="flex-1 min-w-36">
            <label className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5 block">Entity Type</label>
            <select
              value={form.entity_type}
              onChange={(e) => setForm((p) => ({ ...p, entity_type: e.target.value }))}
              className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-teal-400"
            >
              {['departments', 'faculty', 'subjects', 'rooms', 'classes', 'batches'].map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <button
            type="submit" disabled={saving}
            className="flex items-center gap-2 px-5 py-2.5 bg-teal-600 text-white text-sm font-black rounded-xl hover:bg-teal-700 transition-colors shadow-md disabled:opacity-60"
          >
            {saving ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
            Add
          </button>
        </form>
      </div>

      {/* Alias list */}
      {loading ? (
        <div className="flex justify-center py-12"><Loader2 size={28} className="animate-spin text-teal-400" /></div>
      ) : aliases.length === 0 ? (
        <div className="text-center py-12 text-slate-400">
          <BookMarked size={40} className="mx-auto mb-3 text-slate-200" />
          <p className="font-bold">No alias rules yet</p>
          <p className="text-sm mt-1">Rules are auto-learned when you confirm matches in the Review Dashboard</p>
        </div>
      ) : (
        <div className="bg-white rounded-3xl shadow-xl border border-slate-100 overflow-hidden">
          <div className="grid grid-cols-[1fr_auto_1fr_1fr_auto_auto] gap-0 bg-slate-50 px-5 py-3 text-xs font-black text-slate-500 uppercase tracking-wider border-b border-slate-100">
            <span>Original</span><span></span><span>Resolved</span><span>Entity Type</span><span>Confirmed</span><span></span>
          </div>
          <div className="divide-y divide-slate-50">
            {aliases.map((alias) => (
              <div key={alias._id} className="grid grid-cols-[1fr_auto_1fr_1fr_auto_auto] gap-2 px-5 py-3 items-center hover:bg-slate-50/60">
                <span className="font-black text-slate-800 text-sm">{alias.original}</span>
                <ArrowRight size={14} className="text-slate-300" />
                <span className="text-sm text-teal-700 font-semibold">{alias.resolved}</span>
                <span className="text-xs text-slate-400 capitalize">{alias.entity_type}</span>
                <span className="text-xs font-black text-violet-600 bg-violet-50 px-2 py-0.5 rounded-full w-fit">
                  ×{alias.confirmation_count}
                </span>
                <button
                  onClick={() => handleDelete(alias._id)}
                  className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-red-50 text-slate-300 hover:text-red-500 transition-all"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
