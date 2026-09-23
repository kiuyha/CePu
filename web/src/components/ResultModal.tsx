import React from 'react';
import { 
  ShieldCheck, 
  AlertTriangle, 
  AlertOctagon, 
  X, 
  CheckCircle, 
  Briefcase 
} from 'lucide-react';
import type { DetectResponse } from '../types';

interface ResultModalProps {
  result: DetectResponse;
  onClose: () => void;
}

export const ResultModal: React.FC<ResultModalProps> = ({ result, onClose }) => {
  const isSafe = result.category === 'rendah';
  const isWarn = result.category === 'sedang';
  const isDanger = result.category === 'tinggi';

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

        {result.reasons && result.reasons.length > 0 && (
          <div className="result-reasons-container">
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

        {result.alternatives && result.alternatives.length > 0 && (
          <div className="alternatives-container">
            <h4 className="reasons-header">Rekomendasi Lowongan Pekerjaan:</h4>
            <div className="reasons-list">
              {result.alternatives.map((alt, idx) => (
                <div key={idx} className="alternative-item">
                  <Briefcase size={15} color="#10B981" />
                  <span>{alt}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
