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

export async function searchSimilarJobs(
  role: string,
  location?: string,
  limit: number = 5,
): Promise<import('./types').JobSearchResponse> {
  const params = new URLSearchParams({
    role: role.trim(),
    limit: String(Math.min(Math.max(limit, 1), 30)),
  });
  if (location && location.trim()) {
    params.set('location', location.trim());
  }
  const url = `${API_BASE_URL}/v1/jobs/search?${params.toString()}`;
  const resp = await fetch(url);
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    const detail =
      typeof errorData.detail === 'string' ? errorData.detail : null;
    throw new Error(detail || `Pencarian lowongan gagal: status ${resp.status}`);
  }
  return resp.json();
}

export async function getPublishedEducationArticles(): Promise<import('./types').EducationArticle[]> {
  const url = `${API_BASE_URL}/v1/education/articles`;
  const resp = await fetch(url);
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || `Gagal mengambil artikel: status ${resp.status}`);
  }
  return resp.json();
}

export async function adminGetEducationArticles(): Promise<import('./types').EducationArticle[]> {
  const url = `${API_BASE_URL}/v1/education/admin/articles`;
  const resp = await fetch(url);
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || `Gagal mengambil daftar artikel admin: status ${resp.status}`);
  }
  return resp.json();
}

export async function adminCreateEducationArticle(
  payload: import('./types').EducationArticlePayload
): Promise<import('./types').EducationArticle> {
  const url = `${API_BASE_URL}/v1/education/admin/articles`;
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || `Gagal membuat artikel: status ${resp.status}`);
  }
  return resp.json();
}

export async function adminUpdateEducationArticle(
  articleId: string,
  payload: import('./types').EducationArticlePayload
): Promise<import('./types').EducationArticle> {
  const url = `${API_BASE_URL}/v1/education/admin/articles/${articleId}`;
  const resp = await fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || `Gagal memperbarui artikel: status ${resp.status}`);
  }
  return resp.json();
}

export async function adminDeleteEducationArticle(articleId: string): Promise<void> {
  const url = `${API_BASE_URL}/v1/education/admin/articles/${articleId}`;
  const resp = await fetch(url, { method: 'DELETE' });
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || `Gagal menghapus artikel: status ${resp.status}`);
  }
}

// ---------------- Admin Portal APIs ----------------

export async function adminLogin(
  username: string,
  password: string
): Promise<{ token: string; username: string; message: string }> {
  const url = `${API_BASE_URL}/v1/admin/login`;
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Login gagal.');
  }
  return resp.json();
}

function getAuthHeaders(token: string): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  };
}

export async function adminGetOverview(token: string): Promise<import('./types').AdminOverview> {
  const url = `${API_BASE_URL}/v1/admin/overview`;
  const resp = await fetch(url, { headers: getAuthHeaders(token) });
  if (!resp.ok) throw new Error('Gagal memuat overview database.');
  return resp.json();
}

export async function adminGetDetections(
  token: string,
  category?: string
): Promise<import('./types').AdminDetectionRecord[]> {
  const query = category ? `?category=${category}` : '';
  const url = `${API_BASE_URL}/v1/admin/detections${query}`;
  const resp = await fetch(url, { headers: getAuthHeaders(token) });
  if (!resp.ok) throw new Error('Gagal memuat log deteksi.');
  return resp.json();
}

export async function adminGetReports(
  token: string,
  statusFilter?: string
): Promise<import('./types').AdminReportRecord[]> {
  const query = statusFilter ? `?status_filter=${statusFilter}` : '';
  const url = `${API_BASE_URL}/v1/admin/reports${query}`;
  const resp = await fetch(url, { headers: getAuthHeaders(token) });
  if (!resp.ok) throw new Error('Gagal memuat laporan user.');
  return resp.json();
}

export async function adminUpdateReportStatus(
  token: string,
  reportId: string,
  status: string,
  note?: string
): Promise<import('./types').AdminReportRecord> {
  const url = `${API_BASE_URL}/v1/admin/reports/${reportId}`;
  const resp = await fetch(url, {
    method: 'PUT',
    headers: getAuthHeaders(token),
    body: JSON.stringify({ status, note, reviewer: 'admin' }),
  });
  if (!resp.ok) throw new Error('Gagal memperbarui status laporan.');
  return resp.json();
}

export async function adminGetCompanies(
  token: string,
  search?: string
): Promise<import('./types').AdminCompanyRecord[]> {
  const query = search ? `?search=${encodeURIComponent(search)}` : '';
  const url = `${API_BASE_URL}/v1/admin/companies${query}`;
  const resp = await fetch(url, { headers: getAuthHeaders(token) });
  if (!resp.ok) throw new Error('Gagal memuat registri perusahaan.');
  return resp.json();
}

export async function adminToggleCompanyFlag(
  token: string,
  companyId: string,
  isFlaggedScam: boolean
): Promise<import('./types').AdminCompanyRecord> {
  const url = `${API_BASE_URL}/v1/admin/companies/${companyId}/flag`;
  const resp = await fetch(url, {
    method: 'PUT',
    headers: getAuthHeaders(token),
    body: JSON.stringify({ is_flagged_scam: isFlaggedScam }),
  });
  if (!resp.ok) throw new Error('Gagal mengubah status perusahaan.');
  return resp.json();
}

export async function adminGetBlacklists(token: string): Promise<import('./types').AdminBlacklistRecord[]> {
  const url = `${API_BASE_URL}/v1/admin/blacklists`;
  const resp = await fetch(url, { headers: getAuthHeaders(token) });
  if (!resp.ok) throw new Error('Gagal memuat intel blacklist.');
  return resp.json();
}

export async function adminGetWaSessions(token: string): Promise<import('./types').AdminWaSessionRecord[]> {
  const url = `${API_BASE_URL}/v1/admin/wa-sessions`;
  const resp = await fetch(url, { headers: getAuthHeaders(token) });
  if (!resp.ok) throw new Error('Gagal memuat sesi WhatsApp.');
  return resp.json();
}

