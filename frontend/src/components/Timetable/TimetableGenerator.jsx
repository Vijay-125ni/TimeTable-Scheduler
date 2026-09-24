import React, { useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { FileText, Loader2, Upload, X } from 'lucide-react';
import { timetableAPI } from '../../services/api';
import { useToast } from '../../context/ToastContext';

// ── Small helper components ────────────────────────────────────────────────────

function DiagnosticPanel({ title, items, color, icon }) {
  if (!items || items.length === 0) return null;
  const styles = {
    amber:  { card: 'bg-amber-50 border-amber-300',  title: 'text-amber-800', item: 'text-amber-700', dot: 'bg-amber-400' },
    yellow: { card: 'bg-yellow-50 border-yellow-300', title: 'text-yellow-800', item: 'text-yellow-700', dot: 'bg-yellow-400' },
    blue:   { card: 'bg-blue-50 border-blue-300',    title: 'text-blue-800',   item: 'text-blue-700',  dot: 'bg-blue-400'   },
    orange: { card: 'bg-orange-50 border-orange-300', title: 'text-orange-800', item: 'text-orange-700', dot: 'bg-orange-400' },
    red:    { card: 'bg-red-50 border-red-300',       title: 'text-red-800',   item: 'text-red-700',   dot: 'bg-red-400'    },
  };
  const s = styles[color] || styles.blue;
  return (
    <div className={`rounded-xl border-2 p-4 ${s.card}`}>
      <h4 className={`font-semibold text-sm mb-2 flex items-center gap-2 ${s.title}`}>
        <span>{icon}</span>{title}
      </h4>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={i} className={`text-sm flex items-start gap-2 ${s.item}`}>
            <span className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${s.dot}`} />
            {typeof item === 'object' ? (item.reason || JSON.stringify(item)) : item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function SubstitutesPanel({ substitutes }) {
  if (!substitutes || Object.keys(substitutes).length === 0) return null;
  
  return (
    <div className="rounded-xl border-2 bg-purple-50 border-purple-300 p-4">
      <h4 className="font-semibold text-sm mb-3 flex items-center gap-2 text-purple-800">
        <span>👥</span> Alternate Faculty for Absent Staff
      </h4>
      <div className="space-y-4">
        {Object.entries(substitutes).map(([facultyName, data]) => (
          <div key={facultyName} className="bg-white rounded-lg p-3 border border-purple-200">
            <div className="font-semibold text-purple-700 mb-2">
              👤 {facultyName}
            </div>
            <div className="text-xs text-gray-600 mb-2">
              Absent on: <span className="font-medium text-gray-700">{data.absent_days?.join(', ')}</span>
            </div>
            {data.subjects && Object.entries(data.subjects).map(([subject, dayMap]) => (
              <div key={subject} className="ml-3 mt-2 text-xs">
                <div className="text-gray-600 font-medium mb-1">
                  📚 {subject.trim()}
                </div>
                {Object.entries(dayMap).map(([day, alternates]) => (
                  <div key={day} className="ml-2 text-gray-700 py-1">
                    <span className="text-purple-600 font-medium">{day}:</span>{' '}
                    {Array.isArray(alternates) && alternates.length > 0 ? (
                      <span className="text-gray-600">
                        {alternates.slice(0, 3).map(alt => alt.trim()).join(' • ')}
                        {alternates.length > 3 && ` +${alternates.length - 3} more`}
                      </span>
                    ) : (
                      <span className="text-red-600 italic">No alternatives</span>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

export default function TimetableGenerator() {
  const [generating, setGenerating] = useState(false);
  const [extractingFiles, setExtractingFiles] = useState(false);
  const [result, setResult] = useState(null);
  const [constraintFiles, setConstraintFiles] = useState([]);
  const [fileConstraintReport, setFileConstraintReport] = useState(null);
  const fileInputRef = useRef(null);
  const { register, handleSubmit, getValues, setValue } = useForm();
  const { showToast } = useToast();

  const handleConstraintFileSelect = (event) => {
    const selected = Array.from(event.target.files || []);
    if (!selected.length) return;
    setConstraintFiles((current) => [...current, ...selected].slice(0, 10));
    setFileConstraintReport(null);
    event.target.value = '';
  };

  const removeConstraintFile = (index) => {
    setConstraintFiles((current) => current.filter((_, i) => i !== index));
    setFileConstraintReport(null);
  };

  const clearConstraintFiles = () => {
    setConstraintFiles([]);
    setFileConstraintReport(null);
  };

  const buildConstraintsFromFiles = async () => {
    if (!constraintFiles.length) {
      showToast('Add at least one timetable file first.', 'error');
      return;
    }

    setExtractingFiles(true);
    try {
      const response = await timetableAPI.generateConstraintsFromFiles(constraintFiles, {
        periods_per_day: 9,
      });
      const generatedText = response.data?.constraints_text || '';
      if (!generatedText.trim()) {
        showToast('No constraints could be generated from those files.', 'error');
        return;
      }

      const existingText = (getValues('constraints_text') || '').trim();
      const nextText = existingText ? `${existingText}\n\n${generatedText}` : generatedText;
      setValue('constraints_text', nextText, { shouldDirty: true, shouldTouch: true });
      setFileConstraintReport(response.data);

      const count = response.data?.custom_constraints?.length || 0;
      showToast(`${count || 'Some'} constraints generated from uploaded files.`, 'success');
    } catch (error) {
      showToast(error.response?.data?.detail || 'Failed to read timetable files', 'error');
    } finally {
      setExtractingFiles(false);
    }
  };

  const formatFileSize = (file) => {
    if (!file?.size) return '';
    if (file.size < 1024 * 1024) return `${Math.max(1, Math.round(file.size / 1024))} KB`;
    return `${(file.size / (1024 * 1024)).toFixed(1)} MB`;
  };

  const onSubmit = async (data) => {
    setGenerating(true);
    setResult(null);
    try {
      const response = await timetableAPI.generate({
        name: data.name,
        academic_year: data.academic_year,
        semester: parseInt(data.semester),
        working_days: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
        periods_per_day: 9,
        start_time: '09:00',
        end_time: '16:00',
        period_duration_mins: 60,
        break_duration_mins: 15,
        lunch_duration_mins: 60,
        break2_duration_mins: 15,
        constraints_text: data.constraints_text || null,
      });
      setResult(response.data);
      showToast('Timetable generated successfully!', 'success');
    } catch (error) {
      showToast(error.response?.data?.detail || 'Failed to generate timetable', 'error');
    } finally {
      setGenerating(false);
    }
  };

  // Extract diagnostics from result
  const cu = result?.constraints_used || {};
  const parseDiag    = cu.parse_diagnostics || {};
  const corrections  = parseDiag.corrections   || [];
  const parseWarnings= parseDiag.warnings      || [];
  const unrecognized = parseDiag.unrecognized  || [];
  const autoAdj      = cu.auto_adjustments     || [];
  const constrWarn   = cu.constraint_warnings  || [];
  const substitutes  = cu.substitutes          || {};
  const extractedRows = fileConstraintReport?.extracted_timetable || [];
  const documentAnalysis = fileConstraintReport?.document_analysis || {};

  const hasDiagnostics = corrections.length || parseWarnings.length || unrecognized.length || autoAdj.length || constrWarn.length || Object.keys(substitutes).length > 0;

  return (
    <div className="max-w-3xl mx-auto py-8 px-4">
      <h1 className="text-3xl font-bold mb-2 text-gray-900">Generate Timetable</h1>
      <p className="text-gray-500 mb-8 text-sm">
        The AI engine will auto-correct common errors and build an optimised schedule.
      </p>

      {/* ── Form ─────────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 mb-6">
        <h2 className="text-lg font-semibold mb-5 text-gray-800">Schedule Configuration</h2>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name *</label>
              <input {...register('name', { required: true })} className="input w-full" placeholder="Fall 2024" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Academic Year *</label>
              <input {...register('academic_year', { required: true })} className="input w-full" placeholder="2024-2025" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Semester *</label>
              <input {...register('semester', { required: true })} type="number" min="1" max="12" className="input w-full" placeholder="1" />
            </div>
          </div>

          {/* AI Constraints */}
          <div className="border-t pt-5">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xl">🤖</span>
              <h3 className="text-base font-semibold text-indigo-700">AI Constraints</h3>
              <span className="text-xs bg-indigo-100 text-indigo-600 px-2 py-0.5 rounded-full">Optional</span>
            </div>
            <p className="text-xs text-gray-500 mb-3">
              Type in plain English. The AI will parse and auto-correct names, typos, and common patterns.
            </p>

            <div className="rounded-xl border border-dashed border-indigo-200 bg-indigo-50/40 p-3 mb-3">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={handleConstraintFileSelect}
              />

              <div className="flex flex-col sm:flex-row sm:items-center gap-2">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="btn btn-secondary flex items-center justify-center gap-2 text-sm"
                >
                  <Upload size={16} />
                  Add Files
                </button>
                <button
                  type="button"
                  onClick={buildConstraintsFromFiles}
                  disabled={!constraintFiles.length || extractingFiles}
                  className="btn btn-primary flex items-center justify-center gap-2 text-sm disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {extractingFiles ? <Loader2 size={16} className="animate-spin" /> : <FileText size={16} />}
                  Generate Constraints
                </button>
                {constraintFiles.length > 0 && (
                  <button
                    type="button"
                    onClick={clearConstraintFiles}
                    className="text-xs text-gray-500 hover:text-red-600 px-2 py-2"
                  >
                    Clear
                  </button>
                )}
              </div>

              {constraintFiles.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-3">
                  {constraintFiles.map((file, index) => (
                    <span
                      key={`${file.name}-${index}`}
                      className="inline-flex max-w-full items-center gap-2 rounded-lg bg-white border border-indigo-100 px-2 py-1 text-xs text-gray-700"
                    >
                      <FileText size={14} className="text-indigo-500 flex-shrink-0" />
                      <span className="truncate max-w-[220px]">{file.name}</span>
                      <span className="text-gray-400 flex-shrink-0">{formatFileSize(file)}</span>
                      <button
                        type="button"
                        onClick={() => removeConstraintFile(index)}
                        className="text-gray-400 hover:text-red-500 flex-shrink-0"
                        title={`Remove ${file.name}`}
                      >
                        <X size={14} />
                      </button>
                    </span>
                  ))}
                </div>
              )}

              {fileConstraintReport && (
                <div className="mt-3 rounded-lg border border-indigo-100 bg-white p-3 text-xs text-gray-600">
                  <div className="font-semibold text-indigo-700 mb-2">
                    {fileConstraintReport.custom_constraints?.length || 0} parsed constraints
                    {` • ${extractedRows.length} extracted timetable rows`}
                  </div>
                  <div className="mb-2 text-gray-500">
                    Analysis: {documentAnalysis.source || 'unknown'}
                    {documentAnalysis.model ? ` (${documentAnalysis.model})` : ''}
                  </div>
                  <div className="space-y-1">
                    {fileConstraintReport.files?.map((file, index) => (
                      <div key={`${file.filename}-${index}`} className="flex flex-wrap gap-x-2">
                        <span className="font-medium text-gray-700">{file.filename}</span>
                        <span>{file.extractor}</span>
                        <span>{file.characters} chars</span>
                      </div>
                    ))}
                  </div>
                  {fileConstraintReport.warnings?.length > 0 && (
                    <ul className="mt-2 space-y-1 text-amber-700">
                      {fileConstraintReport.warnings.slice(0, 4).map((warning, index) => (
                        <li key={index}>{warning}</li>
                      ))}
                    </ul>
                  )}
                  {extractedRows.length > 0 && (
                    <div className="mt-3 border-t border-indigo-50 pt-2">
                      <div className="font-medium text-gray-700 mb-1">Extracted JSON preview</div>
                      <div className="space-y-1">
                        {extractedRows.slice(0, 3).map((row, index) => (
                          <div key={index} className="rounded-md bg-gray-50 px-2 py-1">
                            <span className="font-medium">
                              {row.course_details?.subject_code || 'No code'}
                            </span>
                            {' — '}
                            <span>{row.course_details?.subject_name || 'Unnamed row'}</span>
                            {row.faculty_assignment?.full_name ? (
                              <span className="text-gray-500"> • {row.faculty_assignment.full_name}</span>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            <textarea
              {...register('constraints_text')}
              className="input w-full h-36 text-sm font-mono"
              placeholder={`Examples:\n• Dr. Shiva cannot teach on Fridays\n• All lab sessions must be consecutive\n• Mathematics should be in the morning\n• Don't schedule CSE-A in period 7 and 8\n• Prof. Meena is available only on Mon, Tue, Thu`}
            />
            {/* Hint chips */}
            <div className="flex flex-wrap gap-2 mt-2">
              {[
                'Faculty unavailability', 'Lab consecutive', 'Morning preference',
                'Subject max/day', 'Avoid period', 'Specific slot',
              ].map(hint => (
                <span key={hint} className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-full">{hint}</span>
              ))}
            </div>
          </div>

          <button
            type="submit"
            disabled={generating}
            className="btn btn-primary w-full py-3 text-base font-semibold flex items-center justify-center gap-2"
          >
            {generating ? (
              <>
                <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
                </svg>
                Generating schedule…
              </>
            ) : '✨ Generate Timetable'}
          </button>
        </form>
      </div>

      {/* ── Success result ────────────────────────────────────────────────── */}
      {result && (
        <div className="space-y-4">
          {/* Status card */}
          <div className="bg-green-50 border-2 border-green-400 rounded-2xl p-5">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 bg-green-500 rounded-full flex items-center justify-center text-white text-lg">✓</div>
              <div>
                <h2 className="text-lg font-bold text-green-800">Timetable Generated!</h2>
                <p className="text-sm text-green-600">ID: {result.id}</p>
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
              {[
                { label: 'Status',   value: result.solver_status },
                { label: 'Solved in',value: `${parseFloat(result.solve_time_seconds).toFixed(1)}s` },
                { label: 'Year',     value: result.academic_year },
                { label: 'Semester', value: result.semester },
              ].map(({ label, value }) => (
                <div key={label} className="bg-white rounded-xl p-3 shadow-sm">
                  <div className="text-xs text-gray-500">{label}</div>
                  <div className="font-semibold text-gray-800 text-sm">{value}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Diagnostics */}
          {hasDiagnostics && (
            <div className="bg-white border border-gray-200 rounded-2xl p-5 space-y-3">
              <h3 className="font-semibold text-gray-700 flex items-center gap-2">
                <span>🔍</span> Smart Scheduling Report
              </h3>

              <SubstitutesPanel substitutes={substitutes} />
              
              <DiagnosticPanel
                title="Auto-corrected Names"
                items={corrections}
                color="amber"
                icon="✏️"
              />
              <DiagnosticPanel
                title="Workload Auto-adjustments"
                items={autoAdj}
                color="blue"
                icon="⚖️"
              />
              <DiagnosticPanel
                title="Constraint Warnings (skipped)"
                items={constrWarn}
                color="orange"
                icon="⚠️"
              />
              <DiagnosticPanel
                title="Partially Understood Constraints"
                items={parseWarnings}
                color="yellow"
                icon="💡"
              />
              <DiagnosticPanel
                title="Unrecognized Phrases"
                items={unrecognized}
                color="red"
                icon="❓"
              />
            </div>
          )}
        </div>
      )}

      {/* ── Tips ─────────────────────────────────────────────────────────── */}
      {!result && (
        <div className="bg-blue-50 border border-blue-200 rounded-2xl p-5">
          <h3 className="font-semibold text-blue-800 mb-3 flex items-center gap-2">
            <span>💡</span> How it works
          </h3>
          <ul className="space-y-2 text-blue-700 text-sm">
            <li>📌 <strong>No hours_per_week?</strong> Automatically derived from subject credit score (3 credits = 3 hrs/week)</li>
            <li>📌 <strong>Schedule too full?</strong> Low-priority subjects are auto-reduced; labs and high-credit subjects are protected</li>
            <li>📌 <strong>Typo in a faculty name?</strong> Fuzzy matching will auto-correct it and tell you what changed</li>
            <li>📌 <strong>Bad constraint?</strong> It's skipped with a warning — the schedule still generates</li>
            <li>📌 All 8 constraint types are supported: availability, consecutive, max/day, preferred slot, avoid period, gap, and more</li>
          </ul>
        </div>
      )}
    </div>
  );
}
