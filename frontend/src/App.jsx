import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Amplify } from 'aws-amplify';
import { fetchAuthSession } from 'aws-amplify/auth';
import { Authenticator } from '@aws-amplify/ui-react';
import '@aws-amplify/ui-react/styles.css';
import Dashboard from './pages/Dashboard.jsx';

const App = ({ initialConfig }) => {
  const [config] = useState(initialConfig ?? null);
  const [error, setError] = useState(null);
  const configuredRef = useRef(false);

  const amplifyConfig = useMemo(() => {
    if (!config) return null;

    return {
      Auth: {
        Cognito: {
          userPoolId: config.userPoolId,
          userPoolClientId: config.userPoolClientId,
          identityPoolId: config.identityPoolId,
          region: config.region,
        },
      },
      API: {
        REST: {
          resumeApi: {
            endpoint: config.apiUrl,
            region: config.region,
          },
        },
      },
      Storage: {
        S3: {
          bucket: config.bucketName,
          region: config.region,
        },
      },
    };
  }, [config]);

  useEffect(() => {
    if (!amplifyConfig || configuredRef.current) {
      return;
    }

    try {
      Amplify.configure(amplifyConfig);
      configuredRef.current = true;
    } catch (err) {
      console.error('Amplify configuration failed:', err);
      setError(err);
    }
  }, [amplifyConfig]);

  if (error) {
    return (
      <div className="flex h-screen items-center justify-center bg-rose-950 text-rose-100">
        <div className="max-w-md rounded-lg border border-rose-500 p-6 text-center">
          <h1 className="text-lg font-semibold">Amplify configuration failed</h1>
          <p className="mt-2 text-sm opacity-90">{error.message}</p>
        </div>
      </div>
    );
  }

  if (!config) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-900 text-slate-200">
        <p>Configuration unavailable.</p>
      </div>
    );
  }

  return (
    <Authenticator loginMechanisms={['email']} variation="modal">
      {({ signOut, user }) => (
        <SignedInShell config={config} user={user} signOut={signOut} />
      )}
    </Authenticator>
  );
};

export default App;

const SignedInShell = ({ config, user, signOut }) => {
  const [sessionInfo, setSessionInfo] = useState({
    userId: user?.username || user?.signInDetails?.loginId || '',
    groups: [],
  });
  const [sessionError, setSessionError] = useState(null);
  const [sessionLoading, setSessionLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const loadSession = async () => {
      setSessionLoading(true);
      try {
        const session = await fetchAuthSession();
        if (cancelled) {
          return;
        }
        const payload = session.tokens?.idToken?.payload ?? {};
        const rawGroups = payload['cognito:groups'];
        const groupsArray = Array.isArray(rawGroups)
          ? rawGroups
          : typeof rawGroups === 'string'
            ? rawGroups.split(',').filter(Boolean)
            : [];
        setSessionInfo({
          userId: payload.sub || payload['cognito:username'] || user?.username || '',
          groups: groupsArray,
        });
        setSessionError(null);
      } catch (err) {
        console.error('Failed to fetch auth session', err);
        if (!cancelled) {
          setSessionError(err);
        }
      } finally {
        if (!cancelled) {
          setSessionLoading(false);
        }
      }
    };

    loadSession();
    return () => {
      cancelled = true;
    };
  }, [user]);

  const groupsLabel = sessionInfo.groups.length
    ? sessionInfo.groups.join(', ')
    : sessionLoading
      ? 'Loading…'
      : 'None';

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900/70 px-6 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm text-slate-400">Signed in as</p>
            <p className="text-base font-semibold text-slate-100">
              {sessionInfo.userId || user?.username || 'user'}
            </p>
            <p className="text-xs text-slate-500">Groups: {groupsLabel}</p>
          </div>
          <button
            type="button"
            onClick={signOut}
            className="rounded bg-slate-800 px-4 py-2 text-sm font-semibold text-slate-200 transition hover:bg-slate-700"
          >
            Sign out
          </button>
        </div>
      </header>

      {sessionError && (
        <div className="mx-auto mt-4 max-w-6xl rounded border border-amber-500 bg-amber-950/70 p-3 text-sm text-amber-100">
          Failed to read user session: {sessionError.message}
        </div>
      )}

      <Dashboard apiUrl={config.apiUrl} userId={sessionInfo.userId} userGroups={sessionInfo.groups} />
    </div>
  );
};
