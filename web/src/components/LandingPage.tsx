import React from 'react';
import { 
  AlertTriangle, 
  TrendingUp, 
  Zap, 
  BookOpen, 
  Flag, 
  Search 
} from 'lucide-react';

interface LandingPageProps {
  onNavigate: (tab: 'home' | 'detect' | 'education' | 'report') => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({ onNavigate }) => {
  return (
    <div>
      <h1 className="page-hero-title">
        Jangan Sampai Jadi Korban <span className="highlight-blue">Lowongan Palsu!</span>
      </h1>
      <p className="page-hero-subtitle">
        CePu membantu Anda mengenali, mendeteksi, dan melaporkan penipuan lowongan kerja di media sosial.
      </p>

      <div className="landing-cta-group">
        <button className="btn-primary" onClick={() => onNavigate('detect')}>
          Cek Lowongan Sekarang
        </button>
        <button className="btn-outline" onClick={() => onNavigate('education')}>
          Pelajari Selengkapnya
        </button>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon red">
            <AlertTriangle size={17} />
          </div>
          <div className="stat-value">18.220+</div>
          <div className="stat-label">Kasus Penipuan Digital Tercatat</div>
        </div>

        <div className="stat-card">
          <div className="stat-icon blue">
            <TrendingUp size={17} />
          </div>
          <div className="stat-value">38%</div>
          <div className="stat-label">Penipuan Loker Asia Pasifik Berasal dari Indonesia</div>
        </div>

        <div className="stat-card">
          <div className="stat-icon orange">
            <Zap size={17} />
          </div>
          <div className="stat-value">7 Triliun</div>
          <div className="stat-label">Kerugian Akibat Scam</div>
        </div>
      </div>

      <h2 className="page-hero-title" style={{ fontSize: '20px', marginBottom: '6px' }}>
        Apa yang Bisa Anda Lakukan?
      </h2>
      <p className="page-hero-subtitle" style={{ marginBottom: '18px' }}>
        Tiga langkah sederhana untuk melindungi diri Anda dan orang lain dari penipuan lowongan kerja
      </p>

      <div className="action-cards">
        <div className="action-card" onClick={() => onNavigate('education')}>
          <div className="action-icon blue">
            <BookOpen size={22} />
          </div>
          <div className="action-info">
            <h4>Edukasi</h4>
            <p>Pelajari ciri-ciri lowongan pekerjaan palsu dan cara melindungi diri Anda dari penipuan.</p>
          </div>
        </div>

        <div className="action-card" onClick={() => onNavigate('report')}>
          <div className="action-icon pink">
            <Flag size={22} />
          </div>
          <div className="action-info">
            <h4>Laporkan</h4>
            <p>Bantu orang lain dengan melaporkan lowongan pekerjaan yang terbukti merupakan penipuan.</p>
          </div>
        </div>

        <div className="action-card" onClick={() => onNavigate('detect')}>
          <div className="action-icon green">
            <Search size={22} />
          </div>
          <div className="action-info">
            <h4>Deteksi</h4>
            <p>Cek apakah lowongan pekerjaan yang Anda terima aman atau berpotensi penipuan.</p>
          </div>
        </div>
      </div>
    </div>
  );
};
