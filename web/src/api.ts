import type { DetectResponse, ReportResponse, HealthResponse } from './types';

const API_BASE_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

export async function detectJob(formData: FormData): Promise<DetectResponse> {
  const url = `${API_BASE_URL}/v1/detect`;
  const resp = await fetch(url, {
    method: 'POST',
    body: formData,
  });

  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || `Deteksi gagal: status ${resp.status}`);
  }

  return resp.json();
}

export async function submitReport(formData: FormData): Promise<ReportResponse> {
  const url = `${API_BASE_URL}/v1/reports`;
  const resp = await fetch(url, {
    method: 'POST',
    body: formData,
  });

  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || `Laporan gagal dikirim: status ${resp.status}`);
  }

  return resp.json();
}

export async function checkHealth(): Promise<HealthResponse> {
  const url = `${API_BASE_URL}/healthz`;
  const resp = await fetch(url);
  if (!resp.ok) {
    throw new Error('Health check error');
  }
  return resp.json();
}
