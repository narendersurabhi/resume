import React, { useEffect, useState } from 'react';
import { apiGet, apiPost } from '../lib/api.js';

const DEFAULT_MODEL = 'gpt-4o-mini';
const PROVIDERS = [
  { label: 'OpenAI', value: 'openai' },
  { label: 'Bedrock', value: 'bedrock' },
];

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
  const [provider, setProvider] = useState('openai');
  const [model, setModel] = useState(DEFAULT_MODEL);
  const [autoRender, setAutoRender] = useState(true);
  const [modelOptions, setModelOptions] = useState([DEFAULT_MODEL]);

  const loadModels = async (prov) => {
    try {
      const res = await apiGet(apiUrl, 'models', { params: { provider: prov } });
      let list = res.data?.models || [];
      if (prov === 'openai' && Array.isArray(list)) {
        const gpt5 = list.filter((m) => typeof m === 'string' && m.toLowerCase().startsWith('gpt-5'));
        if (gpt5.length > 0) list = gpt5;
      }
      if (Array.isArray(list) && list.length > 0) {
        setModelOptions(list);
        if (!list.includes(model)) {
          const lower = list.map((m) => String(m).toLowerCase());
          const idxPro = lower.indexOf('gpt-5-pro');
          setModel(idxPro >= 0 ? list[idxPro] : list[0]);
        }
      } else {
        setModelOptions([model]);
      }
    } catch (e) {
      // leave current options; show no UI error to avoid blocking generate
      setModelOptions([model]);
    }
  };

  useEffect(() => {
    loadModels(provider);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider]);

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
          userId: userId || tenantId || 'anonymous',
          provider,
          model,
          resumeKey: selections.resume.key,
        };
        if (hasJobSelection) payload.jobKey = selections.job.key;
        if (trimmedJobDescription) payload.jobDescription = trimmedJobDescription;

        const response = await apiPost(apiUrl, 'tailor', payload);
        if (onGenerated) onGenerated({ ...response.data, source: 'tailor' });
        setMessage(`Tailor request submitted (job ${response.data?.jobId ?? 'unknown'})`);

        if (autoRender && selections?.template?.key) {
          try {
            await apiPost(apiUrl, 'render', {
              jobId: response.data?.jobId,
              userId: userId || tenantId || 'anonymous',
              jsonS3: response.data?.jsonS3,
              templateKey: selections.template.key,
              format: 'docx',
            });
          } catch (e) {
            console.error('Auto-render failed', e);
          }
        }
        if (onAfterGenerate) onAfterGenerate();
        return;
      }

      const payload = {
        userId: userId || tenantId || 'anonymous',
        resumeText: trimmedResumeText,
        jobDescription: trimmedJobDescription,
        provider,
        model,
      };
      if (selections?.job?.jobId) payload.jobId = selections.job.jobId;

      const response = await apiPost(apiUrl, 'tailor', payload);
      if (onGenerated) onGenerated(response.data);
      if (onAfterGenerate) onAfterGenerate();
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
    <div className="space-y-4 rounded-lg bg-slate-900 p-6 shadow">
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <label className="block text-slate-300">Provider</label>
          <select
            value={provider}
            onChange={(e) => {
              const p = e.target.value;
              setProvider(p);
              const found = PROVIDERS.find((x) => x.value === p);
              if (found && found.models?.length) setModel(found.models[0]);
            }}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-slate-100"
          >
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-slate-300">Model</label>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-slate-100"
          >
            {modelOptions.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>
      </div>
      <label className="flex items-center gap-2 text-xs text-slate-300">
        <input type="checkbox" checked={autoRender} onChange={(e) => setAutoRender(e.target.checked)} />
        Auto-render to DOCX after tailoring
      </label>
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
