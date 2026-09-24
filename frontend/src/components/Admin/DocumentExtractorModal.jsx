import React, { useState, useRef } from 'react';
import {
  X,
  Upload,
  Loader2,
  FileSpreadsheet,
  Download,
  Database,
  AlertTriangle,
  CheckCircle,
  Info,
  ChevronRight,
  Sparkles,
  ArrowRight
} from 'lucide-react';
import api from '../../services/api';
import { useToast } from '../../context/ToastContext';

const TABS = [
  { id: 'departments', label: 'Departments', icon: Sparkles, fields: ['name', 'code'] },
  { id: 'batches', label: 'Batches', icon: Sparkles, fields: ['name', 'start_time', 'end_time', 'period_duration', 'break_times', 'lunch_break'] },
  { id: 'classes', label: 'Classes', icon: Sparkles, fields: ['name', 'section', 'semester', 'student_count', 'department_code', 'batch_name'] },
  { id: 'rooms', label: 'Rooms', icon: Sparkles, fields: ['name', 'code', 'room_type', 'capacity', 'department_code'] },
  { id: 'subjects', label: 'Subjects', icon: Sparkles, fields: ['name', 'code', 'hours_per_week', 'requires_lab', 'department_codes', 'batch_name'] },
  { id: 'faculty', label: 'Faculty', icon: Sparkles, fields: ['name', 'email', 'department_code'] },
  { id: 'mappings', label: 'Mappings', icon: Sparkles, fields: ['subject_code', 'class_name', 'class_section', 'faculty_email', 'room_code'] }
];

const REQUIRED_FIELDS = {
  departments: ['name', 'code'],
  batches: ['name'],
  classes: ['name'],
  rooms: ['name'],
  subjects: ['name', 'code'],
  faculty: ['name', 'email'],
  mappings: ['subject_code', 'class_name', 'faculty_email']
};

