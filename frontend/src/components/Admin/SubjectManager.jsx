import React, { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { subjectAPI, departmentAPI, batchAPI, facultyAPI, classAPI } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import { useFormCache } from '../../hooks/useFormCache';
import ConfirmationModal from '../Layout/ConfirmationModal';
import { Edit, Trash2, Plus, GraduationCap } from 'lucide-react';
import CsvUploader from '../Layout/CsvUploader';

export default function SubjectManager() {
  const [subjects, setSubjects] = useState([]);
  const [classes, setClasses] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [batches, setBatches] = useState([]);
  const [faculty, setFaculty] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editData, setEditData] = useState(null);
  const [selectedDepartmentId, setSelectedDepartmentId] = useState(null);
  const { register, handleSubmit, reset, setValue, watch } = useForm();
  const { showToast } = useToast();

  // Modal State
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [subjectToDelete, setSubjectToDelete] = useState(null);
  
  // Watch all form fields for caching
  const formValues = watch();
  
  // Use form cache hook
  const { clearCache } = useFormCache('subjectFormCache', formValues, setValue, showForm, !!editData);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const subRes = await subjectAPI.getAll().catch(err => { console.error('Subjects fail', err); return { data: [] }; });
      const coreSubjects = (subRes.data || []).filter(sub => !sub.source_subject_id);
      setSubjects(coreSubjects);

      const deptRes = await departmentAPI.getAll().catch(err => { console.error('Depts fail', err); return { data: [] }; });
      setDepartments(deptRes.data);

      const batchRes = await batchAPI.getAll().catch(err => { console.error('Batches fail', err); return { data: [] }; });
      setBatches(batchRes.data);
    } catch (error) {
      console.error('Failed to load data', error);
      showToast('Failed to load data', 'error');
    }
  };

  const handleEdit = (sub) => {
    setEditData(sub);
    setValue('name', sub.name);
    setValue('code', sub.code);
    setValue('department_ids', sub.department_ids && sub.department_ids.length > 0 ? sub.department_ids : (sub.department_id ? [sub.department_id] : []));
    setValue('batch_id', sub.batch_id);
    setValue('hours_per_week', sub.hours_per_week);
    setValue('credits', sub.credits);
    setValue('requires_lab', sub.requires_lab ? 'true' : 'false');
    setShowForm(true);
    setTimeout(() => {
        document.querySelector('.main-content')?.scrollTo({ top: 0, behavior: 'smooth' });
    }, 50);
  };

  const onSubmit = async (data) => {
    try {
      const department_ids = Array.isArray(data.department_ids)
        ? data.department_ids.filter(Boolean)
        : data.department_ids ? [data.department_ids] : [];
      const payload = {
        ...data,
        department_ids,
        department_id: department_ids.length > 0 ? department_ids[0] : null,
        batch_id: data.batch_id || null,
        faculty_id: null,
        hours_per_week: parseInt(data.hours_per_week),
        credits: parseInt(data.credits) || 0,
        requires_lab: data.requires_lab === 'true'
      };

      if (editData) {
        await subjectAPI.update(editData.id, payload);
        showToast('Subject updated!', 'success');
      } else {
        await subjectAPI.create(payload);
        showToast('Subject created!', 'success');
      }

      reset();
      setEditData(null);
      setShowForm(false);
      clearCache();
      loadData();
    } catch (error) {
      showToast(error.response?.data?.detail || 'Failed to save subject', 'error');
    }
  };

  const confirmDelete = async () => {
    if (!subjectToDelete) return;
    try {
      await subjectAPI.delete(subjectToDelete);
      loadData();
      showToast('Subject deleted!', 'success');
    } catch (error) {
      showToast(error.response?.data?.detail || 'Failed to delete subject', 'error');
    }
  };

  const handleDeleteClick = (id) => {
    setSubjectToDelete(id);
    setIsDeleteModalOpen(true);
  };

  return (
    <div>
      <ConfirmationModal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        onConfirm={confirmDelete}
        title="Delete Subject"
        message="Are you sure you want to delete this subject?"
      />

      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <h1 className="text-3xl font-bold">Subjects</h1>
        <div className="flex gap-2">
          <CsvUploader type="subjects" onSuccess={loadData} />
          <button
            onClick={() => {
              setEditData(null);
              reset();
              setShowForm(!showForm);
            }}
            className="btn btn-primary flex items-center gap-2"
          >
            {showForm ? 'Cancel' : <><Plus size={20} /> Add Subject</>}
          </button>
        </div>
      </div>

      {showForm && (
        <div className="card mb-6">
          <h2 className="text-xl font-bold mb-4">{editData ? 'Edit Subject' : 'Add New Subject'}</h2>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div><label className="block text-sm font-medium mb-2">Name *</label><input {...register('name', { required: true })} className="input" /></div>
            <div><label className="block text-sm font-medium mb-2">Code *</label><input {...register('code', { required: true })} className="input" /></div>
            <div>
              <label className="block text-sm font-medium mb-2">Departments *</label>
              <select {...register('department_ids', { required: true })} multiple size={4} className="input h-32">
                {departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Batch *</label>
              <select {...register('batch_id', { required: true })} className="input"><option value="">Select</option>{batches.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select>
            </div>
            <div><label className="block text-sm font-medium mb-2">Hours/Week *</label><input {...register('hours_per_week', { required: true })} type="number" className="input" /></div>
            <div><label className="block text-sm font-medium mb-2">Credits *</label><input {...register('credits', { required: true })} type="number" className="input" defaultValue={3} /></div>
            <div><label className="block text-sm font-medium mb-2">Lab?</label><select {...register('requires_lab')} className="input"><option value="false">No</option><option value="true">Yes</option></select></div>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowForm(false)} className="btn btn-secondary">Cancel</button>
              <button type="submit" className="btn btn-primary">{editData ? 'Update' : 'Create'}</button>
            </div>
          </form>
        </div>
      )}

      {/* Department Cards Grid */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <GraduationCap className="text-blue-500" size={22} />
          Select Department
        </h2>
        
        {departments.length === 0 ? (
          <div className="p-4 bg-gray-50 rounded-lg text-gray-500 text-sm">
            No departments available. Please create departments first.
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {departments.map((dept) => {
              const deptSubjects = subjects.filter(sub => 
                (sub.department_ids && sub.department_ids.includes(dept.id)) || 
                sub.department_id === dept.id
              );
              const subjectCount = deptSubjects.length;
              const isSelected = selectedDepartmentId === dept.id;
              
              return (
                <button
                  key={dept.id}
                  onClick={() => setSelectedDepartmentId(isSelected ? null : dept.id)}
                  className={`w-full text-left rounded-xl p-4 transition-all duration-300 border flex flex-col justify-between h-28 hover:-translate-y-1 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500/20 ${
                    isSelected
                      ? 'bg-gradient-to-br from-blue-600 to-indigo-600 text-white border-transparent shadow-lg shadow-blue-500/10'
                      : 'bg-white text-gray-800 border-gray-100 hover:border-blue-100 hover:bg-blue-50/10'
                  }`}
                >
                  <div className="w-full">
                    <div className="flex justify-between items-start">
                      <span className={`text-xl font-bold tracking-wider ${isSelected ? 'text-white' : 'text-gray-900'}`}>
                        {dept.code}
                      </span>
                    </div>
                    <p className={`text-xs truncate font-normal mt-1 ${isSelected ? 'text-blue-100' : 'text-gray-500'}`} title={dept.name}>
                      {dept.name}
                    </p>
                  </div>
                  <div className={`text-xs font-semibold self-end px-2.5 py-1 rounded-full ${
                    isSelected ? 'bg-white/20 text-white' : 'bg-gray-50 text-gray-600'
                  }`}>
                    {subjectCount} {subjectCount === 1 ? 'Subject' : 'Subjects'}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {selectedDepartmentId === null ? (
        <div className="card text-center py-16 bg-white border border-dashed border-gray-200 rounded-xl shadow-sm">
          <div className="max-w-md mx-auto flex flex-col items-center">
            <div className="w-16 h-16 rounded-full bg-blue-50 flex items-center justify-center text-blue-600 mb-4 animate-pulse">
              <GraduationCap size={32} />
            </div>
            <p className="text-xl font-bold text-gray-800">Select a Department</p>
            <p className="text-gray-500 mt-2 text-sm leading-relaxed">
              Please click on one of the department cards above to view and manage its subjects.
            </p>
          </div>
        </div>
      ) : (
        <div>
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-700">
              Subjects in {departments.find(d => d.id === selectedDepartmentId)?.name || 'Selected Department'}
            </h2>
            <span className="text-sm bg-blue-50 text-blue-700 px-3 py-1 rounded-full font-medium">
              {subjects.filter(sub => (sub.department_ids && sub.department_ids.includes(selectedDepartmentId)) || sub.department_id === selectedDepartmentId).length} Found
            </span>
          </div>

          {subjects.filter(sub => (sub.department_ids && sub.department_ids.includes(selectedDepartmentId)) || sub.department_id === selectedDepartmentId).length === 0 ? (
            <div className="card text-center py-12 bg-white border border-gray-100 rounded-xl">
              <p className="text-lg font-semibold text-gray-700">No subjects configured.</p>
              <p className="text-gray-500 mt-1 text-sm">Create a new subject for this department using the "Add Subject" button above.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {subjects
                .filter(sub => (sub.department_ids && sub.department_ids.includes(selectedDepartmentId)) || sub.department_id === selectedDepartmentId)
                .map(sub => (
                  <div key={sub.id} className="card relative group hover:shadow-lg transition-shadow">
                    <div className="absolute top-2 right-2 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => handleEdit(sub)}
                        className="p-1.5 text-blue-600 hover:bg-blue-50 rounded-full transition-colors"
                        title="Edit Subject"
                      >
                        <Edit size={18} />
                      </button>
                      <button
                        onClick={() => handleDeleteClick(sub.id)}
                        className="p-1.5 text-red-600 hover:bg-red-50 rounded-full transition-colors"
                        title="Delete Subject"
                      >
                        <Trash2 size={18} />
                      </button>
                    </div>

                    <h3 className="text-xl font-bold pr-16">{sub.name}</h3>
                    <p>Code: {sub.code}</p>
                    <p className="text-sm text-gray-600">
                      Departments: {sub.department_ids && sub.department_ids.length > 0 ? sub.department_ids.map(id => departments.find(d => d.id === id)?.name || id).filter(Boolean).join(', ') : departments.find(d => d.id === sub.department_id)?.name}
                    </p>
                    <p className="text-sm text-gray-600">Batch: {batches.find(b => b.id === sub.batch_id)?.name}</p>
                    <p>Hours/Week: {sub.hours_per_week}</p>
                    <p>Credits: {sub.credits || 3}</p>
                    <p>Lab: {sub.requires_lab ? 'Yes' : 'No'}</p>
                  </div>
                ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
