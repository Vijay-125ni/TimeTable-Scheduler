import React, { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { batchAPI } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import { useFormCache } from '../../hooks/useFormCache';
import ConfirmationModal from '../Layout/ConfirmationModal';
import CsvUploader from '../Layout/CsvUploader';
import { Edit, Trash2, Plus } from 'lucide-react';

export default function BatchManager() {
    const [batches, setBatches] = useState([]);
    const [showForm, setShowForm] = useState(false);
    const [editData, setEditData] = useState(null);
    const { register, handleSubmit, reset, setValue, watch } = useForm();
    const { showToast } = useToast();

    // Modal State
    const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
    const [batchToDelete, setBatchToDelete] = useState(null);

    // Watch all form fields for caching
    const formValues = watch();

    // Use form cache hook
    const { clearCache } = useFormCache('batchFormCache', formValues, setValue, showForm, !!editData);

    const loadBatches = async () => {
        try {
            const res = await batchAPI.getAll();
            setBatches(res.data);
        } catch (error) {
            console.error("Failed to load batches", error);
            showToast("Failed to load batches", "error");
        }
    };

    useEffect(() => {
        loadBatches();
    }, []);

    // Breaks state: array of { start, start_ampm, end, end_ampm }
    const [breaks, setBreaks] = useState([]);

    const addBreakRow = () => setBreaks(prev => [...prev, { start: '', start_ampm: 'AM', end: '', end_ampm: 'AM' }]);
    const removeBreakRow = (idx) => setBreaks(prev => prev.filter((_, i) => i !== idx));
    const updateBreakRow = (idx, field, value) => setBreaks(prev => prev.map((b, i) => i === idx ? { ...b, [field]: value } : b));

    const handleEdit = (batch) => {
        setEditData(batch);
        setValue('name', batch.name);
        setValue('period_duration', batch.period_duration);
        setValue('start_time', batch.start_time);
        setValue('end_time', batch.end_time);

        if (batch.lunch_break) {
            setValue('lunch_start', batch.lunch_break.start);
            setValue('lunch_end', batch.lunch_break.end);
        } else {
            setValue('lunch_start', '');
            setValue('lunch_end', '');
        }

        if (batch.break_times) {
            // Populate structured breaks state (convert 24h -> 12h with AM/PM for editing)
            const parsed = batch.break_times.map(b => {
                const start = b.start || '';
                const end = b.end || '';
                const toAmpm = (t) => {
                    if (!t) return { time: '', ampm: 'AM' };
                    const [hh, mm] = t.split(':').map(Number);
                    const ampm = hh >= 12 ? 'PM' : 'AM';
                    const hour12 = ((hh + 11) % 12) + 1;
                    const pad = (n) => String(n).padStart(2, '0');
                    return { time: `${pad(hour12)}:${pad(mm)}`, ampm };
                };
                const s = toAmpm(start);
                const e = toAmpm(end);
                return { start: s.time, start_ampm: s.ampm, end: e.time, end_ampm: e.ampm };
            });
            setBreaks(parsed);
        } else {
            setBreaks([]);
        }

        setShowForm(true);
        setTimeout(() => {
            document.querySelector('.main-content')?.scrollTo({ top: 0, behavior: 'smooth' });
        }, 50);
    };

    const onSubmit = async (data) => {
        try {
            // Build breaks payload from structured `breaks` state (convert 12h->24h using AM/PM)
            const to24 = (time, ampm) => {
                if (!time) return '';
                const [hh, mm] = time.split(':').map(Number);
                let h = hh % 12;
                if (ampm === 'PM') h += 12;
                const pad = (n) => String(n).padStart(2, '0');
                return `${pad(h)}:${pad(mm)}`;
            };

            const parsedBreaks = (breaks && breaks.length > 0)
                ? breaks.filter(b => b.start && b.end).map(b => ({ start: to24(b.start, b.start_ampm), end: to24(b.end, b.end_ampm) }))
                : (data.breaks_text ? data.breaks_text.split('\n').filter(line => line.includes('-')).map(line => {
                    const [start, end] = line.split('-').map(s => s.trim());
                    return { start, end };
                }) : []);

            const payload = {
                name: data.name,
                start_time: data.start_time,
                end_time: data.end_time,
                period_duration: parseInt(data.period_duration),
                break_times: parsedBreaks,
                lunch_break: data.lunch_start && data.lunch_end ? { start: data.lunch_start, end: data.lunch_end } : {}
            };

            if (editData) {
                await batchAPI.update(editData.id, payload);
                showToast("Batch updated successfully!", "success");
            } else {
                await batchAPI.create(payload);
                showToast("Batch created successfully!", "success");
            }

            reset();
            setEditData(null);
            setShowForm(false);
            clearCache();
            setBreaks([]);
            loadBatches();
        } catch (error) {
            showToast("Failed to save batch: " + error.message, "error");
        }
    };

    const confirmDelete = async () => {
        if (!batchToDelete) return;
        try {
            await batchAPI.delete(batchToDelete);
            loadBatches();
            showToast("Batch deleted!", "success");
        } catch (error) {
            showToast("Failed to delete batch", "error");
        }
    };

    const handleDeleteClick = (id) => {
        setBatchToDelete(id);
        setIsDeleteModalOpen(true);
    };

    return (
        <div>
            <ConfirmationModal
                isOpen={isDeleteModalOpen}
                onClose={() => setIsDeleteModalOpen(false)}
                onConfirm={confirmDelete}
                title="Delete Batch"
                message="Are you sure you want to delete this batch configuration?"
            />

            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                <h1 className="text-3xl font-bold">Batch Configurations</h1>
                <div className="flex gap-2">
                    <CsvUploader type="batches" onSuccess={loadBatches} />
                    <button
                        onClick={() => {
                            // If opening the form for a new batch, clear previous state and cache
                            if (!showForm) {
                                setEditData(null);
                                reset();
                                clearCache();
                                setBreaks([]);
                                setShowForm(true);
                                setTimeout(() => {
                                    document.querySelector('.main-content')?.scrollTo({ top: 0, behavior: 'smooth' });
                                }, 50);
                                return;
                            }
                            setShowForm(false);
                        }}
                        className="btn btn-primary flex items-center gap-2"
                    >
                        {showForm ? 'Cancel' : <><Plus size={20} /> Add Batch</>}
                    </button>
                </div>
            </div>

            {showForm && (
                <div className="card mb-6 bg-white p-6 rounded-lg shadow-sm border border-gray-100">
                    <h2 className="text-xl font-bold mb-4">{editData ? 'Edit Batch Configuration' : 'Add New Batch Configuration'}</h2>
                    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            <div><label className="block text-sm font-medium mb-1">Batch Name *</label><input {...register('name', { required: true })} className="input w-full border rounded p-2" placeholder="e.g. 1st Year Main block" /></div>
                            <div><label className="block text-sm font-medium mb-1">Period Duration (mins) *</label><input {...register('period_duration', { required: true })} type="number" defaultValue="60" className="input w-full border rounded p-2" /></div>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div><label className="block text-sm font-medium mb-1">College Start Time *</label><input {...register('start_time', { required: true })} type="time" defaultValue="09:00" className="input w-full border rounded p-2" /></div>
                            <div><label className="block text-sm font-medium mb-1">College End Time *</label><input {...register('end_time', { required: true })} type="time" defaultValue="16:00" className="input w-full border rounded p-2" /></div>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div><label className="block text-sm font-medium mb-1">Lunch Start</label><input {...register('lunch_start')} type="time" className="input w-full border rounded p-2" /></div>
                            <div><label className="block text-sm font-medium mb-1">Lunch End</label><input {...register('lunch_end')} type="time" className="input w-full border rounded p-2" /></div>
                        </div>

                        <div>
                            <label className="block text-sm font-medium mb-1">Breaks</label>
                            <div className="space-y-2">
                                {breaks.map((b, idx) => (
                                    <div key={idx} className="grid grid-cols-4 gap-2 items-center">
                                        <input type="time" value={b.start} onChange={(e) => updateBreakRow(idx, 'start', e.target.value)} className="input p-2" />
                                        <select value={b.start_ampm} onChange={(e) => updateBreakRow(idx, 'start_ampm', e.target.value)} className="input p-2">
                                            <option>AM</option>
                                            <option>PM</option>
                                        </select>
                                        <input type="time" value={b.end} onChange={(e) => updateBreakRow(idx, 'end', e.target.value)} className="input p-2" />
                                        <select value={b.end_ampm} onChange={(e) => updateBreakRow(idx, 'end_ampm', e.target.value)} className="input p-2">
                                            <option>AM</option>
                                            <option>PM</option>
                                        </select>
                                        <div className="col-span-4 flex justify-end">
                                            <button type="button" onClick={() => removeBreakRow(idx)} className="btn btn-secondary ml-2">Remove</button>
                                        </div>
                                    </div>
                                ))}
                                <div className="flex gap-2">
                                    <button type="button" onClick={addBreakRow} className="btn btn-outline">Add Break</button>
                                    <span className="text-sm text-gray-500 self-center">Enter start/end times and select AM/PM for each break (optional).</span>
                                </div>
                                <div className="pt-2">
                                    <label className="block text-sm font-medium mb-1">Or paste legacy breaks (one per line HH:MM-HH:MM)</label>
                                    <textarea {...register('breaks_text')} className="input w-full border rounded p-2 h-20 font-mono text-sm" placeholder="10:30-10:45\n15:00-15:15"></textarea>
                                </div>
                            </div>
                        </div>

                        <div className="flex justify-end gap-2">
                            <button
                                type="button"
                                onClick={() => {
                                    setShowForm(false);
                                    setEditData(null);
                                    reset();
                                }}
                                className="btn btn-secondary"
                            >
                                Cancel
                            </button>
                            <button type="submit" className="btn btn-primary py-2 bg-blue-600 text-white rounded hover:bg-blue-700">{editData ? 'Update Configuration' : 'Create Configuration'}</button>
                        </div>
                    </form>
                </div>
            )}

            {batches.length === 0 ? (
                <div className="card text-center py-12">
                    <p className="text-xl text-gray-600">No batches configured.</p>
                    <p className="text-gray-500 mt-2">Create one to define timings for student groups.</p>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {batches.map(b => (
                        <div key={b.id} className="card relative group hover:shadow-lg transition-shadow">
                            <div className="absolute top-2 right-2 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button
                                    onClick={() => handleEdit(b)}
                                    className="p-1.5 text-blue-600 hover:bg-blue-50 rounded-full transition-colors"
                                    title="Edit Batch"
                                >
                                    <Edit size={18} />
                                </button>
                                <button onClick={() => handleDeleteClick(b.id)} className="p-1.5 text-red-600 hover:bg-red-50 rounded-full transition-colors" title="Delete Batch">
                                    <Trash2 size={18} />
                                </button>
                            </div>

                            <h3 className="font-bold text-lg mb-2">{b.name}</h3>
                            <div className="text-sm text-gray-600 space-y-1">
                                <p>🕒 {b.start_time} - {b.end_time}</p>
                                <p>⏱️ {b.period_duration} mins/period</p>
                                {b.lunch_break && b.lunch_break.start && (
                                    <p>🍱 Lunch: {b.lunch_break.start} - {b.lunch_break.end}</p>
                                )}
                                {b.break_times && b.break_times.length > 0 && (
                                    <div className="mt-2 text-xs bg-gray-50 p-2 rounded">
                                        <strong>Breaks:</strong>
                                        {b.break_times.map((br, idx) => (
                                            <div key={idx}>{br.start} - {br.end}</div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}