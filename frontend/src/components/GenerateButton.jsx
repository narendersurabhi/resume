import React, { useState } from 'react';
import axios from 'axios';

const GenerateButton = ({ apiUrl, tenantId, selections, onGenerated }) => {
  const [isGenerating, setGenerating] = useState(false);
  const [error, setError] = useState(null);

  const handleGenerate = async () => {
    if (!selections.resume || !selections.template) {
      setError('Select both an approved resume and a template.');
      return;
    }

    setGenerating(true);
    setError(null);

    try {
      const response = await axios.post(`${apiUrl}generate`, {
        tenantId,
        resumeKey: selections.resume.key,
        templateKey: selections.template.key,
        jobDescriptionKey: selections.job?.key,
        jobDescription: selections.job?.content,
      });
      if (onGenerated) {
        onGenerated(response.data);
      }
    } catch (err) {
      console.error('Generation failed', err);
      setError('Failed to generate resume. Check console for details.');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="rounded-lg bg-slate-900 p-6 shadow">
      <button
        type="button"
        onClick={handleGenerate}
        disabled={isGenerating}
        className="w-full rounded bg-indigo-500 py-3 font-semibold text-white transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:bg-slate-700"
      >
        {isGenerating ? 'Generating…' : 'Generate Tailored Resume'}
      </button>
      {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
    </div>
  );
};

export default GenerateButton;
