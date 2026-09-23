import type { DetectResponse, ReportResponse, HealthResponse } from './types';

const API_BASE_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

export interface ProgressUpdate {
  stage: string;
  message: string;
  percent: number;
}

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

export async function detectJobStream(
  formData: FormData,
  onProgress: (progress: ProgressUpdate) => void
): Promise<DetectResponse> {
  const url = `${API_BASE_URL}/v1/detect/stream`;
  const resp = await fetch(url, {
    method: 'POST',
    body: formData,
  });

  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || `Deteksi gagal: status ${resp.status}`);
  }

  const reader = resp.body?.getReader();
  if (!reader) {
    throw new Error('Streaming tidak didukung oleh browser Anda');
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let finalResult: DetectResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n\n');
    buffer = lines.pop() || '';

    for (const block of lines) {
      for (const line of block.split('\n')) {
        if (line.startsWith('data: ')) {
          try {
            const payload = JSON.parse(line.slice(6));
            if (payload.type === 'progress') {
              onProgress({
                stage: payload.stage,
                message: payload.message,
                percent: payload.percent,
              });
            } else if (payload.type === 'result') {
              finalResult = payload.data as DetectResponse;
            } else if (payload.type === 'error') {
              throw new Error(payload.message || 'Terjadi kesalahan pada analisis server.');
            }
          } catch (e: any) {
            if (e.message && !e.message.includes('JSON')) {
              throw e;
            }
          }
        }
      }
    }
  }

  if (!finalResult) {
    throw new Error('Hasil analisis tidak diterima dari server.');
  }

  return finalResult;
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
