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
  const [isQueueing, setQueueing] = useState(false);
  const [isGeneratingNow, setGeneratingNow] = useState(false);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);
  const [provider, setProvider] = useState('openai');
  const [model, setModel] = useState(DEFAULT_MODEL);
  const [modelOptions, setModelOptions] = useState([DEFAULT_MODEL]);
  const [preview, setPreview] = useState(null);

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

  const buildPayload = () => {
    const hasResumeSelection = Boolean(selections?.resume?.key);
    const hasTemplateSelection = Boolean(selections?.template?.key);
    const hasJobSelection = Boolean(selections?.job?.key);
    const trimmedResumeText = resumeText?.trim() ?? '';
    const trimmedJobDescription = jobDescription?.trim() ?? '';

    const canUseUploadedFiles = hasResumeSelection && hasTemplateSelection;

    if (canUseUploadedFiles && !trimmedJobDescription && !hasJobSelection) {
      setError('Provide a job description or select an uploaded job description before generating.');
      setMessage(null);
      return null;
    }

    if (!canUseUploadedFiles) {
      if (!trimmedResumeText) {
        setError('Paste resume text before generating.');
        setMessage(null);
        return null;
      }
      if (!trimmedJobDescription) {
        setError('Provide a job description before generating.');
        setMessage(null);
        return null;
      }
    }
    const payload = {
      userId: userId || tenantId || 'anonymous',
      provider,
      model,
    };
    if (canUseUploadedFiles) {
      payload.resumeKey = selections?.resume?.key;
      if (hasJobSelection) payload.jobKey = selections.job.key;
    } else {
      payload.resumeText = trimmedResumeText;
    }
    if (trimmedJobDescription) payload.jobDescription = trimmedJobDescription;
    if (selections?.job?.jobId) payload.jobId = selections.job.jobId;

    return payload;
  };

  const handleQueue = async () => {
    setQueueing(true);
    setGeneratingNow(false);
    setPreview(null);
    setError(null);
    setMessage(null);
    try {
      const payload = buildPayload();
      if (!payload) return;
      const response = await apiPost(apiUrl, 'tailor', payload);
      if (onGenerated) onGenerated({ ...response.data, source: 'tailor', provider, model });
      setMessage('Tailor job queued. Refresh jobs to track progress.');
      if (onAfterGenerate) onAfterGenerate();
    } catch (err) {
      console.error('Queueing failed', err);
      const apiMessage = err.response?.data?.error || err.message || 'Unknown error';
      setError(`Failed to queue: ${apiMessage}`);
    } finally {
      setQueueing(false);
    }
  };

  const handleGenerateNow = async () => {
    setGeneratingNow(true);
    setQueueing(false);
    setPreview(null);
    setError(null);
    setMessage(null);
    try {
      const payload = buildPayload();
      if (!payload) return;
      const response = await apiPost(apiUrl, 'tailor/sync', payload);
      const data = response.data || {};
      if (onGenerated) onGenerated({ ...data, source: 'tailor/sync', provider, model });
      if (data.json) setPreview(data.json);
      setMessage('Generated successfully. Preview below.');
      if (onAfterGenerate) onAfterGenerate();
    } catch (err) {
      console.error('Sync generation failed', err);
      const apiMessage = err.response?.data?.error || err.message || 'Unknown error';
      setError(`Failed to generate now: ${apiMessage}`);
    } finally {
      setGeneratingNow(false);
    }
  };

  return (
    <div className="space-y-4 rounded-lg bg-slate-900 p-6 shadow">
      <div className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
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
      <p className="text-xs text-slate-400">
        Choose how to run: Generate Now (sync) returns immediately; Add to Queue (async) runs in the background.
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <button
          type="button"
          onClick={handleGenerateNow}
          disabled={isGeneratingNow}
          className="w-full rounded bg-emerald-500 py-3 font-semibold text-slate-900 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-200"
        >
          {isGeneratingNow ? 'Generating…' : 'Generate Now'}
        </button>
        <button
          type="button"
          onClick={handleQueue}
          disabled={isQueueing}
          className="w-full rounded bg-indigo-500 py-3 font-semibold text-white transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:bg-slate-700"
        >
          {isQueueing ? 'Queueing…' : 'Add to Queue'}
        </button>
      </div>
      {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
      {message && <p className="mt-3 text-sm text-emerald-400">{message}</p>}
      {preview ? (
        <div className="mt-4">
          <p className="text-xs font-semibold text-slate-300">Preview</p>
          <pre className="mt-2 max-h-64 overflow-auto rounded bg-slate-950 p-3 text-xs text-slate-200">{JSON.stringify(preview, null, 2)}</pre>
        </div>
      ) : null}
    </div>
  );
};

export default GenerateButton;
