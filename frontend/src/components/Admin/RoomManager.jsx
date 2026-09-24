import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { DoorOpen, Edit, Plus, Trash2, GraduationCap } from 'lucide-react';
import { departmentAPI, roomAPI } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import ConfirmationModal from '../Layout/ConfirmationModal';
import CsvUploader from '../Layout/CsvUploader';

export default function RoomManager() {
  const [rooms, setRooms] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editData, setEditData] = useState(null);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [roomToDelete, setRoomToDelete] = useState(null);
  const [selectedDepartmentId, setSelectedDepartmentId] = useState(null);
  const { register, handleSubmit, reset, setValue } = useForm();
  const { showToast } = useToast();

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [roomRes, deptRes] = await Promise.all([
        roomAPI.getAll().catch(() => ({ data: [] })),
        departmentAPI.getAll().catch(() => ({ data: [] })),
      ]);
      setRooms(roomRes.data || []);
      setDepartments(deptRes.data || []);
    } catch (error) {
      showToast('Failed to load rooms', 'error');
    }
  };

  const getDepartmentName = (deptId) => departments.find(d => d.id === deptId)?.name || 'Shared';

  const handleEdit = (room) => {
    setEditData(room);
    setValue('name', room.name || '');
    setValue('code', room.code || '');
    setValue('capacity', room.capacity || '');
    setValue('room_type', room.room_type || 'lecture');
    setValue('department_id', room.department_id || '');
    setShowForm(true);
    setTimeout(() => {
      document.querySelector('.main-content')?.scrollTo({ top: 0, behavior: 'smooth' });
    }, 50);
  };

  const onSubmit = async (data) => {
    try {
      const payload = {
        ...data,
        capacity: data.capacity === '' ? null : parseInt(data.capacity),
        department_id: data.department_id || null,
        room_type: data.room_type || 'lecture',
      };

      if (editData) {
        await roomAPI.update(editData.id, payload);
        showToast('Room updated!', 'success');
      } else {
        await roomAPI.create(payload);
        showToast('Room created!', 'success');
      }

      reset();
      setEditData(null);
      setShowForm(false);
      loadData();
    } catch (error) {
      showToast(error.response?.data?.detail || 'Failed to save room', 'error');
    }
  };

  const confirmDelete = async () => {
    if (!roomToDelete) return;
    try {
      await roomAPI.delete(roomToDelete);
      showToast('Room deleted!', 'success');
      loadData();
    } catch (error) {
      showToast(error.response?.data?.detail || 'Failed to delete room', 'error');
    }
  };

  return (
    <div>
      <ConfirmationModal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        onConfirm={confirmDelete}
        title="Delete Room"
        message="Are you sure you want to delete this room?"
      />

      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <h1 className="text-3xl font-bold">Rooms</h1>
        <div className="flex gap-2">
          <CsvUploader type="rooms" onSuccess={loadData} />
          <button
            onClick={() => {
              setEditData(null);
              reset({ room_type: 'lecture' });
              setShowForm(!showForm);
            }}
            className="btn btn-primary flex items-center gap-2"
          >
            {showForm ? 'Cancel' : <><Plus size={20} /> Add Room</>}
          </button>
        </div>
      </div>

      {showForm && (
        <div className="card mb-6">
          <h2 className="text-xl font-bold mb-4">{editData ? 'Edit Room' : 'Add New Room'}</h2>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-2">Name *</label>
                <input {...register('name', { required: true })} className="input" placeholder="Room 204" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Code</label>
                <input {...register('code')} className="input" placeholder="R204" />
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium mb-2">Type</label>
                <select {...register('room_type')} className="input" defaultValue="lecture">
                  <option value="lecture">Lecture</option>
                  <option value="lab">Lab</option>
                  <option value="seminar">Seminar</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Capacity</label>
                <input {...register('capacity')} type="number" min="0" className="input" placeholder="60" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Department</label>
                <select {...register('department_id')} className="input">
                  <option value="">Shared</option>
                  {departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => { setShowForm(false); setEditData(null); reset(); }} className="btn btn-secondary">Cancel</button>
              <button type="submit" className="btn btn-primary">{editData ? 'Update' : 'Create'}</button>
            </div>
          </form>
        </div>
      )}

      {/* Department Cards Grid */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold text-gray-700 mb-4 flex items-center gap-2">
          <GraduationCap className="text-blue-500" size={22} />
          Select Department / Sharing Type
        </h2>
        
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {/* Shared Rooms Card */}
          {(() => {
            const sharedRoomsCount = rooms.filter(room => !room.department_id).length;
            return (
              <button
                onClick={() => setSelectedDepartmentId(selectedDepartmentId === 'shared' ? null : 'shared')}
                className={`w-full text-left rounded-xl p-4 transition-all duration-300 border flex flex-col justify-between h-28 hover:-translate-y-1 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500/20 ${
                  selectedDepartmentId === 'shared'
                    ? 'bg-gradient-to-br from-indigo-600 to-purple-600 text-white border-transparent shadow-lg shadow-indigo-500/10'
                    : 'bg-white text-gray-800 border-gray-100 hover:border-indigo-100 hover:bg-indigo-50/10'
                }`}
              >
                <div className="w-full">
                  <span className={`text-xl font-bold tracking-wider ${selectedDepartmentId === 'shared' ? 'text-white' : 'text-gray-900'}`}>
                    SHARED
                  </span>
                  <p className={`text-xs truncate font-normal mt-1 ${selectedDepartmentId === 'shared' ? 'text-indigo-100' : 'text-gray-500'}`}>
                    Common classrooms & labs
                  </p>
                </div>
                <div className={`text-xs font-semibold self-end px-2.5 py-1 rounded-full ${
                  selectedDepartmentId === 'shared' ? 'bg-white/20 text-white' : 'bg-gray-50 text-gray-600'
                }`}>
                  {sharedRoomsCount} {sharedRoomsCount === 1 ? 'Room' : 'Rooms'}
                </div>
              </button>
            );
          })()}

          {/* Department Cards */}
          {departments.map((dept) => {
            const deptRooms = rooms.filter(room => room.department_id === dept.id);
            const roomCount = deptRooms.length;
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
                  {roomCount} {roomCount === 1 ? 'Room' : 'Rooms'}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {selectedDepartmentId === null ? (
        <div className="card text-center py-16 bg-white border border-dashed border-gray-200 rounded-xl shadow-sm">
          <div className="max-w-md mx-auto flex flex-col items-center">
            <div className="w-16 h-16 rounded-full bg-blue-50 flex items-center justify-center text-blue-600 mb-4 animate-pulse">
              <GraduationCap size={32} />
            </div>
            <p className="text-xl font-bold text-gray-800">Select a Category</p>
            <p className="text-gray-500 mt-2 text-sm leading-relaxed">
              Please click on a Shared or Department card above to view and manage its rooms.
            </p>
          </div>
        </div>
      ) : (
        <div>
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-700">
              {selectedDepartmentId === 'shared'
                ? 'Shared / Common Rooms'
                : `Rooms in ${departments.find(d => d.id === selectedDepartmentId)?.name || 'Selected Department'}`}
            </h2>
            <span className="text-sm bg-blue-50 text-blue-700 px-3 py-1 rounded-full font-medium">
              {rooms.filter(room => selectedDepartmentId === 'shared' ? !room.department_id : room.department_id === selectedDepartmentId).length} Found
            </span>
          </div>

          {rooms.filter(room => selectedDepartmentId === 'shared' ? !room.department_id : room.department_id === selectedDepartmentId).length === 0 ? (
            <div className="card text-center py-12 bg-white border border-gray-100 rounded-xl">
              <p className="text-lg font-semibold text-gray-700">No rooms configured.</p>
              <p className="text-gray-500 mt-1 text-sm">Create a new room for this category using the "Add Room" button above.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {rooms
                .filter(room => selectedDepartmentId === 'shared' ? !room.department_id : room.department_id === selectedDepartmentId)
                .map(room => (
                  <div key={room.id} className="card relative group hover:shadow-lg transition-shadow">
                    <div className="absolute top-2 right-2 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={() => handleEdit(room)} className="p-1.5 text-blue-600 hover:bg-blue-50 rounded-full transition-colors" title="Edit Room">
                        <Edit size={18} />
                      </button>
                      <button onClick={() => { setRoomToDelete(room.id); setIsDeleteModalOpen(true); }} className="p-1.5 text-red-600 hover:bg-red-50 rounded-full transition-colors" title="Delete Room">
                        <Trash2 size={18} />
                      </button>
                    </div>
                    <h3 className="text-xl font-bold pr-16">{room.name}</h3>
                    <div className="mt-2 space-y-1 text-sm text-gray-600">
                      <p>Code: <span className="font-medium text-gray-800">{room.code || '-'}</span></p>
                      <p>Type: <span className="font-medium text-gray-800 capitalize">{room.room_type || 'lecture'}</span></p>
                      <p>Capacity: <span className="font-medium text-gray-800">{room.capacity ?? '-'}</span></p>
                      <p>Department: <span className="font-medium text-gray-800">{getDepartmentName(room.department_id)}</span></p>
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
