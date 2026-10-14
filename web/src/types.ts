export interface JobAlternative {
  company: string;
  title: string;
  url: string;
}

export interface ReportStats {
  total: number;
  verified: number;
  matched_by: string[];
}

export interface DetectResponse {
  request_id: string;
  risk_score: number;
  category: 'rendah' | 'sedang' | 'tinggi';
  reasons: string[];
  alternatives: (string | JobAlternative)[];
  degraded_sources: string[];
  processing_ms: number;
  model_version: string;
  report_stats?: ReportStats | null;
}

export interface JobListing {
  id: string | null;
  title: string | null;
  company: string | null;
  location: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_display: string | null;
  work_type: string | null;
  listed_at: string | null;
  listed_label: string | null;
  url: string | null;
}

export interface JobSearchResponse {
  role: string;
  location: string | null;
  count: number;
  source: 'db' | 'live' | 'empty';
  jobs: JobListing[];
}

export interface ReportResponse {
  id: string;
  status: string;
}

export interface HealthResponse {
  status: string;
  model_loaded: boolean;
  model_version: string;
  model_load_error?: string | null;
}

export interface EducationArticle {
  id: string;
  slug: string;
  title: string;
  body_md: string;
  tags?: string[] | null;
  published: boolean;
  published_at?: string | null;
}

export interface EducationArticlePayload {
  title: string;
  body_md: string;
  slug?: string;
  tags?: string[];
  published: boolean;
}

export interface AdminOverview {
  detections: number;
  reports: number;
  pending_reports: number;
  companies: number;
  blacklists: number;
  articles: number;
}

export interface AdminDetectionRecord {
  id: string;
  created_at: string;
  channel: string;
  text_input?: string | null;
  ocr_text?: string | null;
  p_bert?: number | null;
  v_company?: number | null;
  v_phone?: number | null;
  v_email?: number | null;
  risk_score?: number | null;
  category?: 'rendah' | 'sedang' | 'tinggi' | null;
  reasons?: string[] | null;
  degraded_sources?: string[] | null;
  processing_ms?: number | null;
  model_version?: string | null;
}

export interface AdminReportRecord {
  id: string;
  created_at: string;
  channel: string;
  contact_optional?: string | null;
  suspect_phone?: string | null;
  suspect_email?: string | null;
  suspect_company?: string | null;
  message_raw?: string | null;
  screenshot_path?: string | null;
  status: string;
  reviewer?: string | null;
  note?: string | null;
}

export interface AdminCompanyRecord {
  id: string;
  name_norm: string;
  legal_name: string;
  ahu_no?: string | null;
  registered?: boolean | null;
  is_flagged_scam: boolean;
  source: string;
  updated_at: string;
}

export interface AdminBlacklistRecord {
  id: string;
  kind: string;
  value_masked: string;
  report_count: number;
  last_reported_at: string;
  sources?: string[] | null;
  active: boolean;
}

export interface AdminWaSessionRecord {
  phone_hash: string;
  current_state: string;
  context?: Record<string, any> | null;
  last_active_at: string;
}
