import React, { useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { ingestionAPI } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import {
  Upload, FileText, File, Image, Table, Archive,
  X, CheckCircle, AlertCircle, Loader2, Brain, Zap
} from 'lucide-react';

const ACCEPTED_EXTENSIONS = [
  '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv',
  '.txt', '.html', '.htm', '.xml', '.json', '.ppt', '.pptx',
  '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp', '.zip'
];

const FILE_ICONS = {
  pdf: { icon: FileText, color: 'text-red-500', bg: 'bg-red-50' },
  doc: { icon: FileText, color: 'text-blue-600', bg: 'bg-blue-50' },
  docx: { icon: FileText, color: 'text-blue-600', bg: 'bg-blue-50' },
  xls: { icon: Table, color: 'text-green-600', bg: 'bg-green-50' },
  xlsx: { icon: Table, color: 'text-green-600', bg: 'bg-green-50' },
  csv: { icon: Table, color: 'text-emerald-600', bg: 'bg-emerald-50' },
  png: { icon: Image, color: 'text-purple-500', bg: 'bg-purple-50' },
  jpg: { icon: Image, color: 'text-purple-500', bg: 'bg-purple-50' },
  jpeg: { icon: Image, color: 'text-purple-500', bg: 'bg-purple-50' },
  zip: { icon: Archive, color: 'text-amber-500', bg: 'bg-amber-50' },
  default: { icon: File, color: 'text-slate-500', bg: 'bg-slate-50' },
};

function getFileIcon(filename) {
  const ext = filename.split('.').pop()?.toLowerCase() || 'default';
  return FILE_ICONS[ext] || FILE_ICONS.default;
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function UploadPage() {
  const [files, setFiles] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);
  const folderInputRef = useRef(null);
  const navigate = useNavigate();
  const { showToast } = useToast();

  const addFiles = useCallback((newFiles) => {
    const validFiles = Array.from(newFiles).filter((f) => {
      const ext = '.' + f.name.split('.').pop()?.toLowerCase();
      return ACCEPTED_EXTENSIONS.includes(ext);
    });

    setFiles((prev) => {
      const existingNames = new Set(prev.map((f) => f.name + f.size));
      const unique = validFiles.filter((f) => !existingNames.has(f.name + f.size));
      return [...prev, ...unique];
    });

    const rejected = newFiles.length - validFiles.length;
    if (rejected > 0) {
      showToast(`${rejected} file(s) skipped — unsupported format`, 'warning');
    }
  }, [showToast]);

  const onDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files;
    if (dropped?.length) addFiles(dropped);
  }, [addFiles]);

  const onDragOver = useCallback((e) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const onDragLeave = useCallback(() => setIsDragging(false), []);

  const removeFile = (idx) => setFiles((prev) => prev.filter((_, i) => i !== idx));
  const clearAll = () => setFiles([]);

  const handleUpload = async () => {
    if (!files.length) {
      showToast('Please select at least one file', 'warning');
      return;
    }
    setUploading(true);
    try {
      const res = await ingestionAPI.upload(files);
      const { session_id, queued_files, upload_errors } = res.data;

      if (upload_errors?.length) {
        showToast(`${upload_errors.length} file(s) had upload errors`, 'warning');
      }

      showToast(`${queued_files} file(s) queued for AI processing`, 'success');
      navigate(`/knowledge/processing/${session_id}`);
    } catch (err) {
      showToast(err.response?.data?.detail || 'Upload failed', 'error');
    } finally {
      setUploading(false);
    }
  };

  const totalSize = files.reduce((a, f) => a + f.size, 0);

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Header */}
      <header>
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 bg-gradient-to-br from-violet-600 to-indigo-600 rounded-xl flex items-center justify-center shadow-lg shadow-violet-500/30">
            <Brain size={22} className="text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-black text-slate-800 tracking-tight">Knowledge Ingestion</h1>
            <p className="text-slate-500 text-sm">Upload institutional documents — AI extracts and organizes everything</p>
          </div>
        </div>
        <div className="h-1 w-24 bg-gradient-to-r from-violet-500 to-indigo-500 rounded-full mt-3" />
      </header>

      {/* Supported formats */}
      <div className="flex flex-wrap gap-2">
        {['PDF', 'DOCX', 'XLSX', 'CSV', 'Images', 'PPT', 'JSON', 'ZIP'].map((f) => (
          <span key={f} className="text-xs font-bold px-3 py-1 bg-violet-50 text-violet-700 rounded-full border border-violet-100">
            {f}
          </span>
        ))}
        <span className="text-xs text-slate-400 self-center ml-1">and more...</span>
      </div>

      {/* Drop Zone */}
      <div
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => fileInputRef.current?.click()}
        className={`relative border-2 border-dashed rounded-3xl p-16 text-center cursor-pointer transition-all duration-300 group
          ${isDragging
            ? 'border-violet-500 bg-violet-50 scale-[1.01]'
            : 'border-slate-200 bg-slate-50/60 hover:border-violet-400 hover:bg-violet-50/50'
          }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ACCEPTED_EXTENSIONS.join(',')}
          className="hidden"
          onChange={(e) => e.target.files && addFiles(e.target.files)}
        />
        <input
          ref={folderInputRef}
          type="file"
          webkitdirectory=""
          directory=""
          multiple
          className="hidden"
          onChange={(e) => e.target.files && addFiles(e.target.files)}
        />

        {/* Animated upload icon */}
        <div className={`mx-auto w-20 h-20 rounded-2xl flex items-center justify-center mb-6 transition-all duration-300
          ${isDragging
            ? 'bg-violet-500 shadow-xl shadow-violet-500/40 scale-110'
            : 'bg-white shadow-lg group-hover:bg-violet-500 group-hover:shadow-violet-500/30 group-hover:scale-105'
          }`}>
          <Upload size={36} className={`transition-colors duration-300 ${isDragging ? 'text-white' : 'text-slate-400 group-hover:text-white'}`} />
        </div>

        <h2 className="text-2xl font-black text-slate-700 mb-2">
          {isDragging ? 'Drop your files here!' : 'Drag & Drop your documents'}
        </h2>
        <p className="text-slate-500 mb-6">or click to browse files</p>

        <div className="flex justify-center gap-3">
          <button
            onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
            className="px-5 py-2.5 bg-violet-600 text-white text-sm font-bold rounded-xl hover:bg-violet-700 transition-colors shadow-md shadow-violet-500/20"
          >
            Browse Files
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); folderInputRef.current?.click(); }}
            className="px-5 py-2.5 bg-white border border-slate-200 text-slate-700 text-sm font-bold rounded-xl hover:bg-slate-50 transition-colors shadow-sm"
          >
            Upload Folder
          </button>
        </div>
      </div>

      {/* File Queue */}
      {files.length > 0 && (
        <div className="bg-white rounded-3xl shadow-xl border border-slate-100 overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
            <div>
              <h3 className="font-black text-slate-800">
                {files.length} file{files.length !== 1 ? 's' : ''} ready
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">Total: {formatBytes(totalSize)}</p>
            </div>
            <button
              onClick={clearAll}
              className="text-xs font-bold text-slate-400 hover:text-red-500 transition-colors px-3 py-1.5 rounded-lg hover:bg-red-50"
            >
              Clear all
            </button>
          </div>

          <div className="divide-y divide-slate-50 max-h-96 overflow-y-auto visible-scrollbar">
            {files.map((file, idx) => {
              const { icon: Icon, color, bg } = getFileIcon(file.name);
              return (
                <div key={`${file.name}-${idx}`} className="flex items-center gap-4 px-6 py-3 hover:bg-slate-50 transition-colors group">
                  <div className={`w-10 h-10 ${bg} rounded-xl flex items-center justify-center shrink-0`}>
                    <Icon size={18} className={color} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-slate-700 text-sm truncate">{file.name}</p>
                    <p className="text-xs text-slate-400">{formatBytes(file.size)}</p>
                  </div>
                  <button
                    onClick={() => removeFile(idx)}
                    className="opacity-0 group-hover:opacity-100 w-7 h-7 flex items-center justify-center rounded-lg hover:bg-red-100 text-slate-300 hover:text-red-500 transition-all"
                  >
                    <X size={14} />
                  </button>
                </div>
              );
            })}
          </div>

          <div className="px-6 py-4 bg-slate-50/60 border-t border-slate-100 flex justify-end">
            <button
              onClick={handleUpload}
              disabled={uploading}
              className="flex items-center gap-2.5 px-8 py-3 bg-gradient-to-r from-violet-600 to-indigo-600 text-white font-black text-sm rounded-2xl hover:from-violet-700 hover:to-indigo-700 transition-all shadow-lg shadow-violet-500/30 disabled:opacity-60 disabled:cursor-not-allowed active:scale-95"
            >
              {uploading ? (
                <><Loader2 size={18} className="animate-spin" /> Uploading...</>
              ) : (
                <><Zap size={18} /> Start AI Processing</>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Feature cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { icon: Brain, color: 'from-violet-500 to-indigo-500', title: 'AI Understanding', desc: 'Extracts entities from any document format using LLM' },
          { icon: Zap, color: 'from-amber-500 to-orange-500', title: 'Instant Deduplication', desc: 'Detects duplicates with fuzzy + semantic similarity' },
          { icon: CheckCircle, color: 'from-emerald-500 to-teal-500', title: 'Conflict Resolution', desc: 'Shows conflicts side-by-side for human review' },
        ].map(({ icon: Icon, color, title, desc }) => (
          <div key={title} className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
            <div className={`w-9 h-9 bg-gradient-to-br ${color} rounded-xl flex items-center justify-center mb-3 shadow-sm`}>
              <Icon size={18} className="text-white" />
            </div>
            <h4 className="font-black text-slate-800 text-sm mb-1">{title}</h4>
            <p className="text-xs text-slate-500 leading-relaxed">{desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
