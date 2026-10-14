import React, { useEffect, useState } from 'react';
import {
  ShieldCheck,
  AlertTriangle,
  AlertOctagon,
  X,
  CheckCircle,
  Briefcase,
  Search,
  MapPin,
  ExternalLink,
  Loader2,
} from 'lucide-react';
import type { DetectResponse, JobListing } from '../types';
import { searchSimilarJobs } from '../api';

interface ResultModalProps {
  result: DetectResponse;
  onClose: () => void;
}

const SimilarJobs: React.FC<{ requestId: string }> = ({ requestId }) => {
  const [open, setOpen] = useState(false);
  const [role, setRole] = useState('');
  const [location, setLocation] = useState('');
  const [jobs, setJobs] = useState<JobListing[] | null>(null);
  const [searchedRole, setSearchedRole] = useState('');
  const [source, setSource] = useState<'db' | 'live' | 'empty' | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset tiap hasil deteksi baru
  useEffect(() => {
    setOpen(false);
    setRole('');
    setLocation('');
    setJobs(null);
    setSearchedRole('');
    setSource(null);
    setError(null);
    setLoading(false);
  }, [requestId]);

  // Escape menutup popup dalam dulu
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open ]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!role.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const data = await searchSimilarJobs(role, location || undefined, 10);
      setJobs(data.jobs);
      setSearchedRole(data.role);
      setSource(data.source);
    } catch (err: any) {
      setError(err.message || 'Gagal mencari lowongan. Coba lagi.');
      setJobs(null);
      setSource(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="alternatives-container">
      <div className="similar-jobs-trigger">
        <div className="trigger-icon">
          <Briefcase size={20} />
        </div>
        <div className="trigger-text">
          <h4>Butuh alternatif yang lebih aman?</h4>
          <p>Pekerjaan yang mirip dari data tersimpan, lengkap dengan tautan.</p>
        </div>
        <button type="button" className="btn-primary btn-sm" onClick={() => setOpen(true)}>
          <Search size={14} />
          <span>Cari yang Mirip</span>
        </button>
      </div>

      {open && (
        <div className="similar-jobs-overlay" onClick={() => setOpen(false)}>
          <div className="similar-jobs-modal" onClick={(e) => e.stopPropagation()}>
            <div className="similar-jobs-modal-head">
              <div>
                <h3>Cari Pekerjaan yang Mirip</h3>
                <p>Lowongan sejenis dari data tersimpan.</p>
              </div>
              <button
                type="button"
                className="icon-btn"
                onClick={() => setOpen(false)}
                title="Tutup"
              >
                <X size={18} />
              </button>
            </div>

            <form className="similar-jobs-form row" onSubmit={handleSearch}>
              <input
                type="text"
                className="form-input"
                placeholder="Posisi, cth: driver"
                value={role}
                onChange={(e) => setRole(e.target.value)}
              />
              <input
                type="text"
                className="form-input"
                placeholder="Lokasi (opsional)"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
              />
              <button type="submit" className="btn-primary btn-sm" disabled={!role.trim() || loading}>
                {loading ? <Loader2 size={14} className="spin-icon" /> : <Search size={14} />}
                <span>{loading ? 'Mencari...' : 'Cari'}</span>
              </button>
            </form>

            <div className="similar-jobs-modal-body">
              {error && <div className="similar-jobs-error">{error}</div>}

              {jobs !== null && !error && (
                jobs.length === 0 ? (
                  <div className="similar-jobs-empty">
                    Tidak menemukan lowongan '{searchedRole}'. Coba kata kunci lain atau tambah lokasi.
                  </div>
                ) : (
                  <>
                    <div className="similar-jobs-count">
                      Ditemukan <strong>{jobs.length} lowongan</strong> untuk '{searchedRole}'
                      {source !== null && source !== 'empty' && (
                        <span className="similar-jobs-source inline">
                          {source === 'db' ? ' · dari data tersimpan' : ' · baru dari JobStreet'}
                        </span>
                      )}
                    </div>
                    <div className="similar-jobs-list">
                      {jobs.map((job, idx) => (
                        <div key={job.id ?? idx} className="similar-job-card">
                          <div className="similar-job-title">
                            {job.url ? (
                              <a href={job.url} target="_blank" rel="noopener noreferrer" className="job-link">
                                {job.title || '(tanpa judul)'}
                              </a>
                            ) : (
                              <span>{job.title || '(tanpa judul)'}</span>
                            )}
                          </div>
                          <div className="similar-job-meta">
                            {job.company && <span>{job.company}</span>}
                            {job.location && (
                              <span className="similar-job-loc">
                                <MapPin size={12} /> {job.location}
                              </span>
                            )}
                          </div>
                          {job.salary_display && (
                            <div className="similar-job-salary">{job.salary_display}</div>
                          )}
                          {job.url && (
                            <a
                              href={job.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="similar-job-open"
                            >
                              Buka lowongan <ExternalLink size={12} />
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  </>
                )
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export const ResultModal: React.FC<ResultModalProps> = ({ result, onClose }) => {
  const isSafe = result.category === 'rendah';
  const isWarn = result.category === 'sedang';
  const isDanger = result.category === 'tinggi';
  const needsAlternatives = isWarn || isDanger;

  const cardVariant = isSafe ? 'safe' : isWarn ? 'warn' : 'danger';
  const title = isSafe ? 'Aman' : isWarn ? 'Hati-Hati' : 'Bahaya';
  const riskLabel = isSafe
    ? 'Tingkat risiko penipuan Rendah'
    : isWarn
    ? 'Tingkat risiko penipuan Sedang'
    : 'Tingkat risiko penipuan Tinggi';

  return (
    <div className="result-modal-overlay" onClick={onClose}>
      <div
        className={`result-card ${cardVariant}`}
        onClick={(e) => e.stopPropagation()}
      >
        <button className="result-close-btn" onClick={onClose}>
          <X size={18} />
        </button>

        <div className="result-icon-wrapper">
          {isSafe && <ShieldCheck size={54} color="#22C55E" />}
          {isWarn && <AlertTriangle size={54} color="#F59E0B" />}
          {isDanger && <AlertOctagon size={54} color="#EF4444" />}
        </div>

        <h3 className={`result-title ${cardVariant}`}>{title}</h3>
        <p className="result-risk-level">{riskLabel}</p>

        {/* Risk Score Pill */}
        <div className={`result-score-badge ${cardVariant}`}>
          <span className="score-num">{(result.risk_score * 100).toFixed(1)}%</span>
          <span className="score-label">Skor Risiko: {result.risk_score.toFixed(3)}</span>
        </div>

        {result.report_stats && result.report_stats.total > 0 && (
          <div className={`report-count-banner ${cardVariant}`}>
            <AlertTriangle size={16} />
            <span>
              Dilaporkan oleh <strong>{result.report_stats.total} pengguna</strong>
              {result.report_stats.verified > 0 && (
                <> (<strong>{result.report_stats.verified} terverifikasi</strong> penipuan)</>
              )}
              . <span className="report-count-note">Tidak memengaruhi skor — info tambahan.</span>
            </span>
          </div>
        )}

        {result.reasons && result.reasons.length > 0 && (          <div className="result-reasons-container">
            <h4 className="reasons-header">
              {isSafe ? 'Alasan:' : 'Alasan Terindikasi:'}
            </h4>
            <div className="reasons-list">
              {result.reasons.map((reason, idx) => (
                <div key={idx} className="reason-item">
                  <span className="reason-icon">
                    {isSafe ? (
                      <CheckCircle size={15} color="#22C55E" />
                    ) : (
                      <AlertTriangle
                        size={15}
                        color={isWarn ? '#F59E0B' : '#EF4444'}
                      />
                    )}
                  </span>
                  <span>{reason}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {needsAlternatives && <SimilarJobs requestId={result.request_id} />}
      </div>
    </div>
  );
};
