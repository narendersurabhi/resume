import React, { useState } from 'react';
import axios from 'axios';

const categories = [
  { label: 'Approved Resume', value: 'approved' },
  { label: 'Style Template', value: 'template' },
  { label: 'Job Description', value: 'jobs' },
];

const UploadForm = ({ apiUrl, tenantId, onUploadComplete }) => {
  const [selectedCategory, setSelectedCategory] = useState(categories[0].value);
  const [file, setFile] = useState(null);
  const [isUploading, setUploading] = useState(false);
  const [message, setMessage] = useState(null);

  const toBase64 = (inputFile) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(inputFile);
      reader.onload = () => {
        const result = reader.result;
        resolve(result.split(',')[1]);
      };
      reader.onerror = (error) => reject(error);
    });

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!file) return;
    setUploading(true);
    setMessage(null);

    try {
      const content = await toBase64(file);
      const response = await axios.post(`${apiUrl}upload`, {
        tenantId,
        category: selectedCategory,
        fileName: file.name,
        content,
      });
      setMessage('Upload successful');
      setFile(null);
      if (onUploadComplete) {
        onUploadComplete({
          key: response.data.key,
          category: selectedCategory,
          fileName: file.name,
        });
      }
    } catch (error) {
      console.error('Upload failed', error);
      setMessage('Upload failed. Check console for details.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 rounded-lg bg-slate-900 p-6 shadow">
      <div>
        <label htmlFor="category" className="block text-sm font-medium text-slate-300">
          File Category
        </label>
        <select
          id="category"
          className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-slate-100"
          value={selectedCategory}
          onChange={(event) => setSelectedCategory(event.target.value)}
        >
          {categories.map((category) => (
            <option key={category.value} value={category.value}>
              {category.label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-300">File</label>
        <input
          type="file"
          className="mt-1 w-full rounded border border-dashed border-slate-600 bg-slate-800 p-3"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </div>

      <button
        type="submit"
        disabled={!file || isUploading}
        className="w-full rounded bg-emerald-500 py-2 font-semibold text-slate-900 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-slate-700"
      >
        {isUploading ? 'Uploading…' : 'Upload'}
      </button>

      {message && <p className="text-sm text-slate-400">{message}</p>}
    </form>
  );
};

export default UploadForm;
