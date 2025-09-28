import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import UploadForm from '../components/UploadForm.jsx';
import ResumeList from '../components/ResumeList.jsx';
import GenerateButton from '../components/GenerateButton.jsx';
import DownloadLinks from '../components/DownloadLinks.jsx';

const Dashboard = ({ apiUrl }) => {
  const [tenantId] = useState('demo-tenant');
  const [uploads, setUploads] = useState({ approved: [], template: [], jobs: [] });
  const [selections, setSelections] = useState({ resume: null, template: null, job: null });
  const [jobDescriptionText, setJobDescriptionText] = useState('');
  const [jobs, setJobs] = useState([]);

  const handleUploadComplete = (item) => {
    setUploads((prev) => ({
      ...prev,
      [item.category]: [item, ...(prev[item.category] ?? [])],
    }));
    if (item.category === 'jobs') {
      setSelections((prev) => ({ ...prev, job: item }));
    }
  };

  const refreshJob = useCallback(
    async (jobId) => {
      try {
        const response = await axios.get(`${apiUrl}status/${jobId}`, {
          params: { tenantId },
        });
        setJobs((prev) =>
          prev.map((job) => (job.jobId === jobId ? { ...job, ...response.data } : job)),
        );
      } catch (error) {
        console.error('Failed to refresh job status', error);
      }
    },
    [apiUrl, tenantId],
  );

  useEffect(() => {
    const activeJobs = jobs.filter((job) => ['RUNNING', 'PENDING', 'STARTING'].includes(job.status));
    if (activeJobs.length === 0) {
      return undefined;
    }
    const interval = setInterval(() => {
      activeJobs.forEach((job) => {
        refreshJob(job.jobId);
      });
    }, 8000);
    return () => clearInterval(interval);
  }, [jobs, refreshJob]);

  const handleJobStarted = (payload) => {
    setJobs((prev) => [
      {
        jobId: payload.jobId,
        status: 'RUNNING',
        createdAt: new Date().toISOString(),
      },
      ...prev,
    ]);
  };

  const handleLinksLoaded = (jobId, links) => {
    setJobs((prev) =>
      prev.map((job) => (job.jobId === jobId ? { ...job, ...links } : job)),
    );
  };

  const selectedResumeKey = selections.resume?.key;
  const selectedTemplateKey = selections.template?.key;
  const selectedJobKey = selections.job?.key;

  const resumeOptions = useMemo(() => uploads.approved, [uploads.approved]);
  const templateOptions = useMemo(() => uploads.template, [uploads.template]);
  const jobOptions = useMemo(() => uploads.jobs, [uploads.jobs]);

  return (
    <main className="mx-auto max-w-6xl space-y-10 p-6">
      <header className="space-y-3">
        <h1 className="text-3xl font-bold text-white">Resume Tailoring Dashboard</h1>
        <p className="text-slate-400">
          Upload approved resumes, templates, and job descriptions, then launch a Bedrock-powered tailoring workflow.
        </p>
      </header>

      <section className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        <UploadForm apiUrl={apiUrl} tenantId={tenantId} onUploadComplete={handleUploadComplete} />
        <div className="rounded-lg bg-slate-900 p-6 shadow md:col-span-1 lg:col-span-2">
          <label htmlFor="job-description" className="block text-sm font-medium text-slate-300">
            Job Description
          </label>
          <textarea
            id="job-description"
            rows={8}
            value={jobDescriptionText}
            onChange={(event) => setJobDescriptionText(event.target.value)}
            className="mt-2 w-full rounded border border-slate-700 bg-slate-800 p-3 text-sm text-slate-100"
            placeholder="Paste the job description here"
          />
          <p className="mt-2 text-xs text-slate-500">
            Optionally upload job descriptions as files to reuse them across tailoring requests.
          </p>
        </div>
      </section>

      <section className="grid gap-6 md:grid-cols-3">
        <ResumeList
          title="Approved Resumes"
          items={resumeOptions}
          selectedKey={selectedResumeKey}
          onSelect={(item) => setSelections((prev) => ({ ...prev, resume: item }))}
        />
        <ResumeList
          title="Templates"
          items={templateOptions}
          selectedKey={selectedTemplateKey}
          onSelect={(item) => setSelections((prev) => ({ ...prev, template: item }))}
        />
        <ResumeList
          title="Job Descriptions"
          items={jobOptions}
          selectedKey={selectedJobKey}
          onSelect={(item) => setSelections((prev) => ({ ...prev, job: item }))}
        />
      </section>

      <GenerateButton
        apiUrl={apiUrl}
        tenantId={tenantId}
        selections={selections}
        jobDescriptionText={jobDescriptionText}
        onJobStarted={handleJobStarted}
      />

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold text-white">Workflow Executions</h2>
        {jobs.length === 0 ? (
          <p className="text-sm text-slate-400">No tailoring workflows have been started yet.</p>
        ) : (
          <ul className="space-y-3">
            {jobs.map((job) => (
              <li
                key={job.jobId}
                className="flex flex-col gap-3 rounded-lg border border-slate-800 bg-slate-900 p-4 text-sm text-slate-100 md:flex-row md:items-center md:justify-between"
              >
                <div className="space-y-1">
                  <p className="font-semibold">Job {job.jobId}</p>
                  <p className="text-xs text-slate-400">
                    Status: <span className="font-mono text-slate-200">{job.status}</span>
                  </p>
                  {job.validationReport && (
                    <details className="text-xs text-slate-400">
                      <summary className="cursor-pointer text-slate-300">Validation report</summary>
                      <pre className="mt-2 whitespace-pre-wrap break-words rounded bg-slate-950 p-3 text-[11px] text-slate-300">
                        {job.validationReport}
                      </pre>
                    </details>
                  )}
                  {job.error && (
                    <p className="text-xs text-rose-400">{job.error}</p>
                  )}
                </div>
                <DownloadLinks apiUrl={apiUrl} tenantId={tenantId} job={job} onLinksLoaded={handleLinksLoaded} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
};

export default Dashboard;
