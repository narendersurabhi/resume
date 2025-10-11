import React, { useMemo, useState } from 'react';
import axios from 'axios';
import UploadForm from '../components/UploadForm.jsx';
import ResumeList from '../components/ResumeList.jsx';
import GenerateButton from '../components/GenerateButton.jsx';

const Dashboard = ({ apiUrl }) => {
  const [tenantId] = useState('demo-tenant');
  const [uploads, setUploads] = useState({ approved: [], template: [], jobs: [] });
  const [selections, setSelections] = useState({ resume: null, template: null, job: null });
  const [jobDescription, setJobDescription] = useState('');
  const [generatedOutputs, setGeneratedOutputs] = useState([]);

  const handleUploadComplete = (item) => {
    setUploads((prev) => ({
      ...prev,
      [item.category]: [...(prev[item.category] ?? []), item],
    }));
  };

  // === Option B: do NOT fetch download links automatically ===
  const handleGenerated = (result) => {
    setGeneratedOutputs((prev) => [
      {
        ...result,
        createdAt: new Date().toISOString(),
        docxUrl: null,
        pdfUrl: null,
        linksLoading: false,
        linksError: null,
      },
      ...prev,
    ]);
  };

  const fetchLinks = async (out) => {
    setGeneratedOutputs(prev =>
      prev.map(x => x.outputId === out.outputId ? { ...x, linksLoading: true, linksError: null } : x)
    );

    try {
      const url = (p) => new URL(p, apiUrl).href;   // safe with/without trailing slash
      const reqs = [];
      const index = {}; // track positions

      if (out.docxKey) { index.docx = reqs.length;
        reqs.push(axios.get(url('download'), { params: { key: out.docxKey } }));
      }
      if (out.pdfKey)  { index.pdf  = reqs.length;
        reqs.push(axios.get(url('download'), { params: { key: out.pdfKey } }));
      }

      const results = await Promise.allSettled(reqs);
      const docxRes = index.docx !== undefined ? results[index.docx] : null;
      const pdfRes  = index.pdf  !== undefined ? results[index.pdf]  : null;

      const docxUrl = docxRes?.status === 'fulfilled' ? docxRes.value?.data?.url : null;
      const pdfUrl  = pdfRes?.status  === 'fulfilled' ? pdfRes.value?.data?.url  : null;

      setGeneratedOutputs(prev =>
        prev.map(x => x.outputId === out.outputId
          ? { ...x, linksLoading: false, linksError: (!docxUrl && out.docxKey) || (!pdfUrl && out.pdfKey) ? 'Failed to fetch some links' : null,
              docxUrl, pdfUrl }
          : x)
      );
    } catch (e) {
      setGeneratedOutputs(prev =>
        prev.map(x => x.outputId === out.outputId ? { ...x, linksLoading: false, linksError: 'Failed to fetch download links' } : x)
      );
    }
  };


  const preparedSelections = useMemo(
    () => ({
      ...selections,
      job: jobDescription ? { content: jobDescription } : selections.job,
    }),
    [selections, jobDescription]
  );

  return (
    <main className="mx-auto max-w-6xl space-y-10 p-6">
      <header className="space-y-3">
        <h1 className="text-3xl font-bold text-white">Resume Tailoring Dashboard</h1>
        <p className="text-slate-400">
          Upload approved resumes and templates, provide job descriptions, then generate tailored outputs ready for download.
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
            value={jobDescription}
            onChange={(event) => setJobDescription(event.target.value)}
            className="mt-2 w-full rounded border border-slate-700 bg-slate-800 p-3 text-sm text-slate-100"
            placeholder="Paste the job description here"
          />
          <p className="mt-2 text-xs text-slate-500">
            You can also upload job descriptions as files and select them below.
          </p>
        </div>
      </section>

      <section className="grid gap-6 md:grid-cols-3">
        <ResumeList
          title="Approved Resumes"
          items={uploads.approved}
          onSelect={(item) => setSelections((prev) => ({ ...prev, resume: item }))}
        />
        <ResumeList
          title="Templates"
          items={uploads.template}
          onSelect={(item) => setSelections((prev) => ({ ...prev, template: item }))}
        />
        <ResumeList
          title="Job Descriptions"
          items={uploads.jobs}
          onSelect={(item) => setSelections((prev) => ({ ...prev, job: item }))}
        />
      </section>

      <GenerateButton
        apiUrl={apiUrl}
        tenantId={tenantId}
        selections={preparedSelections}
        onGenerated={handleGenerated}
      />

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold text-white">Generated Outputs</h2>
        {generatedOutputs.length === 0 ? (
          <p className="text-sm text-slate-400">No tailored resumes generated yet.</p>
        ) : (
          <ul className="space-y-3">
            {generatedOutputs.map((output) => (
              <li
                key={output.outputId}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-900 p-4 text-sm text-slate-100"
              >
                <div>
                  <p className="font-semibold">Output {output.outputId}</p>
                  <p className="text-xs text-slate-400">Generated {output.createdAt}</p>
                  {output.linksError && (
                    <p className="mt-1 text-xs text-rose-400">{output.linksError}</p>
                  )}
                </div>
                <div className="flex gap-2">
                  {output.docxUrl ? (
                    <a
                      href={output.docxUrl}
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
    </main>
  );
};

export default Dashboard;
