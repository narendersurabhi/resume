import React, { useState } from 'react';
import axios from 'axios';

const GenerateButton = ({ apiUrl, tenantId, selections, jobDescriptionText, onJobStarted }) => {
  const [isGenerating, setGenerating] = useState(false);
  const [error, setError] = useState(null);
  const [useComprehend, setUseComprehend] = useState(true);

  const handleGenerate = async () => {
    if (!selections.resume) {
      setError('Select an approved resume before tailoring.');
      return;
    }

    const payload = {
      tenantId,
      resumeKey: selections.resume.key,
      templateKey: selections.template?.key ?? null,
      jobDescriptionKey: selections.job?.key ?? null,
      jobDescription: jobDescriptionText || selections.job?.content || null,
      options: {
        runComprehend: useComprehend,
      },
    };

    if (!payload.jobDescription && !payload.jobDescriptionKey) {
      setError('Provide a job description via text area or upload.');
      return;
    }

    setGenerating(true);
    setError(null);

    try {
      const response = await axios.post(`${apiUrl}tailor`, payload);
      if (onJobStarted) {
        onJobStarted(response.data);
      }
    } catch (err) {
      console.error('Failed to start tailoring workflow', err);
      setError('Failed to start tailoring. Check console for details.');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="rounded-lg bg-slate-900 p-6 shadow space-y-4">
      <div className="flex items-center justify-between text-sm text-slate-300">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={useComprehend}
            onChange={() => setUseComprehend((value) => !value)}
            className="h-4 w-4 rounded border-slate-700 bg-slate-800"
          />
          Enable Comprehend PII check
        </label>
      </div>
      <button
        type="button"
        onClick={handleGenerate}
        disabled={isGenerating}
        className="w-full rounded bg-indigo-500 py-3 font-semibold text-white transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:bg-slate-700"
      >
        {isGenerating ? 'Starting workflow…' : 'Tailor Resume'}
      </button>
      {error && <p className="text-sm text-rose-400">{error}</p>}
    </div>
  );
};

export default GenerateButton;
