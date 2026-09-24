import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { authAPI } from '../../services/api';
import { useToast } from '../../context/ToastContext';

const Settings = () => {
    const { register, handleSubmit, formState: { errors }, reset, watch } = useForm();
    const { showToast } = useToast();
    const [loading, setLoading] = useState(false);

    const newPassword = watch('new_password');

    const onSubmit = async (data) => {
        setLoading(true);
        try {
            await authAPI.changePassword({
                current_password: data.current_password,
                new_password: data.new_password
            });
            showToast('Password updated successfully!', 'success');
            reset();
        } catch (error) {
            showToast(error.response?.data?.detail || 'Failed to update password', 'error');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="max-w-2xl mx-auto">
            <h2 className="text-2xl font-bold text-gray-800 mb-6">Settings</h2>

            <div className="bg-white rounded-lg shadow-md p-6">
                <h3 className="text-lg font-semibold text-gray-700 mb-4">Change Password</h3>

                <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            Current Password
                        </label>
                        <input
                            type="password"
                            {...register('current_password', { required: 'Current password is required' })}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-primary-500"
                        />
                        {errors.current_password && (
                            <p className="text-red-500 text-xs mt-1">{errors.current_password.message}</p>
                        )}
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            New Password
                        </label>
                        <input
                            type="password"
                            {...register('new_password', {
                                required: 'New password is required',
                                minLength: { value: 6, message: 'Password must be at least 6 characters' }
                            })}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-primary-500"
                        />
                        {errors.new_password && (
                            <p className="text-red-500 text-xs mt-1">{errors.new_password.message}</p>
                        )}
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            Confirm New Password
                        </label>
                        <input
                            type="password"
                            {...register('confirm_password', {
                                required: 'Please confirm your password',
                                validate: value => value === newPassword || 'Passwords do not match'
                            })}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-primary-500"
                        />
                        {errors.confirm_password && (
                            <p className="text-red-500 text-xs mt-1">{errors.confirm_password.message}</p>
                        )}
                    </div>

                    <div className="flex justify-end mt-6">
                        <button
                            type="submit"
                            disabled={loading}
                            className={`px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 ${loading ? 'opacity-50 cursor-not-allowed' : ''
                                }`}
                        >
                            {loading ? 'Updating...' : 'Update Password'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

export default Settings;
