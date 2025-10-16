import React, { useState } from 'react';
import { apiPost } from '../lib/api.js';

const DEFAULT_MODEL = 'gpt-4o-mini';

const GenerateButton = ({
  apiUrl,
  tenantId,
  selections,
  resumeText,
  jobDescription,
  userId,
  onGenerated,
  onAfterGenerate,
}) => {
  const [isGenerating, setGenerating] = useState(false);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);

  const handleGenerate = async () => {
    const hasResumeSelection = Boolean(selections?.resume?.key);
    const hasTemplateSelection = Boolean(selections?.template?.key);
    const hasJobSelection = Boolean(selections?.job?.key);
    const trimmedResumeText = resumeText?.trim() ?? '';
    const trimmedJobDescription = jobDescription?.trim() ?? '';

    const canUseUploadedFiles = hasResumeSelection && hasTemplateSelection;

    if (canUseUploadedFiles && !trimmedJobDescription && !hasJobSelection) {
      setError('Provide a job description or select an uploaded job description before generating.');
      setMessage(null);
      return;
    }

    if (!canUseUploadedFiles) {
      if (!trimmedResumeText) {
        setError('Paste resume text before generating.');
        setMessage(null);
        return;
      }
      if (!trimmedJobDescription) {
        setError('Provide a job description before generating.');
        setMessage(null);
        return;
      }
    }

    setGenerating(true);
    setError(null);
    setMessage(null);

    try {
      if (canUseUploadedFiles) {
        const payload = {
          tenantId,
          resumeKey: selections.resume.key,
          templateKey: selections.template.key,
        };

        if (hasJobSelection) {
          payload.jobKey = selections.job.key;
        }
        if (trimmedJobDescription) {
          payload.jobDescription = trimmedJobDescription;
        }

        const response = await apiPost(apiUrl, 'generate', payload);
        if (onGenerated) {
          onGenerated({
            ...response.data,
            source: 'generate',
          });
        }
        if (onAfterGenerate) {
          onAfterGenerate();
        }
        setMessage(`Document generation started (output ${response.data?.outputId ?? 'pending'}).`);
        return;
      }

      const payload = {
        userId: userId || tenantId || 'anonymous',
        resumeText: trimmedResumeText,
        jobDescription: trimmedJobDescription,
        provider: selections?.provider || 'openai',
        model: selections?.model || DEFAULT_MODEL,
      };

      if (selections?.job?.jobId) {
        payload.jobId = selections.job.jobId;
      }

      const response = await apiPost(apiUrl, 'tailor', payload);
      if (onGenerated) {
        onGenerated(response.data);
      }
      if (onAfterGenerate) {
        onAfterGenerate();
      }
      setMessage(`Tailor request submitted (job ${response.data?.jobId ?? 'unknown'})`);
    } catch (err) {
      console.error('Generation failed', err);
      const apiMessage = err.response?.data?.error || err.message || 'Unknown error';
      setError(`Failed to generate resume: ${apiMessage}`);
      setMessage(null);
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
      {message && <p className="mt-3 text-sm text-emerald-400">{message}</p>}
    </div>
  );
};

export default GenerateButton;
