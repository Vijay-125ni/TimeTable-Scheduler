import React, { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { authAPI } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import ConfirmationModal from '../Layout/ConfirmationModal';
import { Trash2, Plus, Key, UserCheck } from 'lucide-react';

export default function FacultyAccounts() {
  const [accounts, setAccounts] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const { register, handleSubmit, reset } = useForm();
  const { showToast } = useToast();

  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [accountToDelete, setAccountToDelete] = useState(null);

  useEffect(() => { loadAccounts(); }, []);

  const loadAccounts = async () => {
    try {
      const res = await authAPI.getFacultyAccounts();
      setAccounts(res.data);
    } catch (error) {
      showToast('Failed to load accounts', 'error');
    }
  };

  const handleDeleteClick = (id) => {
    setAccountToDelete(id);
    setIsDeleteModalOpen(true);
  };

  const confirmDelete = async () => {
    if (!accountToDelete) return;
    try {
      await authAPI.deleteFacultyAccount(accountToDelete);
      loadAccounts();
      showToast('Faculty login account revoked!', 'success');
    } catch (error) {
      showToast(error.response?.data?.detail || 'Failed to revoke access', 'error');
    } finally {
      setIsDeleteModalOpen(false);
      setAccountToDelete(null);
    }
  };

  const onSubmit = async (data) => {
    try {
      await authAPI.createFaculty(data);
      showToast('Login account generated successfully!', 'success');
      reset();
      setShowForm(false);
      loadAccounts();
    } catch (error) {
      showToast(error.response?.data?.detail || 'Failed to create account', 'error');
    }
  };

  return (
    <div className="space-y-6">
      <ConfirmationModal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        onConfirm={confirmDelete}
        title="Revoke Access"
        message="Are you sure you want to delete this faculty's login credentials? They will no longer be able to log in. Their timetable schedules will remain intact."
      />

      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-slate-50 p-4 rounded-2xl border border-slate-100">
        <div>
           <h2 className="text-xl font-bold text-slate-700 flex items-center gap-2">
               <Key size={20} className="text-primary-500" /> 
               Login Credentials
           </h2>
           <p className="text-sm text-slate-500 mt-1">Provide portal access to your faculty staff so they can view scheduled timetables.</p>
        </div>
        <button
          onClick={() => { reset(); setShowForm(!showForm); }}
          className="btn btn-primary flex items-center gap-2"
        >
          {showForm ? 'Cancel' : <><Plus size={20} /> Generate Login</>}
        </button>
      </div>

      {showForm && (
        <div className="bg-white rounded-2xl shadow-lg border border-slate-100 p-6">
          <h3 className="text-lg font-bold mb-4">Create New Faculty Login</h3>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 max-w-2xl">
            <div className="grid grid-cols-2 gap-4">
               <div>
                  <label className="block text-sm font-bold text-slate-600 mb-2">Username *</label>
                  <input {...register('username', { required: true })} className="input w-full" placeholder="e.g. jdoe_cs" />
               </div>
               <div>
                  <label className="block text-sm font-bold text-slate-600 mb-2">Full Name *</label>
                  <input {...register('full_name', { required: true })} className="input w-full" placeholder="John Doe" />
               </div>
               <div>
                  <label className="block text-sm font-bold text-slate-600 mb-2">Email *</label>
                  <input {...register('email', { required: true })} type="email" className="input w-full" placeholder="john@institution.com" />
               </div>
               <div>
                  <label className="block text-sm font-bold text-slate-600 mb-2">Temporary Password *</label>
                  <input {...register('password', { required: true, minLength: 6 })} type="password" placeholder="Min 6 chars" className="input w-full" />
               </div>
            </div>
            
            <div className="flex justify-end pt-2">
              <button type="submit" className="btn btn-primary px-8">Generate Credentials</button>
            </div>
          </form>
        </div>
      )}

      {accounts.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-2xl border border-dashed border-slate-300">
          <UserCheck size={48} className="mx-auto text-slate-300 mb-4" />
          <p className="text-lg font-bold text-slate-600">No Login Accounts</p>
          <p className="text-slate-500">You haven't generated any login credentials for faculty yet.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {accounts.map(acc => (
            <div key={acc.id} className="bg-white p-5 rounded-2xl shadow-sm border border-slate-100 flex justify-between items-start group">
              <div>
                <h3 className="font-bold text-slate-800 flex items-center gap-2">
                   {acc.full_name}
                   {acc.is_active && <span className="w-2 h-2 rounded-full bg-green-500" title="Active"></span>}
                </h3>
                <p className="text-sm text-slate-500 font-medium">@{acc.username}</p>
                <p className="text-xs text-slate-400 mt-2">{acc.email}</p>
              </div>
              <button
                onClick={() => handleDeleteClick(acc.id)}
                className="p-2 text-red-500 hover:bg-red-50 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                title="Revoke Login Access"
              >
                <Trash2 size={18} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
