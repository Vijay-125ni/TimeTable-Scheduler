import React, { useRef, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api, { clearApiCache, departmentAPI, classAPI, facultyAPI, timetableAPI } from '../../services/api';
import { isAdmin, getUser } from '../../utils/auth';
import { useToast } from '../../context/ToastContext';
import {
  Users,
  BookOpen,
  GraduationCap,
  DoorOpen,
  Calendar,
  Plus,
  LayoutDashboard,
  Clock,
  ChevronRight,
  User,
  Download,
  Upload,
  FileText,
  Building2,
  Layers,
  Settings as SettingsIcon,
  Sparkles,
  GitMerge,
  AlertTriangle,
  CheckCircle2
} from 'lucide-react';
import DocumentExtractorModal from './DocumentExtractorModal';

export default function Dashboard() {
  const [stats, setStats] = useState({ departments: 0, classes: 0, faculty: 0, timetables: 0 });
  const [missingSummary, setMissingSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [bulkImporting, setBulkImporting] = useState(false);
  const [bulkImportResults, setBulkImportResults] = useState([]);
  const [documentExtractorOpen, setDocumentExtractorOpen] = useState(false);
  const folderInputRef = useRef(null);
  const navigate = useNavigate();
  const { showToast } = useToast();
  const admin = isAdmin();
  const user = getUser();

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    try {
      const results = await Promise.allSettled([
        departmentAPI.getAll(), classAPI.getAll(), facultyAPI.getAll(), timetableAPI.getAll(),
        admin ? api.get('/imports/missing-data-summary') : Promise.resolve({ data: null })
      ]);

      const [dRes, cRes, fRes, tRes, mRes] = results;

      setStats({
        departments: dRes.status === 'fulfilled' ? dRes.value.data.length : 0,
        classes: cRes.status === 'fulfilled' ? cRes.value.data.length : 0,
        faculty: fRes.status === 'fulfilled' ? fRes.value.data.length : 0,
        timetables: tRes.status === 'fulfilled' ? tRes.value.data.length : 0
      });

      if (mRes.status === 'fulfilled' && mRes.value?.data) {
        setMissingSummary(mRes.value.data);
      }
    } catch (error) {
      console.error('Failed to load stats:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleStatClick = (path) => {
    if (!admin && path !== '/view') return;
    navigate(path);
  };

  const handleFullDataFetch = async (event) => {
    const files = Array.from(event.target.files || []).filter((file) => file.name.toLowerCase().endsWith('.csv'));
    if (!files.length) return;

    const form = new FormData();
    files.forEach((file) => form.append('files', file));

    setBulkImporting(true);
    setBulkImportResults([]);

    try {
      const res = await api.post('/imports/upload-folder', form);
      const data = res.data || {};

      setBulkImportResults(data.results || []);
      clearApiCache();
      await loadStats();

      const failed = Number(data.failed || 0);
      const partial = Number(data.partial || 0);
      showToast(
        failed || partial
          ? `Imported with ${failed} failed and ${partial} partial CSV file(s)`
          : `Imported ${data.imported || 0} records from folder`,
        failed ? 'error' : partial ? 'warning' : 'success'
      );
    } catch (error) {
      console.error(error);
      showToast(error.response?.data?.detail || error.message || 'Folder import failed', 'error');
    } finally {
      setBulkImporting(false);
      if (folderInputRef.current) folderInputRef.current.value = '';
    }
  };

  const StatCard = ({ title, value, color, path }) => (
    <div
      onClick={() => handleStatClick(path)}
      className={`relative overflow-hidden rounded-2xl p-8 text-white cursor-pointer transform hover:scale-[1.02] transition-all duration-300 shadow-lg ${color} ${(!admin && path !== '/view') ? 'cursor-default hover:scale-100' : ''}`}
    >
      {/* Background pattern blobs */}
      <div className="absolute -right-6 -top-6 w-32 h-32 bg-white/10 rounded-full blur-2xl" />
      <div className="absolute right-10 bottom-2 w-16 h-16 bg-black/5 rounded-full blur-xl" />

      <div className="relative flex flex-col items-center justify-center text-center">
        <p className="text-6xl font-black mb-2 tracking-tight">{loading ? <span className="animate-pulse">...</span> : value}</p>
        <p className="text-xs font-bold uppercase tracking-[0.2em] opacity-90">{title}</p>
      </div>
    </div>
  );

  const ActionButton = ({ icon: Icon, label, color, onClick, disabled = false }) => (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center gap-2 px-5 py-3 rounded-xl font-bold text-sm transition-all duration-200 shadow-md hover:shadow-lg active:scale-95 disabled:opacity-60 disabled:cursor-not-allowed disabled:active:scale-100 ${color} text-white`}
    >
      <Icon size={18} />
      {label}
    </button>
  );


  return (
    <div className="max-w-7xl mx-auto space-y-10">
      <header className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4">
        <div>
          <h1 className="text-4xl font-black text-slate-800 tracking-tight uppercase">
            {admin ? 'Admin Dashboard' : 'Faculty Dashboard'}
          </h1>
          <div className="h-1.5 w-20 bg-primary-500 rounded-full mt-2"></div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {admin && (
            <button
              onClick={() => navigate('/generate')}
              className="flex items-center gap-2 px-5 py-2.5 rounded-2xl bg-gradient-to-r from-primary-600 to-indigo-600 text-white font-black text-sm shadow-md hover:shadow-xl hover:scale-105 active:scale-95 transition-all cursor-pointer"
            >
              <Sparkles size={18} />
              Generate Timetable
            </button>
          )}
          <div className="bg-white px-4 py-2 rounded-2xl shadow-sm border border-slate-100 flex items-center gap-3">
            <div className="w-10 h-10 bg-primary-100 text-primary-600 rounded-xl flex items-center justify-center">
              <User size={20} />
            </div>
            <div>
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Logged in as</p>
              <p className="text-sm font-black text-slate-700">{user?.full_name || user?.username}</p>
            </div>
          </div>
        </div>
      </header>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {admin ? (
          <>
            <StatCard title="Departments" value={stats.departments} color="bg-[#434d5b]" path="/departments" />
            <StatCard title="Classes" value={stats.classes} color="bg-[#3b82f6]" path="/classes" />
            <StatCard title="Faculty" value={stats.faculty} color="bg-[#22c55e]" path="/faculty" />
            <StatCard title="Timetables" value={stats.timetables} color="bg-[#f59e0b]" path="/view" />
          </>
        ) : (
          <>
            <StatCard title="Available Timetables" value={stats.timetables} color="bg-[#3b82f6]" path="/view" />
            <div className="lg:col-span-3 bg-gradient-to-r from-primary-600/10 to-blue-600/10 rounded-3xl p-8 border border-primary-500/10 flex items-center justify-center">
              <div className="text-center">
                <h3 className="text-2xl font-black text-primary-700 mb-2">Welcome Back!</h3>
                <p className="text-slate-500">You can view all generated timetables and filter by your name in the Timetables section.</p>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Missing Data Notification Card */}
      {admin && missingSummary && (
        <div className={`rounded-3xl p-8 shadow-xl border transition-all ${
          missingSummary.has_missing 
            ? 'bg-amber-50/70 border-amber-200' 
            : 'bg-emerald-50/70 border-emerald-200'
        }`}>
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
            <div className="flex items-center gap-3">
              <div className={`w-12 h-12 rounded-2xl flex items-center justify-center shadow-md ${
                missingSummary.has_missing ? 'bg-amber-500 text-white' : 'bg-emerald-500 text-white'
              }`}>
                {missingSummary.has_missing ? <AlertTriangle size={24} /> : <CheckCircle2 size={24} />}
              </div>
              <div>
                <h2 className="text-xl font-extrabold text-slate-800 flex items-center gap-2">
                  Missing Data Notifications
                  {missingSummary.has_missing && (
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-black bg-amber-500 text-white shadow-sm">
                      {missingSummary.total_missing} Issues
                    </span>
                  )}
                </h2>
                <p className="text-xs text-slate-500 font-semibold mt-0.5">
                  {missingSummary.has_missing
                    ? 'Incomplete academic data detected. Click "Fix" to enter missing details on respective pages.'
                    : 'All extracted and imported data is complete! Timetable generation is ready.'}
                </p>
              </div>
            </div>

            {missingSummary.has_missing && (
              <button
                onClick={() => setDocumentExtractorOpen(true)}
                className="flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-xs font-black rounded-xl shadow-md transition-all active:scale-95 cursor-pointer"
              >
                <Sparkles size={16} /> Re-extract / Fill Data
              </button>
            )}
          </div>

          {missingSummary.has_missing && (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mt-4">
              {[
                { id: 'departments', label: 'Departments', path: '/departments', count: missingSummary.details?.departments?.count || 0 },
                { id: 'batches', label: 'Batches', path: '/batches', count: missingSummary.details?.batches?.count || 0 },
                { id: 'classes', label: 'Classes', path: '/classes', count: missingSummary.details?.classes?.count || 0 },
                { id: 'rooms', label: 'Rooms', path: '/rooms', count: missingSummary.details?.rooms?.count || 0 },
                { id: 'subjects', label: 'Subjects', path: '/subjects', count: missingSummary.details?.subjects?.count || 0 },
                { id: 'faculty', label: 'Faculty', path: '/faculty', count: missingSummary.details?.faculty?.count || 0 },
                { id: 'mappings', label: 'Faculty Mappings', path: '/mapping', count: missingSummary.details?.mappings?.count || 0 },
              ].map(cat => (
                <div
                  key={cat.id}
                  className={`p-4 rounded-2xl border transition-all flex flex-col justify-between ${
                    cat.count > 0 ? 'bg-white border-amber-300 shadow-sm' : 'bg-slate-50/50 border-slate-200 opacity-60'
                  }`}
                >
                  <div className="flex justify-between items-center mb-2">
                    <span className="font-extrabold text-sm text-slate-800">{cat.label}</span>
                    <span className={`px-2 py-0.5 text-xs font-black rounded-full ${
                      cat.count > 0 ? 'bg-amber-100 text-amber-800 border border-amber-300' : 'bg-emerald-100 text-emerald-700'
                    }`}>
                      {cat.count > 0 ? `${cat.count} missing` : 'Complete'}
                    </span>
                  </div>
                  {cat.count > 0 && (
                    <button
                      onClick={() => navigate(cat.path)}
                      className="mt-2 w-full py-1.5 px-3 bg-slate-900 hover:bg-slate-800 text-white font-bold text-xs rounded-xl shadow transition-all flex items-center justify-center gap-1 cursor-pointer"
                    >
                      Fix in {cat.label} <ChevronRight size={14} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Quick Actions Row */}
      <div className="bg-white rounded-3xl p-8 shadow-xl border border-slate-100">
        <h2 className="text-xl font-extrabold text-slate-700 mb-6 flex items-center gap-2">
          <LayoutDashboard size={24} className="text-primary-500" />
          Quick Actions
        </h2>
        <div className="flex flex-wrap gap-3">
          {admin ? (
            <>
              <input
                ref={folderInputRef}
                type="file"
                accept=".csv"
                multiple
                webkitdirectory=""
                directory=""
                onChange={handleFullDataFetch}
                className="hidden"
              />
              <ActionButton icon={FileText} label="Extract & Fill Data" color="bg-gradient-to-r from-violet-600 to-purple-600" onClick={() => setDocumentExtractorOpen(true)} />
              <ActionButton icon={Sparkles} label="Generate Timetable" color="bg-gradient-to-r from-primary-600 to-blue-600" onClick={() => navigate('/generate')} />
              <ActionButton icon={Calendar} label="View Timetables" color="bg-amber-500" onClick={() => navigate('/view')} />
              <ActionButton icon={Building2} label="Departments" color="bg-indigo-600" onClick={() => navigate('/departments')} />
              <ActionButton icon={Layers} label="Batches" color="bg-cyan-600" onClick={() => navigate('/batches')} />
              <ActionButton icon={GraduationCap} label="Classes" color="bg-sky-600" onClick={() => navigate('/classes')} />
              <ActionButton icon={DoorOpen} label="Rooms" color="bg-teal-600" onClick={() => navigate('/rooms')} />
              <ActionButton icon={BookOpen} label="Subjects" color="bg-slate-700" onClick={() => navigate('/subjects')} />
              <ActionButton icon={Users} label="Faculty" color="bg-blue-600" onClick={() => navigate('/faculty')} />
              <ActionButton icon={GitMerge} label="Faculty Mapping" color="bg-indigo-700" onClick={() => navigate('/mapping')} />
              <ActionButton
                icon={Upload}
                label={bulkImporting ? 'Fetching CSVs...' : 'Full Data Fetch'}
                color="bg-emerald-600"
                onClick={() => folderInputRef.current?.click()}
                disabled={bulkImporting}
              />
              <ActionButton icon={Download} label="Download Templates" color="bg-purple-600" onClick={() => { window.location.href = '/api/imports/templates'; }} />
              <ActionButton icon={SettingsIcon} label="Settings" color="bg-slate-600" onClick={() => navigate('/settings')} />
            </>
          ) : (
            <>
              <ActionButton icon={Calendar} label="View All Timetables" color="bg-primary-600" onClick={() => navigate('/view')} />
              <ActionButton icon={SettingsIcon} label="Settings" color="bg-slate-600" onClick={() => navigate('/settings')} />
            </>
          )}
        </div>
        {admin && bulkImportResults.length > 0 && (
          <div className="mt-6 rounded-xl border border-slate-200 overflow-hidden">
            <div className="grid grid-cols-[1.2fr_0.8fr_0.8fr] bg-slate-50 px-4 py-2 text-xs font-black uppercase tracking-wider text-slate-500">
              <span>CSV File</span>
              <span>Status</span>
              <span>Imported</span>
            </div>
            {bulkImportResults.map((item, index) => (
              <div key={`${item.file}-${index}`} className="grid grid-cols-[1.2fr_0.8fr_0.8fr] gap-3 border-t border-slate-100 px-4 py-3 text-sm">
                <span className="font-semibold text-slate-700 break-all">{item.file}</span>
                <span className={`font-bold ${item.status === 'success' ? 'text-emerald-600' : item.status === 'partial' ? 'text-amber-600' : item.status === 'failed' ? 'text-red-600' : 'text-slate-500'}`}>
                  {item.status}
                </span>
                <span className="text-slate-600">
                  {item.imported ?? '-'}
                  {item.skipped ? ` (${item.skipped} skipped)` : ''}
                </span>
                {item.message && (
                  <span className="col-span-3 text-xs text-slate-500 break-words">{item.message}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recent Activity Section */}
      {admin && (
        <div className="bg-white rounded-3xl p-8 shadow-xl border border-slate-100">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
            <h2 className="text-xl font-extrabold text-slate-700 flex items-center gap-2">
              <Clock size={24} className="text-primary-500" />
              Recent System Activity
            </h2>
          </div>

          <div className="space-y-4">
            {[
              { action: "Generated timetable for Spring 2024", time: "2 hours ago", type: "system" },
              { action: "Added 5 new faculty members to AIML Dept", time: "5 hours ago", type: "modify" },
              { action: "System maintenance completed", time: "1 day ago", type: "modify" }
            ].map((item, idx) => (
              <div key={idx} className="flex items-center justify-between p-4 rounded-2xl bg-slate-50 border border-slate-100 hover:bg-slate-100 transition-colors cursor-default">
                <div className="flex flex-wrap items-center gap-4">
                  <div className={`w-2 h-2 rounded-full ${item.type === 'system' ? 'bg-blue-500' : 'bg-green-500'}`} />
                  <div>
                    <p className="font-bold text-slate-700 text-sm">{item.action}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{item.time}</p>
                  </div>
                </div>
                <ChevronRight size={18} className="text-slate-300" />
              </div>
            ))}
          </div>
        </div>
      )}
      <DocumentExtractorModal
        isOpen={documentExtractorOpen}
        onClose={() => setDocumentExtractorOpen(false)}
        onImportSuccess={async () => {
          clearApiCache();
          await loadStats();
        }}
      />
    </div>
  );
}
