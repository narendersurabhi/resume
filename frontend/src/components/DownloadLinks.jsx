import React, { useState } from 'react';
import axios from 'axios';

const DownloadLinks = ({ apiUrl, tenantId, job, onLinksLoaded }) => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchLinks = async () => {
    if (!job?.jobId) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await axios.get(`${apiUrl}download/${job.jobId}`, {
        params: { tenantId },
      });
      onLinksLoaded(job.jobId, response.data);
    } catch (err) {
      console.error('Failed to fetch download URLs', err);
      setError('Download not ready yet.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      {job.docxUrl && (
        <a
          href={job.docxUrl}
          className="rounded bg-emerald-500 px-3 py-1 font-semibold text-slate-900 hover:bg-emerald-400"
        >
          Download DOCX
        </a>
      )}
      {job.pdfUrl && (
        <a
          href={job.pdfUrl}
          className="rounded bg-indigo-500 px-3 py-1 font-semibold text-white hover:bg-indigo-400"
        >
          Download PDF
        </a>
      )}
      {!job.docxUrl && !job.pdfUrl && (
        <button
          type="button"
          onClick={fetchLinks}
          disabled={isLoading}
          className="rounded bg-slate-700 px-3 py-1 font-semibold text-slate-100 hover:bg-slate-600 disabled:cursor-not-allowed disabled:bg-slate-800"
        >
          {isLoading ? 'Checking…' : 'Check for downloads'}
        </button>
      )}
      {error && <span className="text-xs text-rose-400">{error}</span>}
    </div>
  );
};

export default DownloadLinks;
