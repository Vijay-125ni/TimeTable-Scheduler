import React, { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { departmentAPI } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import { useFormCache } from '../../hooks/useFormCache';
import ConfirmationModal from '../Layout/ConfirmationModal';
import { Edit, Trash2, Plus, AlertTriangle } from 'lucide-react';
import CsvUploader from '../Layout/CsvUploader';

export default function DepartmentManager() {
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editData, setEditData] = useState(null);
  const { register, handleSubmit, reset, setValue, watch, formState: { errors } } = useForm();
  const { showToast } = useToast();
  
  // Get form values for caching
  const formValues = watch();
  
  // Use form cache hook
  const { clearCache } = useFormCache('departmentFormCache', formValues, setValue, showForm, !!editData);

  // Confirmation Modal State
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [departmentToDelete, setDepartmentToDelete] = useState(null);

  useEffect(() => {
    loadDepartments();
  }, []);

  const loadDepartments = async () => {
    try {
      const response = await departmentAPI.getAll();
      setDepartments(response.data);
    } catch (error) {
      console.error('Failed to load departments', error);
      showToast('Failed to load departments', 'error');
    } finally {
      setLoading(false);
    }
  };

  const incompleteDepartments = departments.filter(d => !d.name || d.name === '[Missing Name]' || !d.code || !d.code.trim());

  const handleEdit = (dept) => {
    setEditData(dept);
    setValue('name', dept.name === '[Missing Name]' ? '' : dept.name);
    setValue('code', dept.code || '');
    setShowForm(true);
    setTimeout(() => {
        document.querySelector('.main-content')?.scrollTo({ top: 0, behavior: 'smooth' });
    }, 50);
  };

  const onSubmit = async (data) => {
    try {
      if (editData) {
        await departmentAPI.update(editData.id, data);
        showToast('Department updated!', 'success');
      } else {
        await departmentAPI.create(data);
        showToast('Department created!', 'success');
      }

      reset();
      setEditData(null);
      setShowForm(false);
      clearCache();
      loadDepartments();
    } catch (error) {
      showToast(error.response?.data?.detail || 'Failed to save department', 'error');
    }
  };

  const confirmDelete = async () => {
    if (!departmentToDelete) return;
    try {
      await departmentAPI.delete(departmentToDelete);
      loadDepartments();
      showToast('Deleted!', 'success');
    } catch (error) {
      showToast(error.response?.data?.detail || 'Failed to delete', 'error');
    }
  };

  const handleDeleteClick = (id) => {
    setDepartmentToDelete(id);
    setIsDeleteModalOpen(true);
  };

  return (
    <div>
      <ConfirmationModal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        onConfirm={confirmDelete}
        title="Delete Department"
        message="Are you sure you want to delete this department? This action cannot be undone."
      />

      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <div>
          <h1 className="text-3xl font-bold">Departments</h1>
          <p className="text-sm text-slate-500 font-medium">Manage all academic department names and codes.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => {
              setEditData(null);
              reset();
              setShowForm(!showForm);
            }}
            className="btn btn-primary flex items-center gap-2"
          >
            {showForm ? 'Cancel' : <><Plus size={20} /> Add Department</>}
          </button>
          <CsvUploader type="departments" />
        </div>
      </div>

      {incompleteDepartments.length > 0 && (
        <div className="mb-6 p-4 rounded-2xl bg-amber-50 border border-amber-200 text-amber-900 flex items-start gap-3 shadow-sm">
          <AlertTriangle size={20} className="text-amber-600 shrink-0 mt-0.5" />
          <div>
            <h4 className="font-extrabold text-sm text-amber-900">
              {incompleteDepartments.length} Department(s) have missing details!
            </h4>
            <p className="text-xs text-amber-700 mt-0.5">
              Please click the edit button on highlighted cards to enter the missing Department Name or Code.
            </p>
          </div>
        </div>
      )}

      {showForm && (
        <div className="card mb-6 border-2 border-primary-500/20">
          <h2 className="text-xl font-semibold mb-4">{editData ? 'Edit Department' : 'Add New Department'}</h2>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Name *</label>
              <input
                {...register('name', { required: true })}
                className={`input ${editData && (!watch('name') || watch('name') === '[Missing Name]') ? 'border-amber-500 bg-amber-50/50' : ''}`}
                placeholder="Computer Science"
              />
              {errors.name && <p className="text-red-500 text-sm">Name required</p>}
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Code *</label>
              <input
                {...register('code', { required: true })}
                className={`input ${editData && (!watch('code') || !watch('code').trim()) ? 'border-amber-500 bg-amber-50/50' : ''}`}
                placeholder="CSE"
              />
              {errors.code && <p className="text-red-500 text-sm">Code required</p>}
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setShowForm(false)} className="btn btn-secondary">Cancel</button>
              <button type="submit" className="btn btn-primary">{editData ? 'Update' : 'Create'}</button>
            </div>
          </form>
        </div>
      )}

      {loading ? <div className="text-center py-12">Loading...</div> : departments.length === 0 ? (
        <div className="card text-center py-12">
          <p className="text-xl text-gray-600">There are no departments.</p>
          <p className="text-gray-500 mt-2">Kindly add it.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {departments.map((dept) => {
            const isMissing = !dept.name || dept.name === '[Missing Name]' || !dept.code || !dept.code.trim();
            return (
              <div
                key={dept.id}
                className={`card relative group hover:shadow-lg transition-all ${
                  isMissing ? 'border-2 border-amber-400 bg-amber-50/30' : ''
                }`}
              >
                {isMissing && (
                  <span className="absolute top-2 left-2 px-2 py-0.5 text-[10px] font-black rounded-full bg-amber-500 text-white flex items-center gap-1 shadow-sm">
                    <AlertTriangle size={12} /> Missing Field(s)
                  </span>
                )}
                <div className="absolute top-2 right-2 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => handleEdit(dept)}
                    className="p-1.5 text-blue-600 hover:bg-blue-50 rounded-full transition-colors"
                    title="Edit Department"
                  >
                    <Edit size={18} />
                  </button>
                  <button
                    onClick={() => handleDeleteClick(dept.id)}
                    className="p-1.5 text-red-600 hover:bg-red-50 rounded-full transition-colors"
                    title="Delete Department"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>

                <h3 className={`text-xl font-bold mt-4 ${!dept.name || dept.name === '[Missing Name]' ? 'text-amber-700 italic' : ''}`}>
                  {dept.name || '[Missing Name]'}
                </h3>
                <p>
                  Code:{' '}
                  <span className={`font-semibold ${!dept.code ? 'text-amber-600 italic font-normal' : ''}`}>
                    {dept.code || '[Missing Code]'}
                  </span>
                </p>
                <p className="text-sm text-gray-500 mt-2">Created: {new Date(dept.created_at).toLocaleDateString()}</p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
