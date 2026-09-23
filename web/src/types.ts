export interface DetectResponse {
  request_id: string;
  risk_score: number;
  category: 'rendah' | 'sedang' | 'tinggi';
  reasons: string[];
  alternatives: string[];
  degraded_sources: string[];
  processing_ms: number;
  model_version: string;
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