export default function DocumentExtractorModal({ isOpen, onClose, onImportSuccess }) {
  const { showToast } = useToast();
  const fileInputRef = useRef(null);
  
  const [files, setFiles] = useState([]);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState('');
  const [progress, setProgress] = useState(0);
  const [modelLogs, setModelLogs] = useState('');
  const [extractedData, setExtractedData] = useState(null);
  const [activeTab, setActiveTab] = useState('departments');
  const [warnings, setWarnings] = useState([]);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  
  const logsEndRef = useRef(null);

  // Auto-scroll logs
  React.useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [modelLogs]);

  if (!isOpen) return null;

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragging(true);
  };

  const handleDragLeave = () => {
    setDragging(false);
  };

  const addFilesToQueue = (newFiles) => {
    const validFiles = Array.from(newFiles);
    setFiles(prev => {
      const existingNames = new Set(prev.map(f => f.name));
      const unique = validFiles.filter(f => !existingNames.has(f.name));
      return [...prev, ...unique];
    });
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      addFilesToQueue(e.dataTransfer.files);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      addFilesToQueue(e.target.files);
    }
  };

  const removeFile = (index) => {
    setFiles(prev => prev.filter((_, idx) => idx !== index));
  };

  const clearQueue = () => {
    setFiles([]);
  };

  const resetState = () => {
    setFiles([]);
    setExtractedData(null);
    setLoading(false);
    setLoadingStage('');
    setProgress(0);
    setModelLogs('');
    setWarnings([]);
  };

  const startExtraction = async () => {
    if (files.length === 0) return;

    setLoading(true);
    setProgress(0);
    setModelLogs('');
    setWarnings([]);

    const mergedData = {
      departments: [],
      batches: [],
      classes: [],
      rooms: [],
      subjects: [],
      faculty: [],
      mappings: []
    };
    const allWarnings = [];

    try {
      const token = localStorage.getItem('token');
      const totalFiles = files.length;

      for (let i = 0; i < totalFiles; i++) {
        const file = files[i];
        const fileNum = i + 1;
        
        setLoadingStage(`[File ${fileNum}/${totalFiles}] Extracting ${file.name}...`);
        setModelLogs(prev => prev + `\n========================================\n🚀 [File ${fileNum}/${totalFiles}] Processing: ${file.name}\n========================================\n`);

        const form = new FormData();
        form.append('file', file);

        const response = await fetch(`${import.meta.env.VITE_API_URL || '/api'}/imports/extract-academic-data`, {
          method: 'POST',
          body: form,
          headers: {
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
          }
        });

        if (!response.ok) {
          let errorData;
          try { errorData = await response.json(); } catch (e) { errorData = { detail: response.statusText }; }
          const errMsg = errorData.detail || `Failed to extract file ${file.name}`;
          setModelLogs(prev => prev + `\n❌ Error: ${errMsg}\n`);
          allWarnings.push(`${file.name}: ${errMsg}`);
          continue;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop();

          for (const line of lines) {
            if (!line.trim()) continue;

            try {
              const data = JSON.parse(line);

              if (data.status === 'log') {
                console.log('[AI Log]', data.text);
                setModelLogs(prev => prev + data.text);
              } else if (data.status === 'progress') {
                console.log(`[AI Progress ${data.progress}%]`, data.message);
                const overallPct = Math.round(((i / totalFiles) * 100) + (data.progress / totalFiles));
                setProgress(overallPct);
                setLoadingStage(`[File ${fileNum}/${totalFiles}] ${data.message}`);
              } else if (data.status === 'error') {
                console.error('[AI Error]', data.error);
                setModelLogs(prev => prev + `\n❌ ${data.error}\n`);
                allWarnings.push(`${file.name}: ${data.error}`);
              } else if (data.status === 'success') {
                const { extracted_data, warnings: serverWarnings } = data.data;
                if (serverWarnings && serverWarnings.length > 0) {
                  allWarnings.push(...serverWarnings.map(w => `${file.name}: ${w}`));
                }
                if (extracted_data) {
                  Object.keys(mergedData).forEach(key => {
                    if (extracted_data[key] && Array.isArray(extracted_data[key])) {
                      mergedData[key].push(...extracted_data[key]);
                    }
                  });
                }
              }
            } catch (e) {
              console.error('Error parsing stream line:', e, line);
            }
          }
        }
      }

      // Deduplicate merged items by key properties
      const dedupeBy = (arr, keyFn) => {
        const seen = new Set();
        return arr.filter(item => {
          const k = keyFn(item);
          if (!k || seen.has(k)) return false;
          seen.add(k);
          return true;
        });
      };

      mergedData.departments = dedupeBy(mergedData.departments, d => (d.code || d.name || '').toLowerCase());
      mergedData.batches = dedupeBy(mergedData.batches, b => (b.name || '').toLowerCase());
      mergedData.classes = dedupeBy(mergedData.classes, c => `${c.name}-${c.section || ''}`.toLowerCase());
      mergedData.rooms = dedupeBy(mergedData.rooms, r => (r.code || r.name || '').toLowerCase());
      mergedData.subjects = dedupeBy(mergedData.subjects, s => (s.code || s.name || '').toLowerCase());
      mergedData.faculty = dedupeBy(mergedData.faculty, f => (f.email || f.name || '').toLowerCase());

      setExtractedData(mergedData);
      setWarnings(allWarnings);
      setProgress(100);
      const totalItems = Object.values(mergedData).reduce((sum, arr) => sum + arr.length, 0);
      showToast(`Extracted and merged ${totalItems} items across ${files.length} file(s)!`, 'success');
    } catch (err) {
      console.error(err);
      showToast(err.message || 'Queue extraction failed', 'error');
    } finally {
      setLoading(false);
      setLoadingStage('');
      setProgress(0);
    }
  };

  const startExcelExtraction = async () => {
    if (files.length === 0) return;
    
    setLoading(true);
    setProgress(0);
    setModelLogs('');
    setWarnings([]);

    const mergedData = {
      departments: [],
      batches: [],
      classes: [],
      rooms: [],
      subjects: [],
      faculty: [],
      mappings: []
    };
    const allWarnings = [];

    try {
      const totalFiles = files.length;

      for (let i = 0; i < totalFiles; i++) {
        const file = files[i];
        const fileNum = i + 1;
        setLoadingStage(`[File ${fileNum}/${totalFiles}] Parsing Excel ${file.name}...`);
        setProgress(Math.round((i / totalFiles) * 100));
        setModelLogs(prev => prev + `\n--- Processing Excel File [${fileNum}/${totalFiles}]: ${file.name} ---\n`);

        const form = new FormData();
        form.append('file', file);

        try {
          const response = await api.post('/imports/extract-excel-data', form);
          const data = response.data;
          
          if (data.status === 'success') {
             const { extracted_data, warnings: serverWarnings } = data.data;
             if (serverWarnings) allWarnings.push(...serverWarnings.map(w => `${file.name}: ${w}`));
             if (extracted_data) {
               Object.keys(mergedData).forEach(key => {
                 if (extracted_data[key] && Array.isArray(extracted_data[key])) {
                   mergedData[key].push(...extracted_data[key]);
                 }
               });
             }
             setModelLogs(prev => prev + `✓ Completed Excel extraction for ${file.name}\n`);
          } else {
             throw new Error(`Failed to parse ${file.name}`);
          }
        } catch (fileErr) {
          setModelLogs(prev => prev + `❌ Error: ${fileErr.message}\n`);
          allWarnings.push(`${file.name}: ${fileErr.message}`);
        }
      }

      setExtractedData(mergedData);
      setWarnings(allWarnings);
      setProgress(100);
      const totalItems = Object.values(mergedData).reduce((sum, arr) => sum + arr.length, 0);
      showToast(`Extracted ${totalItems} items strictly from Excel queue!`, 'success');
    } catch (err) {
      console.error(err);
      showToast(err.message || 'Excel queue extraction failed', 'error');
    } finally {
      setLoading(false);
      setLoadingStage('');
      setProgress(0);
    }
  };


  const handleCellChange = (tabId, rowIndex, fieldName, value) => {
    const updatedData = { ...extractedData };
    updatedData[tabId][rowIndex][fieldName] = value;
    setExtractedData(updatedData);
  };

  const addRow = (tabId) => {
    const updatedData = { ...extractedData };
    const tabObj = TABS.find(t => t.id === tabId);
    const newRow = {};
    tabObj.fields.forEach(f => {
      newRow[f] = f === 'capacity' || f === 'semester' || f === 'student_count' || f === 'hours_per_week' || f === 'period_duration' ? 0 : '';
    });
    updatedData[tabId] = [...updatedData[tabId], newRow];
    setExtractedData(updatedData);
  };

  const deleteRow = (tabId, rowIndex) => {
    const updatedData = { ...extractedData };
    updatedData[tabId] = updatedData[tabId].filter((_, idx) => idx !== rowIndex);
    setExtractedData(updatedData);
  };

  const downloadCSVs = async () => {
    if (!extractedData) return;
    try {
      showToast('Generating zip file...', 'info');
      const response = await api.post('/imports/download-filled-templates', extractedData, {
        responseType: 'blob'
      });
      
      const blob = new Blob([response.data], { type: 'application/zip' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'extracted_academic_templates.zip');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      showToast('CSV templates downloaded successfully!', 'success');
    } catch (err) {
      showToast('Failed to download ZIP file.', 'error');
    }
  };

  const getMissingFieldsCount = () => {
    if (!extractedData) return 0;
    let count = 0;
    Object.keys(REQUIRED_FIELDS).forEach(tabId => {
      const rows = extractedData[tabId] || [];
      const reqs = REQUIRED_FIELDS[tabId];
      rows.forEach(row => {
        reqs.forEach(field => {
          const val = row[field];
          if (val === undefined || val === null || (typeof val === 'string' && val.trim() === '')) {
            count++;
          }
        });
      });
    });
    return count;
  };

  const importToDatabase = async () => {
    if (!extractedData) return;
    
    const missingCount = getMissingFieldsCount();
    if (missingCount > 0) {
      showToast(`Syncing to database (${missingCount} missing field(s) stored to complete on respective management pages)...`, 'info');
    }

    setImporting(true);
    try {
      const res = await api.post('/imports/import-extracted-data', extractedData);
      setImportResult(res.data);
      if (res.data.error_count === 0) {
        showToast(`Imported ${res.data.imported} records successfully!`, 'success');
        if (onImportSuccess) onImportSuccess();
      } else {
        showToast(`Imported ${res.data.imported} records with some errors.`, 'warning');
      }
    } catch (err) {
      showToast(err.response?.data?.detail || 'Import process encountered an error', 'error');
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-md animate-fade-in">
      <div className="relative w-full max-w-6xl h-[90vh] bg-white rounded-3xl shadow-2xl flex flex-col overflow-hidden border border-slate-100 animate-scale-up">
        
        {/* Header */}
        <header className="px-8 py-5 border-b border-slate-100 flex justify-between items-center bg-gradient-to-r from-violet-50/50 to-indigo-50/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-violet-600 rounded-xl flex items-center justify-center text-white shadow-md">
              <Sparkles size={20} />
            </div>
            <div>
              <h2 className="text-xl font-black text-slate-800 tracking-tight">AI Document Extractor & Template Filler</h2>
              <p className="text-xs text-slate-500 font-semibold uppercase tracking-wider">Powered by PaddleOCR & Qwen Cloud API</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-10 h-10 rounded-full border border-slate-100 flex items-center justify-center hover:bg-slate-50 hover:text-rose-500 transition-colors shadow-sm bg-white"
          >
            <X size={18} />
          </button>
        </header>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-8 space-y-6">
          {!extractedData && !loading && (
            <div className="max-w-2xl mx-auto mt-10">
              {/* Upload Dropzone */}
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-3 border-dashed rounded-3xl p-10 text-center cursor-pointer transition-all duration-300 ${
                  dragging
                    ? 'border-violet-500 bg-violet-50/50 scale-[1.01]'
                    : files.length > 0
                    ? 'border-emerald-500 bg-emerald-50/10'
                    : 'border-slate-200 hover:border-violet-400 hover:bg-slate-50/50'
                }`}
              >
                 <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  onChange={handleFileChange}
                  className="hidden"
                />
                <div className="flex flex-col items-center gap-3">
                  <div className={`w-14 h-14 rounded-2xl flex items-center justify-center shadow-lg transition-transform ${
                    files.length > 0 ? 'bg-emerald-500 text-white' : 'bg-violet-100 text-violet-600'
                  }`}>
                    <Upload size={26} />
                  </div>
                  <div>
                    <p className="text-lg font-extrabold text-slate-700">Drag & Drop Academic File(s) or Scanned Images</p>
                    <p className="text-sm font-medium text-slate-400 mt-1">Select multiple PDF, Image, Excel, Word, or Text files to process in queue</p>
                  </div>
                </div>
              </div>

              {/* Files Queue List */}
              {files.length > 0 && (
                <div className="mt-6 bg-slate-50 border border-slate-200 rounded-2xl p-5 shadow-sm">
                  <div className="flex items-center justify-between pb-3 border-b border-slate-200 mb-3">
                    <span className="text-xs font-black text-slate-500 uppercase tracking-wider">
                      Selected Queue ({files.length} {files.length === 1 ? 'file' : 'files'})
                    </span>
                    <button
                      onClick={clearQueue}
                      className="text-xs font-extrabold text-rose-600 hover:text-rose-700 bg-rose-50 hover:bg-rose-100 px-3 py-1 rounded-lg transition-colors"
                    >
                      Clear All
                    </button>
                  </div>

                  <div className="space-y-2 max-h-48 overflow-y-auto pr-1 custom-scrollbar">
                    {files.map((f, idx) => (
                      <div key={idx} className="flex items-center justify-between bg-white border border-slate-200 rounded-xl px-4 py-2.5 shadow-2xs">
                        <div className="flex items-center gap-3 overflow-hidden">
                          <span className="w-6 h-6 rounded-full bg-violet-100 text-violet-700 text-xs font-black flex items-center justify-center shrink-0">
                            {idx + 1}
                          </span>
                          <div className="truncate">
                            <p className="text-sm font-bold text-slate-800 truncate">{f.name}</p>
                            <p className="text-xs font-medium text-slate-400">{(f.size / (1024 * 1024)).toFixed(2)} MB</p>
                          </div>
                        </div>
                        <button
                          onClick={() => removeFile(idx)}
                          className="w-7 h-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-rose-500 hover:bg-rose-50 transition-colors shrink-0"
                          title="Remove file"
                        >
                          <X size={15} />
                        </button>
                      </div>
                    ))}
                  </div>

                  <div className="mt-4 flex items-center gap-3">
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="text-xs font-extrabold text-violet-600 hover:text-violet-700 bg-violet-100/60 hover:bg-violet-100 px-4 py-2 rounded-xl transition-colors"
                    >
                      + Add More Files
                    </button>
                  </div>

                  {/* Action Buttons */}
                  <div className="mt-5 flex flex-col gap-3">
                    <button
                      onClick={startExtraction}
                      className="flex items-center gap-3 px-8 py-4 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-700 hover:to-indigo-700 text-white text-base font-black rounded-2xl shadow-xl hover:shadow-2xl transition-all duration-200 active:scale-95 group w-full justify-center"
                    >
                      Start Extraction Pipeline ({files.length} {files.length === 1 ? 'File' : 'Files'})
                      <ArrowRight size={18} className="transform group-hover:translate-x-1 transition-transform" />
                    </button>

                    {files.some(f => f.name.toLowerCase().endsWith('.xlsx') || f.name.toLowerCase().endsWith('.xls')) && (
                      <button
                        onClick={startExcelExtraction}
                        className="flex items-center gap-3 px-8 py-4 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white text-base font-black rounded-2xl shadow-xl hover:shadow-2xl transition-all duration-200 active:scale-95 group w-full justify-center"
                      >
                        Extract Excel Queue (Strict Mode)
                        <FileSpreadsheet size={18} className="transform group-hover:translate-x-1 transition-transform" />
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Loading state */}
          {/* Loading state */}
          {loading && (
            <div className="flex flex-col items-center justify-center p-8 space-y-6 w-full max-w-2xl mx-auto">
              <Loader2 className="animate-spin text-violet-600" size={48} />
              <div className="text-center w-full">
                <p className="text-xl font-black text-slate-800 mb-2">Extracting Data...</p>
                <div className="w-full bg-slate-100 h-3 rounded-full overflow-hidden my-4 shadow-inner">
                  <div 
                    className="bg-gradient-to-r from-violet-500 to-indigo-500 h-full rounded-full transition-all duration-300 ease-out relative"
                    style={{ width: `${progress}%` }}
                  >
                    <div className="absolute inset-0 bg-white/20 animate-pulse"></div>
                  </div>
                </div>
                <div className="flex justify-between text-xs font-bold text-slate-400 mb-6">
                  <span>{loadingStage}</span>
                  <span>{progress}%</span>
                </div>
                
                {/* Live Model Logs */}
                <div className="w-full bg-slate-900 rounded-xl overflow-hidden shadow-xl border border-slate-700 flex flex-col h-115 ">
                  <div className="bg-slate-800 px-4 py-2 flex items-center justify-between text-xs font-bold text-slate-400 border-b border-slate-700">
                    <span className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                      Live AI Logs
                    </span>
                    <span>Qwen API</span>
                  </div>
                  <div className="p-4 text-emerald-400 font-mono text-xs overflow-y-auto h-full text-left whitespace-pre-wrap flex-1 custom-scrollbar">
                    {modelLogs || 'Waiting for AI response stream...'}
                    <div ref={logsEndRef} />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Results display */}
          {extractedData && (
            <div className="h-full flex flex-col space-y-6">
              
              {/* Warnings Banner if any */}
              {warnings.length > 0 && (
                <div className="p-4 rounded-2xl bg-amber-50 border border-amber-200 flex gap-3 text-amber-800 text-sm">
                  <AlertTriangle size={20} className="shrink-0 text-amber-500" />
                  <div>
                    <p className="font-extrabold">OCR Warnings / Remarks</p>
                    <ul className="list-disc pl-5 mt-1 space-y-0.5 font-medium">
                      {warnings.map((w, idx) => (
                        <li key={idx}>{w}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {/* Tab Navigation */}
              <div className="flex overflow-x-auto gap-2 pb-1 border-b border-slate-100">
                {TABS.map(tab => {
                  const count = extractedData[tab.id]?.length || 0;
                  const isActive = activeTab === tab.id;
                  
                  // Count missing fields in this tab
                  let missingInTab = 0;
                  const reqs = REQUIRED_FIELDS[tab.id] || [];
                  (extractedData[tab.id] || []).forEach(row => {
                    reqs.forEach(f => {
                      const val = row[f];
                      if (val === undefined || val === null || (typeof val === 'string' && val.trim() === '')) {
                        missingInTab++;
                      }
                    });
                  });

                  return (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      className={`flex items-center gap-2 px-5 py-3 rounded-t-xl font-bold text-sm transition-all duration-200 border-b-2 whitespace-nowrap ${
                        isActive
                          ? 'border-violet-600 text-violet-600 bg-violet-50/30'
                          : 'border-transparent text-slate-400 hover:text-slate-600 hover:bg-slate-50/50'
                      }`}
                    >
                      {tab.label}
                      <span className={`px-2 py-0.5 text-xs font-black rounded-full ${
                        isActive ? 'bg-violet-100 text-violet-600' : 'bg-slate-100 text-slate-500'
                      }`}>
                        {count}
                      </span>
                      {missingInTab > 0 && (
                        <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse border border-white" title={`${missingInTab} missing required value(s)`} />
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Active Tab Preview Table */}
              <div className="flex-1 min-h-[300px] border border-slate-100 rounded-2xl overflow-hidden bg-white flex flex-col">
                <div className="flex justify-between items-center px-6 py-4 bg-slate-50 border-b border-slate-100">
                  <span className="text-xs font-black uppercase text-slate-400 tracking-wider">
                    Extracted {TABS.find(t => t.id === activeTab).label} List
                  </span>
                  <button
                    onClick={() => addRow(activeTab)}
                    className="text-xs font-extrabold text-violet-600 hover:text-violet-700 bg-violet-50 hover:bg-violet-100 px-3 py-1.5 rounded-lg transition-colors"
                  >
                    + Add Row
                  </button>
                </div>
                
                <div className="flex-1 overflow-auto max-h-[350px]">
                  <table className="w-full text-left border-collapse text-sm">
                    <thead>
                      <tr className="bg-slate-50/50 text-slate-500 font-extrabold border-b border-slate-100">
                        {TABS.find(t => t.id === activeTab).fields.map(field => (
                          <th key={field} className="px-6 py-3 border-r border-slate-100 capitalize">{field.replace('_', ' ')}</th>
                        ))}
                        <th className="px-6 py-3 text-center">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {extractedData[activeTab]?.length === 0 ? (
                        <tr>
                          <td colSpan={TABS.find(t => t.id === activeTab).fields.length + 1} className="px-6 py-10 text-center font-bold text-slate-400">
                            No records extracted for this template category. Use the "+ Add Row" button above to insert one manually.
                          </td>
                        </tr>
                      ) : (
                        extractedData[activeTab]?.map((row, rowIndex) => (
                          <tr key={rowIndex} className="hover:bg-slate-50/40 transition-colors">
                            {TABS.find(t => t.id === activeTab).fields.map(field => {
                              const isRequired = REQUIRED_FIELDS[activeTab]?.includes(field);
                              const isEmpty = row[field] === undefined || row[field] === null || (typeof row[field] === 'string' && row[field].trim() === '');
                              const hasError = isRequired && isEmpty;
                              
                              return (
                                <td key={field} className={`px-4 py-2 border-r border-slate-100 ${hasError ? 'bg-rose-50/10' : ''}`}>
                                  <input
                                    type={typeof row[field] === 'number' ? 'number' : 'text'}
                                    value={row[field] ?? ''}
                                    onChange={(e) => handleCellChange(activeTab, rowIndex, field, e.target.type === 'number' ? Number(e.target.value) : e.target.value)}
                                    placeholder={isRequired ? 'Required' : ''}
                                    className={`w-full px-2 py-1 bg-transparent border rounded font-semibold text-slate-700 outline-none transition-all ${
                                      hasError
                                        ? 'border-rose-400 bg-rose-50/30 hover:border-rose-500 focus:border-rose-500 placeholder-rose-400'
                                        : 'border-transparent hover:border-slate-200 focus:bg-white focus:border-violet-500'
                                    }`}
                                  />
                                </td>
                              );
                            })}
                            <td className="px-4 py-2 text-center">
                              <button
                                onClick={() => deleteRow(activeTab, rowIndex)}
                                className="text-xs font-bold text-rose-500 hover:text-rose-700 px-2 py-1 rounded bg-rose-50 hover:bg-rose-100 transition-colors"
                              >
                                Delete
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Import Results Banner */}
              {importResult && (
                <div className={`p-5 rounded-2xl border flex gap-4 ${
                  importResult.error_count === 0
                    ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                    : 'bg-amber-50 border-amber-200 text-amber-800'
                }`}>
                  {importResult.error_count === 0 ? (
                    <CheckCircle className="text-emerald-500 shrink-0" size={24} />
                  ) : (
                    <Info className="text-amber-500 shrink-0" size={24} />
                  )}
                  <div className="flex-1">
                    <p className="font-extrabold text-base">Database Sync Completed</p>
                    <p className="text-sm font-semibold mt-1">
                      Successfully imported <strong className="font-black text-slate-900">{importResult.imported}</strong> record(s) across all active tables ({importResult.skipped} skipped).
                    </p>
                    {importResult.error_count > 0 && (
                      <div className="mt-3">
                        <p className="font-extrabold text-xs uppercase tracking-wider text-rose-700">Errors Encountered ({importResult.error_count}):</p>
                        <div className="mt-1 space-y-1 max-h-24 overflow-y-auto text-xs font-mono bg-white/60 p-3 rounded-lg border border-slate-200">
                          {Object.entries(importResult.results || {}).map(([key, res]) => (
                            res.errors?.map((err, i) => {
                              const msg = typeof err === 'object' ? err.message : err;
                              const row = typeof err === 'object' && err.row ? ` (row ${err.row})` : '';
                              return (
                                <div key={`${key}-${i}`} className="text-rose-600">[{key.toUpperCase()}]{row} {msg}</div>
                              );
                            })
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <footer className="px-8 py-5 border-t border-slate-100 flex justify-between items-center bg-slate-50/50">
          <div className="flex items-center gap-4">
            {extractedData && (
              <button
                onClick={() => {
                  setExtractedData(null);
                  setFile(null);
                  setImportResult(null);
                }}
                className="text-sm font-extrabold text-slate-400 hover:text-slate-600 px-4 py-2 hover:bg-slate-100 rounded-xl transition-all"
              >
                Clear / Upload Another File
              </button>
            )}
            
            {extractedData && (() => {
              const missingCount = getMissingFieldsCount();
              if (missingCount > 0) {
                return (
                  <span className="flex items-center gap-1.5 text-xs font-black text-rose-600 bg-rose-50 border border-rose-100 px-3 py-1.5 rounded-xl animate-pulse">
                    <AlertTriangle size={14} className="shrink-0" />
                    {missingCount} required field(s) empty
                  </span>
                );
              }
              return null;
            })()}
          </div>
          <div className="flex gap-3">
            {extractedData ? (
              <>
                <button
                  onClick={downloadCSVs}
                  className="flex items-center gap-2 px-6 py-3 border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 font-extrabold text-sm rounded-xl shadow-sm transition-all duration-150 active:scale-95"
                >
                  <Download size={16} />
                  Download Filled CSVs
                </button>
                <button
                  onClick={importToDatabase}
                  disabled={importing}
                  className="flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-700 hover:to-indigo-700 text-white font-black text-sm rounded-xl shadow-md hover:shadow-lg transition-all duration-150 active:scale-95 disabled:opacity-55 disabled:active:scale-100"
                >
                  {importing ? (
                    <>
                      <Loader2 className="animate-spin" size={16} />
                      Syncing...
                    </>
                  ) : (
                    <>
                      <Database size={16} />
                      Sync to Database
                    </>
                  )}
                </button>
              </>
            ) : (
              <button
                onClick={onClose}
                className="px-6 py-3 border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 font-extrabold text-sm rounded-xl shadow-sm transition-all duration-150 active:scale-95"
              >
                Cancel
              </button>
            )}
          </div>
        </footer>

      </div>
    </div>
  );
}
