import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import UploadForm from '../components/UploadForm.jsx';
import ResumeList from '../components/ResumeList.jsx';
import GenerateButton from '../components/GenerateButton.jsx';
import { apiGet, apiPost } from '../lib/api.js';

const PRIVILEGED_GROUPS = ['Admin', 'Manager'];

const Dashboard = ({ apiUrl, userId, userGroups }) => {
  const [tenantId] = useState('demo-tenant');
  const [uploads, setUploads] = useState({ approved: [], template: [], jobs: [] });
  const [selections, setSelections] = useState({ resume: null, template: null, job: null });
  const [resumeText, setResumeText] = useState('');
  const [jobDescription, setJobDescription] = useState('');
  const [generatedOutputs, setGeneratedOutputs] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobsError, setJobsError] = useState(null);
  const [selectedJob, setSelectedJob] = useState(null);
  const [renderingJobId, setRenderingJobId] = useState(null);
  const [detailsTemplate, setDetailsTemplate] = useState(null);
  
  // Retry UI state
  const [retryProvider, setRetryProvider] = useState('openai');
  const [retryModel, setRetryModel] = useState('gpt-5-mini');
  const [retryModels, setRetryModels] = useState(['gpt-5-mini']);
  const [retryBusy, setRetryBusy] = useState(false);
  const [retryMsg, setRetryMsg] = useState(null);
  const [retryErr, setRetryErr] = useState(null);
  const [pingBusy, setPingBusy] = useState(false);
  const [pingStatus, setPingStatus] = useState(null);

  const fileInputRef = useRef();
  const templateFileInputRef = useRef();

  const handleUploadComplete = (item) => {
    setUploads((prev) => ({
      ...prev,
      [item.category]: [...(prev[item.category] ?? []), item],
    }));
  };

  const handleGenerated = (result) => {
    const id = result.jobId || result.outputId || `job-${Date.now()}`;
    setGeneratedOutputs((prev) => [
      {
        ...result,
        outputId: id,
        status: result.status || 'processing',
        createdAt: new Date().toISOString(),
        docxUrl: null,
        pdfUrl: null,
        linksLoading: false,
        linksError: null,
      },
      ...prev,
    ]);
  };

  const isPrivileged = useMemo(
    () => (userGroups ?? []).some((g) => PRIVILEGED_GROUPS.includes(g)),
    [userGroups],
  );

  const loadJobs = useCallback(async () => {
    if (!userId) {
      return;
    }
    setJobsLoading(true);
    setJobsError(null);
    try {
      const params = {};
      if (!isPrivileged) {
        params.userId = userId;
      }
      const response = await apiGet(apiUrl, 'jobs', { params });
      const items = response.data?.items ?? response.data?.jobs ?? [];
      setJobs(items);
    } catch (error) {
      console.error('Failed to load jobs', error);
      const msg = error.response?.data?.error || error.message || 'Unknown error';
      setJobsError(`Failed to load jobs: ${msg}`);
    } finally {
      setJobsLoading(false);
    }
  }, [apiUrl, userId, isPrivileged]);

  useEffect(() => {
    if (userId) {
      loadJobs();
    }
  }, [userId, loadJobs]);

  const fetchLinks = async (out) => {
    setGeneratedOutputs((prev) =>
      prev.map((x) =>
        x.outputId === out.outputId
          ? { ...x, linksLoading: true, linksError: null }
          : x,
      ),
    );

    try {
      const requests = [];
      const index = {};

      if (out.docxKey) {
        index.docx = requests.length;
        requests.push(apiGet(apiUrl, 'download', { params: { key: out.docxKey } }));
      }
      if (out.pdfKey) {
        index.pdf = requests.length;
        requests.push(apiGet(apiUrl, 'download', { params: { key: out.pdfKey } }));
      }

      const results = await Promise.allSettled(requests);
      const docxRes = index.docx !== undefined ? results[index.docx] : null;
      const pdfRes = index.pdf !== undefined ? results[index.pdf] : null;

      const docxUrl = docxRes?.status === 'fulfilled' ? docxRes.value?.data?.url : null;
      const pdfUrl = pdfRes?.status === 'fulfilled' ? pdfRes.value?.data?.url : null;

      setGeneratedOutputs((prev) =>
        prev.map((x) =>
          x.outputId === out.outputId
            ? {
                ...x,
                linksLoading: false,
                linksError:
                  (!docxUrl && out.docxKey) || (!pdfUrl && out.pdfKey)
                    ? 'Failed to fetch some links'
                    : null,
                docxUrl,
                pdfUrl,
              }
            : x,
        ),
      );
    } catch (error) {
      const msg = error.response?.data?.error || error.message || 'Unknown error';
      setGeneratedOutputs((prev) =>
        prev.map((x) =>
          x.outputId === out.outputId
            ? {
                ...x,
                linksLoading: false,
                linksError: `Failed to fetch download links: ${msg}`,
              }
            : x,
        ),
      );
    }
  };

  const toBase64 = (file) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => {
        const result = reader.result || '';
        const [, encoded = ''] = String(result).split(',');
        resolve(encoded);
      };
      reader.onerror = (err) => reject(err);
    });

  const handleTemplateFileChange = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const content = await toBase64(file);
      const response = await apiPost(apiUrl, 'upload', {
        tenantId,
        category: 'template',
        fileName: file.name,
        fileType: file.type,
        content,
      });
      handleUploadComplete({
        ...response.data,
        fileName: file.name,
        key: response.data?.key || file.name,
        category: 'template',
      });
    } catch (error) {
      const msg = error.response?.data?.error || error.message || 'Unknown error';
      alert(`Failed to upload template: ${msg}`);
    }
    event.target.value = '';
  };

  const handleResumeFileChange = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const content = await toBase64(file);
      const response = await apiPost(apiUrl, 'upload', {
        tenantId,
        category: 'approved',
        fileName: file.name,
        fileType: file.type,
        content,
      });
      handleUploadComplete({
        ...response.data,
        fileName: file.name,
        category: 'approved',
      });
    } catch (error) {
      const msg = error.response?.data?.error || error.message || 'Unknown error';
      alert(`Failed to upload resume: ${msg}`);
    }
    event.target.value = '';
  };

  const handleRender = async (job, templateOverrideKey = null) => {
    if (!job?.outputs?.json) {
      alert('Tailored JSON not available for this job yet.');
      return;
    }
    setRenderingJobId(job.jobId);
    try {
      const payload = {
        jobId: job.jobId,
        userId,
        jsonS3: job.outputs.json,
        format: 'docx',
      };
      const effectiveTemplateKey = templateOverrideKey
        || (detailsTemplate && selectedJob && selectedJob.jobId === job.jobId && detailsTemplate.key)
        || (selections?.template?.key);
      if (effectiveTemplateKey) payload.templateKey = effectiveTemplateKey;
      else payload.templateId = 'default';
      await apiPost(apiUrl, 'render', payload);
      await loadJobs();
    } catch (error) {
      const msg = error.response?.data?.error || error.message || 'Unknown error';
      alert(`Failed to render document: ${msg}`);
    } finally {
      setRenderingJobId(null);
    }
  };

  // Reset details template when switching selected job
  useEffect(() => {
    setDetailsTemplate(null);
  }, [selectedJob?.jobId]);

  const handleDownload = async (key) => {
    if (!key) return;
    try {
      const response = await apiGet(apiUrl, 'download', { params: { key } });
      const url = response.data?.url;
      if (url) {
        window.open(url, '_blank', 'noopener');
      } else {
        alert('Download URL unavailable.');
      }
    } catch (error) {
      const msg = error.response?.data?.error || error.message || 'Unknown error';
      alert(`Failed to prepare download: ${msg}`);
    }
  };

  const preparedSelections = useMemo(
    () => ({
      ...selections,
      job: jobDescription ? { content: jobDescription } : selections.job,
    }),
    [selections, jobDescription],
  );

  const selectedJobDocxKey = selectedJob?.outputs?.render?.docx?.key;
  const selectedJobPdfKey = selectedJob?.outputs?.render?.pdf?.key;
  const shareToken = selectedJob?.shareToken;
  const shareUrl = shareToken && typeof window !== 'undefined'
    ? `${window.location.origin}/?share=${shareToken}`
    : null;

  const canRetry = useMemo(() => Boolean(selectedJob?.inputs?.resume && selectedJob?.inputs?.jobDesc), [selectedJob?.inputs?.resume, selectedJob?.inputs?.jobDesc]);

  const handleTestOpenAI = async () => {
    setPingBusy(true);
    setPingStatus(null);
    try {
      const response = await apiGet(apiUrl, 'tailor/test', {
        params: {
          tenantId,
          provider: retryProvider,
          model: retryModel,
        },
      });
      const data = response.data || {};
      if (data.ok) {
        setPingStatus(`Success: ${data.provider}/${data.model} in ${data.latencyMs ?? '?'} ms${data.schemaUsed ? ' (custom schema)' : ''}`);
      } else {
        setPingStatus(`Failed: ${data.error || 'Unknown error'}`);
      }
    } catch (error) {
      const msg = error.response?.data?.error || error.message || 'Unknown error';
      setPingStatus(`Failed: ${msg}`);
    } finally {
      setPingBusy(false);
    }
  };

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-8 p-6">
      <section className="rounded-lg border border-slate-800 bg-slate-900 p-6 shadow">
        <h2 className="text-lg font-semibold text-white">Authenticated User</h2>
        <div className="mt-2 grid gap-2 text-sm text-slate-300 md:grid-cols-2">
          <p><span className="font-medium text-slate-100">User ID:</span> {userId || 'unknown'}</p>
          <p>
            <span className="font-medium text-slate-100">Groups:</span>{' '}
            {userGroups?.length ? userGroups.join(', ') : 'None'}
          </p>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-6 shadow">
          <label htmlFor="resume-text" className="block text-sm font-medium text-slate-300">
            Resume Text
          </label>
          <textarea
            id="resume-text"
            value={resumeText}
            onChange={(event) => setResumeText(event.target.value)}
            className="mt-2 h-56 w-full rounded border border-slate-700 bg-slate-800 p-3 text-sm text-slate-100"
            placeholder="Paste the resume content here"
          />
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-6 shadow">
          <label htmlFor="job-description" className="block text-sm font-medium text-slate-300">
            Job Description
          </label>
          <textarea
            id="job-description"
            value={jobDescription}
            onChange={(event) => setJobDescription(event.target.value)}
            className="mt-2 h-56 w-full rounded border border-slate-700 bg-slate-800 p-3 text-sm text-slate-100"
            placeholder="Paste the job description here"
          />
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-3">
        <UploadForm apiUrl={apiUrl} tenantId={tenantId} userId={userId} onUploadComplete={handleUploadComplete} />
        <div className="space-y-4">
          <ResumeList
            title="Approved Resumes"
            items={uploads.approved}
            selected={selections.resume}
            onSelect={(item) => setSelections((prev) => ({ ...prev, resume: item }))}
            actionButton={
              <>
                <input
                  type="file"
                  accept=".docx,.txt,.md,.pdf"
                  ref={fileInputRef}
                  style={{ display: 'none' }}
                  onChange={handleResumeFileChange}
                />
                <button
                  className="ml-auto mb-2 flex h-8 w-8 items-center justify-center rounded bg-emerald-600 text-white text-xl font-bold hover:bg-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-400"
                  title="Upload Resume"
                  onClick={() => fileInputRef.current?.click()}
                >
                  +
                </button>
              </>
            }
          />
          <ResumeList
            title="Templates"
            items={uploads.template}
            selected={selections.template}
            onSelect={(item) => setSelections((prev) => ({ ...prev, template: item }))}
            actionButton={
              <>
                <input
                  type="file"
                  accept=".docx"
                  ref={templateFileInputRef}
                  style={{ display: 'none' }}
                  onChange={handleTemplateFileChange}
                />
                <button
                  className="ml-auto mb-2 flex h-8 w-8 items-center justify-center rounded bg-emerald-600 text-white text-xl font-bold hover:bg-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-400"
                  title="Upload Template"
                  onClick={() => templateFileInputRef.current?.click()}
                >
                  +
                </button>
              </>
            }
          />
        </div>
        <div className="space-y-4">
          <GenerateButton
            apiUrl={apiUrl}
            tenantId={tenantId}
            selections={preparedSelections}
            resumeText={resumeText}
            jobDescription={jobDescription}
            userId={userId}
            onGenerated={handleGenerated}
            onAfterGenerate={loadJobs}
          />
          <div className="rounded-lg border border-slate-800 bg-slate-900 p-6 text-sm text-slate-100 shadow">
            <h3 className="text-base font-semibold text-white">Test Model Connection</h3>
            <div className="mt-2">
              <label className="block text-xs font-medium text-slate-300">
                Test Prompt
              </label>
              <textarea
                className="mt-1 w-full rounded border border-slate-700 bg-slate-800 p-2 text-xs text-slate-100"
                rows={3}
                value={pingPrompt}
                onChange={(event) => setPingPrompt(event.target.value)}
              />
            </div>
            <button
              type="button"
              onClick={handleTestOpenAI}
              disabled={pingBusy}
              className="mt-3 w-full rounded bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:bg-slate-700 disabled:opacity-60"
            >
              {pingBusy ? 'Testing…' : 'Test OpenAI'}
            </button>
            {pingResult && (
              <pre className="mt-2 max-h-48 overflow-auto rounded border border-slate-800 bg-slate-950/80 p-3 text-[11px] text-slate-300">
{JSON.stringify(pingResult, null, 2)}
              </pre>
            )}
            {pingStatus && <p className="mt-2 text-xs text-slate-300">{pingStatus}</p>}
          </div>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold text-white">Generated Outputs</h2>
        {generatedOutputs.length === 0 ? (
          <p className="text-sm text-slate-400">No tailored resumes generated yet.</p>
        ) : (
          <ul className="space-y-3">
            {generatedOutputs.map((output) => (
              <li
                key={output.outputId ?? output.jobId}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-900 p-4 text-sm text-slate-100"
              >
                <div>
                  <p className="font-semibold">Output {output.outputId ?? output.jobId}</p>
                  <p className="text-xs text-slate-400">Generated {output.createdAt}</p>
                  {output.status && (
                    <p className="text-xs text-slate-500">Status: {output.status}</p>
                  )}
                  {output.linksError && (
                    <p className="mt-1 text-xs text-rose-400">{output.linksError}</p>
                  )}
                </div>
                <div className="flex gap-2">
                  {output.docxUrl ? (
                    <a
                      href={output.docxUrl}
                      download={`resume_${output.outputId ?? output.jobId}.docx`}
                      className="rounded bg-emerald-500 px-3 py-2 text-xs font-semibold text-slate-900 hover:bg-emerald-400"
                    >
                      Download DOCX
                    </a>
                  ) : null}
                  {output.pdfUrl ? (
                    <a
                      href={output.pdfUrl}
                      className="rounded bg-indigo-500 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-400"
                    >
                      Download PDF
                    </a>
                  ) : null}
                  {!output.docxUrl && !output.pdfUrl && (
                    <button
                      onClick={() => fetchLinks(output)}
                      disabled={output.linksLoading}
                      className="rounded bg-slate-700 px-3 py-2 text-xs font-semibold hover:bg-slate-600 disabled:opacity-60"
                    >
                      {output.linksLoading ? 'Fetching links…' : 'Get download links'}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-semibold text-white">Jobs</h2>
          <button
            type="button"
            onClick={loadJobs}
            disabled={jobsLoading}
            className="rounded bg-slate-800 px-3 py-2 text-sm font-semibold text-slate-200 transition hover:bg-slate-700 disabled:opacity-60"
          >
            {jobsLoading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
        {jobsError && (
          <div className="rounded border border-rose-600 bg-rose-950/60 p-3 text-sm text-rose-100">
            {jobsError}
          </div>
        )}
        {jobsLoading ? (
          <p className="text-sm text-slate-400">Loading jobs…</p>
        ) : jobs.length === 0 ? (
          <p className="text-sm text-slate-400">No jobs available yet.</p>
        ) : (
          <ul className="space-y-3">
            {jobs.map((job) => {
              const docxKey = job.outputs?.render?.docx?.key;
              return (
                <li
                  key={job.jobId}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-900 p-4 text-sm text-slate-100"
                >
                  <div>
                    <p className="font-semibold">Job {job.jobId}</p>
                    <p className="text-xs text-slate-400">User: {job.userId}</p>
                    <p className="text-xs text-slate-400">Status: {job.status}</p>
                    <p className="text-xs text-slate-400">Provider: {job.provider} | Model: {job.model}</p>
                    {job.shareToken && (
                      <p className="text-xs text-slate-500">Share token: {job.shareToken}</p>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setSelectedJob(job)}
                      className="rounded bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700"
                    >
                      Details
                    </button>
                    <button
                      type="button"
                      onClick={() => handleRender(job)}
                      disabled={renderingJobId === job.jobId}
                      className="rounded bg-indigo-500 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-400 disabled:opacity-60"
                    >
                      {renderingJobId === job.jobId ? 'Rendering…' : 'Render DOCX'}
                    </button>
                    {docxKey ? (
                      <button
                        type="button"
                        onClick={() => handleDownload(docxKey)}
                        className="rounded bg-emerald-500 px-3 py-2 text-xs font-semibold text-slate-900 hover:bg-emerald-400"
                      >
                        Download DOCX
                      </button>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {selectedJob && (
          <div className="rounded-lg border border-slate-800 bg-slate-900 p-6 text-sm text-slate-100">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Job details: {selectedJob.jobId}</h3>
              <button
                type="button"
                onClick={() => setSelectedJob(null)}
                className="rounded bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700"
              >
                Close
              </button>
            </div>
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              <p>User ID: {selectedJob.userId}</p>
              <p>Status: {selectedJob.status}</p>
              <p>Provider: {selectedJob.provider}</p>
              <p>Model: {selectedJob.model}</p>
            </div>
            <div className="mt-4">
              <p className="text-xs font-semibold text-slate-300">Render Template</p>
              <div className="mt-2 flex items-center gap-2">
                <select
                  className="flex-1 rounded border border-slate-700 bg-slate-800 p-2 text-xs text-slate-100"
                  value={detailsTemplate?.key || ''}
                  onChange={(e) => {
                    const key = e.target.value;
                    const found = (uploads.template || []).find((t) => t.key === key) || null;
                    setDetailsTemplate(found);
                  }}
                >
                  <option value="">Default template</option>
                  {(uploads.template || []).map((t) => (
                    <option key={t.key} value={t.key}>{t.fileName}</option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => handleRender(selectedJob, detailsTemplate?.key || null)}
                  disabled={renderingJobId === selectedJob.jobId}
                  className="rounded bg-indigo-500 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-400 disabled:opacity-60"
                >
                  {renderingJobId === selectedJob.jobId ? 'Rendering…' : 'Render DOCX'}
                </button>
              </div>
            </div>
            {shareUrl && (
              <div className="mt-3">
                <p className="text-xs text-slate-400">Share URL:</p>
                <div className="mt-1 flex items-center gap-2">
                  <code className="flex-1 truncate rounded bg-slate-800 px-2 py-1 text-xs">{shareUrl}</code>
                  <button
                    type="button"
                    onClick={() => navigator.clipboard?.writeText(shareUrl)}
                    className="rounded bg-slate-800 px-2 py-1 text-xs font-semibold text-slate-200 hover:bg-slate-700"
                  >
                    Copy
                  </button>
                </div>
              </div>
            )}
            <div className="mt-4">
              <p className="text-xs font-semibold text-slate-300">Outputs</p>
              <pre className="mt-2 max-h-64 overflow-auto rounded bg-slate-950 p-3 text-xs text-slate-200">
{JSON.stringify(selectedJob.outputs ?? {}, null, 2)}
              </pre>
              <div className="mt-3 flex gap-2">
                {selectedJobDocxKey && (
                  <button
                    type="button"
                    onClick={() => handleDownload(selectedJobDocxKey)}
                    className="rounded bg-emerald-500 px-3 py-2 text-xs font-semibold text-slate-900 hover:bg-emerald-400"
                  >
                    Download DOCX
                  </button>
                )}
                {selectedJobPdfKey && (
                  <button
                    type="button"
                    onClick={() => handleDownload(selectedJobPdfKey)}
                    className="rounded bg-indigo-500 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-400"
                  >
                    Download PDF
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </section>
    </main>
  );
};

export default Dashboard;








