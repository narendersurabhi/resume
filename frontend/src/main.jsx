import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './styles.css';

const rootElement = document.getElementById('root');
const root = ReactDOM.createRoot(rootElement);

const LoadingScreen = () => (
  <div className="flex h-screen items-center justify-center bg-slate-900 text-slate-200">
    <p>Loading application…</p>
  </div>
);

const ErrorScreen = ({ message }) => (
  <div className="flex h-screen items-center justify-center bg-rose-950 text-rose-100">
    <div className="max-w-md rounded-lg border border-rose-500 p-6 text-center">
      <h1 className="text-lg font-semibold">Configuration Error</h1>
      <p className="mt-2 text-sm opacity-90">{message}</p>
      <p className="mt-4 text-xs opacity-70">Check that config.json is available in the frontend bucket.</p>
    </div>
  </div>
);

async function bootstrap() {
  root.render(<LoadingScreen />);

  try {
    const response = await fetch('/config.json', { cache: 'no-cache' });
    if (!response.ok) {
      throw new Error(`Failed to load config.json (status ${response.status})`);
    }

    const config = await response.json();
    window.__APP_CONFIG__ = config;

    root.render(
      <React.StrictMode>
        <App initialConfig={config} />
      </React.StrictMode>,
    );
  } catch (err) {
    console.error('Failed to bootstrap frontend config:', err);
    root.render(<ErrorScreen message={err.message} />);
  }
}

bootstrap();
