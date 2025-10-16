import axios from 'axios';
import { fetchAuthSession } from 'aws-amplify/auth';

const ensureAbsoluteUrl = (baseUrl, path) => {
  if (!baseUrl) {
    throw new Error('API base URL is not defined.');
  }
  const base = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`;
  const normalizedPath = (path ?? '').replace(/^\/+/, '');
  return new URL(normalizedPath, base).toString();
};

const buildHeaders = async (extraHeaders = {}) => {
  const session = await fetchAuthSession();
  const token = session?.tokens?.idToken?.toString();
  return token ? { Authorization: token, ...extraHeaders } : { ...extraHeaders };
};

export const apiPost = async (baseUrl, path, data, options = {}) => {
  const headers = await buildHeaders(options.headers);
  const url = ensureAbsoluteUrl(baseUrl, path);
  return axios.post(url, data, { ...options, headers });
};

export const apiGet = async (baseUrl, path, options = {}) => {
  const headers = await buildHeaders(options.headers);
  const url = ensureAbsoluteUrl(baseUrl, path);
  return axios.get(url, { ...options, headers });
};

export const apiDelete = async (baseUrl, path, options = {}) => {
  const headers = await buildHeaders(options.headers);
  const url = ensureAbsoluteUrl(baseUrl, path);
  return axios.delete(url, { ...options, headers });
};
