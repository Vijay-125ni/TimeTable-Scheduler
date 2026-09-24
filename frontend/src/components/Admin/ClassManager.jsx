import React, { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { classAPI, departmentAPI, batchAPI, roomAPI } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import { useFormCache } from '../../hooks/useFormCache';
import ConfirmationModal from '../Layout/ConfirmationModal';
import CsvUploader from '../Layout/CsvUploader';
import { Edit, Trash2, Plus, GraduationCap } from 'lucide-react';

export default function ClassManager() {
  const [classes, setClasses] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [batches, setBatches] = useState([]);
  const [rooms, setRooms] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editData, setEditData] = useState(null);
  const { register, handleSubmit, reset, setValue, watch } = useForm();
  const { showToast } = useToast();
  const [selectedDepartmentId, setSelectedDepartmentId] = useState(null);

  // Modal State
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [classToDelete, setClassToDelete] = useState(null);

  // Watch all form fields for caching
  const formValues = watch();
  
  // Use form cache hook
  const { clearCache } = useFormCache('classFormCache', formValues, setValue, showForm, !!editData);

  useEffect(() => { 
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const classRes = await classAPI.getAll().catch(err => { console.error('Classes fail', err); return { data: [] }; });
      setClasses(classRes.data);

      const deptRes = await departmentAPI.getAll().catch(err => { console.error('Depts fail', err); return { data: [] }; });
      setDepartments(deptRes.data);

      const batchRes = await batchAPI.getAll().catch(err => { console.error('Batch fail', err); return { data: [] }; });
      setBatches(batchRes.data);

      const roomRes = await roomAPI.getAll().catch(err => { console.error('Rooms fail', err); return { data: [] }; });
      setRooms(roomRes.data);
    } catch (error) {
      console.error('Failed to load data', error);
      showToast('Failed to load data', 'error');
    }
  };

  const handleEdit = (cls) => {
    setEditData(cls);
    setValue('name', cls.name);
    setValue('section', cls.section);
    setValue('department_id', cls.department_id);
    setValue('batch_id', cls.batch_id);
    setValue('room_id', cls.room_id);
    setValue('semester', cls.semester);
    setValue('student_count', cls.student_count);
    setShowForm(true);
    setTimeout(() => {
        document.querySelector('.main-content')?.scrollTo({ top: 0, behavior: 'smooth' });
    }, 50);
  };

  const onSubmit = async (data) => {
    try {
      const payload = {
        ...data,
        department_id: data.department_id || null,
        semester: parseInt(data.semester),
        student_count: parseInt(data.student_count),
        batch_id: data.batch_id || null,
        room_id: data.room_id || null
      };

      if (editData) {
        await classAPI.update(editData.id, payload);
        showToast('Class updated!', 'success');
      } else {
        await classAPI.create(payload);
        showToast('Class created!', 'success');
      }

      reset();
      setEditData(null);
      setShowForm(false);
      clearCache();
      loadData();
    } catch (error) {
      showToast(error.response?.data?.detail || 'Failed to save class', 'error');
    }
  };

  const confirmDelete = async () => {
    if (!classToDelete) return;
    try {
      await classAPI.delete(classToDelete);
      loadData();
      showToast('Class deleted!', 'success');
    } catch (error) {
      showToast(error.response?.data?.detail || 'Failed to delete class', 'error');
    }
  };

  const handleDeleteClick = (id) => {
    setClassToDelete(id);
    setIsDeleteModalOpen(true);
  };

  const getBatchName = (batchId) => {
    const b = batches.find(b => b.id === batchId);
    return b ? b.name : '-';
  };

  const getRoomName = (roomId) => {
    const room = rooms.find(r => r.id === roomId);
    return room ? `${room.name}${room.code ? ` (${room.code})` : ''}` : '-';
  };

  return (
    <div>
      <ConfirmationModal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        onConfirm={confirmDelete}
        title="Delete Class"
        message="Are you sure you want to delete this class? This action cannot be undone."
      />

      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <h1 className="text-3xl font-bold">Classes</h1>
        <div className="flex gap-2">
          <CsvUploader type="classes" onSuccess={loadData} />
          <button
            onClick={() => {
              setEditData(null);
              setShowForm(!showForm);
            }}
            className="btn btn-primary flex items-center gap-2"
          >
            {showForm ? 'Cancel' : <><Plus size={20} /> Add Class</>}
          </button>
        </div>
      </div>

      {showForm && (
        <div className="card mb-6">
          <h2 className="text-xl font-bold mb-4">{editData ? 'Edit Class' : 'Add New Class'}</h2>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div><label className="block text-sm font-medium mb-2">Name *</label><input {...register('name', { required: true })} className="input" placeholder="B.Tech 2nd Year" /></div>
            <div><label className="block text-sm font-medium mb-2">Section</label><input {...register('section')} className="input" placeholder="A" /></div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-2">Department *</label>
                <select {...register('department_id', { required: true })} className="input">
                  <option value="">Select</option>
                  {departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Batch Config</label>
                <select {...register('batch_id')} className="input">
                  <option value="">Default (Global Settings)</option>
                  {batches.map(b => <option key={b.id} value={b.id}>{b.name} ({b.start_time}-{b.end_time})</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Default Room</label>
              <select {...register('room_id')} className="input">
                <option value="">No fixed room</option>
                {rooms.map(room => (
                  <option key={room.id} value={room.id}>
                    {room.name}{room.code ? ` (${room.code})` : ''} - {room.room_type || 'lecture'}{room.capacity ? `, ${room.capacity} seats` : ''}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div><label className="block text-sm font-medium mb-2">Semester</label><input {...register('semester')} type="number" className="input" /></div>
              <div><label className="block text-sm font-medium mb-2">Students</label><input {...register('student_count')} type="number" className="input" /></div>
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
              const deptClasses = classes.filter(cls => cls.department_id === dept.id);
              const classCount = deptClasses.length;
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
                    {classCount} {classCount === 1 ? 'Class' : 'Classes'}
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
              Please click on one of the department cards above to view and manage its classes.
            </p>
          </div>
        </div>
      ) : (
        <div>
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-700">
              Classes in {departments.find(d => d.id === selectedDepartmentId)?.name || 'Selected Department'}
            </h2>
            <span className="text-sm bg-blue-50 text-blue-700 px-3 py-1 rounded-full font-medium">
              {classes.filter(cls => cls.department_id === selectedDepartmentId).length} Found
            </span>
          </div>

          {classes.filter(cls => cls.department_id === selectedDepartmentId).length === 0 ? (
            <div className="card text-center py-12 bg-white border border-gray-100 rounded-xl">
              <p className="text-lg font-semibold text-gray-700">No classes configured.</p>
              <p className="text-gray-500 mt-1 text-sm">Create a new class for this department using the "Add Class" button above.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {classes
                .filter(cls => cls.department_id === selectedDepartmentId)
                .map(cls => (
                  <div key={cls.id} className="card relative group hover:shadow-lg transition-shadow">
                    <div className="absolute top-2 right-2 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => handleEdit(cls)}
                        className="p-1.5 text-blue-600 hover:bg-blue-50 rounded-full transition-colors"
                        title="Edit Class"
                      >
                        <Edit size={18} />
                      </button>
                      <button
                        onClick={() => handleDeleteClick(cls.id)}
                        className="p-1.5 text-red-600 hover:bg-red-50 rounded-full transition-colors"
                        title="Delete Class"
                      >
                        <Trash2 size={18} />
                      </button>
                    </div>

                    <h3 className="text-xl font-bold pr-16">{cls.name} {cls.section}</h3>
                    <div className="mt-2 space-y-1 text-sm text-gray-600">
                      <p>Semester: <span className="font-medium text-gray-800">{cls.semester}</span></p>
                      <p>Students: <span className="font-medium text-gray-800">{cls.student_count}</span></p>
                      <p>Batch: <span className="font-medium text-gray-800">{getBatchName(cls.batch_id)}</span></p>
                      <p>Room: <span className="font-medium text-gray-800">{getRoomName(cls.room_id)}</span></p>
                    </div>
                  </div>
                ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
