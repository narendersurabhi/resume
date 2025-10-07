import React, { useEffect, useState } from "react";
import { Amplify } from "aws-amplify";
import { getCurrentUser } from "aws-amplify/auth";
import { get, post } from "aws-amplify/api";
import { uploadData } from "aws-amplify/storage";

import Dashboard from "./pages/Dashboard.jsx";
import runtimeConfig from "../public/config.json?url";

const App = () => {
  const [config, setConfig] = useState(null);

  useEffect(() => {
    const loadConfig = async () => {
      try {
        const response = await fetch(runtimeConfig);
        const data = await response.json();

        console.log("✅ Loaded runtime config:", data);

        Amplify.configure({
          Auth: {
            Cognito: {
              userPoolId: data.userPoolId,
              userPoolClientId: data.userPoolClientId,
              identityPoolId: data.identityPoolId,
              region: data.region,
            },
          },
          API: {
            REST: {
              resumeApi: {
                endpoint: data.apiUrl,
                region: data.region,
              },
            },
          },
          Storage: {
            S3: {
              bucket: data.bucketName,
              region: data.region,
            },
          },
        });

        setConfig(data);
      } catch (err) {
        console.error("❌ Failed to load runtime config:", err);
      }
    };

    loadConfig();
  }, []);

  if (!config) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-900 text-slate-200">
        <p>Loading configuration...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <Dashboard apiUrl={config.apiUrl} />
    </div>
  );
};

export default App;
