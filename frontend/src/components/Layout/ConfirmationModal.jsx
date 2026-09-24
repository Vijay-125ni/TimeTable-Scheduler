import React from 'react';
import { createPortal } from 'react-dom';

const ConfirmationModal = ({ isOpen, onClose, onConfirm, title, message }) => {
    if (!isOpen) return null;

    return createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm transition-opacity">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 mx-4 transform transition-all scale-100 border border-slate-100">
                <div className="mb-4">
                    <h3 className="text-xl font-bold text-gray-900">{title}</h3>
                    <p className="text-gray-500 mt-2 text-sm leading-relaxed">{message}</p>
                </div>
                <div className="flex justify-end space-x-3 mt-6">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-gray-300"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={() => {
                            onConfirm();
                            onClose();
                        }}
                        className="px-4 py-2 text-white bg-red-600 hover:bg-red-700 rounded-lg font-medium shadow-md transition-all hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1"
                    >
                        Confirm
                    </button>
                </div>
            </div>
        </div>,
        document.body
    );
};

export default ConfirmationModal;
