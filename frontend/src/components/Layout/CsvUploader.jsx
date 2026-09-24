import React, { useRef, useState } from 'react';
import { useToast } from '../../context/ToastContext';
import { Upload } from 'lucide-react';
import api, { clearApiCache } from '../../services/api';

export default function CsvUploader({ type, onSuccess, className, style }) {
  const inputRef = useRef();
  const { showToast } = useToast();
  const [loading, setLoading] = useState(false);

  const handleFile = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const form = new FormData();
    form.append('type', type);
    form.append('file', file);
    setLoading(true);
    try {
      const res = await api.post('/imports/upload', form);
      const data = res.data || {};
      const issueCount = Number(data.error_count || 0) + Number(data.warning_count || 0);
      const status = data.error_count ? 'warning' : 'success';
      const message = data.message || `Imported ${data.imported || 0} ${data.type || type}`;
      showToast(issueCount ? message : `Imported ${data.imported || 0} ${data.type || type}`, status);
      clearApiCache();
      // Prefer callback (no full-page reload), fall back to reload if none provided
      if (onSuccess) {
        onSuccess();
      } else {
        window.location.reload();
      }
    } catch (err) {
      console.error(err);
      showToast(err.response?.data?.detail || err.message || 'CSV upload failed', 'error');
    } finally {
      setLoading(false);
      // Reset file input so same file can be re-uploaded
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  return (
    <div>
      <input ref={inputRef} type="file" accept=".csv" onChange={handleFile} style={{ display: 'none' }} />
      <button
        onClick={() => inputRef.current && inputRef.current.click()}
        className={className || "btn btn-secondary flex items-center gap-2"}
        style={style}
        title={`Upload ${type} CSV`}
        disabled={loading}
      >
        <Upload size={16} />
        {loading ? 'Uploading...' : 'Upload CSV'}
      </button>
    </div>
  );
}
