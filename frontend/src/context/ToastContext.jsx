import React, { createContext, useContext, useState, useCallback } from 'react';
import Toast from '../components/Layout/Toast';

const ToastContext = createContext();

export const useToast = () => {
    const context = useContext(ToastContext);
    if (!context) {
        throw new Error('useToast must be used within a ToastProvider');
    }
    return context;
};

export const ToastProvider = ({ children }) => {
    const [toast, setToast] = useState({ message: '', type: '' });

    const showToast = useCallback((message, type = 'info') => {
        setToast({ message, type });
    }, []);

    const hideToast = useCallback(() => {
        setToast({ message: '', type: '' });
    }, []);

    return (
        <ToastContext.Provider value={{ showToast, hideToast }}>
            {children}
            {toast.message && (
                <Toast
                    message={toast.message}
                    type={toast.type}
                    onClose={hideToast}
                />
            )}
        </ToastContext.Provider>
    );
};
