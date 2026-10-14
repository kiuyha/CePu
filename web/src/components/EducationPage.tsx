import React, { useEffect, useState } from 'react';
import { 
  HelpCircle, 
  DollarSign, 
  Building2, 
  CreditCard, 
  ShieldAlert, 
  Search, 
  Eye, 
  Lock, 
  UserCheck,
  BookOpen,
  ChevronDown,
  ChevronUp
} from 'lucide-react';
import { getPublishedEducationArticles } from '../api';
import type { EducationArticle } from '../types';
import { MarkdownRenderer } from './MarkdownRenderer';

export const EducationPage: React.FC = () => {
  const [articles, setArticles] = useState<EducationArticle[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    getPublishedEducationArticles()
      .then((data) => {
        if (mounted) {
          setArticles(data);
          // Secara default buka artikel pertama jika ada
          if (data.length > 0) {
            setExpandedId(data[0].id);
          }
        }
      })
      .catch((err) => {
        console.warn('Gagal memuat artikel dari database, menggunakan fallback statis:', err);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, []);

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  return (
    <div>
      <h1 className="page-hero-title">
        Kenali <span className="highlight-blue">Penipuan</span><br />
        <span className="highlight-blue">Lowongan Kerja</span>
      </h1>
      <p className="page-hero-subtitle">
        Pelajari ciri-ciri lowongan palsu, cara kerjanya, dan bagaimana melindungi diri Anda.
      </p>

      {/* Loading Indicator */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '16px', color: 'var(--secondary-text)', fontSize: '14px' }}>
          Memuat panduan terkini...
        </div>
      )}

      {/* Dynamic Articles from Database if available */}
      {!loading && articles.length > 0 ? (
        <div style={{ marginBottom: '36px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <BookOpen size={20} color="#3898EC" />
            <h2 style={{ fontSize: '18px', fontWeight: 800, margin: 0 }}>Panduan & Artikel Resmi</h2>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {articles.map((art) => {
              const isExpanded = expandedId === art.id;
              return (
                <div
                  key={art.id}
                  style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '16px',
                    padding: '18px 20px',
                    transition: 'all 0.2s ease',
                  }}
                >
                  <div
                    onClick={() => toggleExpand(art.id)}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      cursor: 'pointer',
                      userSelect: 'none',
                    }}
                  >
                    <div>
                      <h3 style={{ fontSize: '16px', fontWeight: 700, margin: '0 0 6px 0', color: 'var(--primary-text)' }}>
                        {art.title}
                      </h3>
                      {art.tags && art.tags.length > 0 && (
                        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                          {art.tags.map((tag, idx) => (
                            <span
                              key={idx}
                              style={{
                                fontSize: '11px',
                                background: 'rgba(56, 152, 236, 0.1)',
                                color: '#3898EC',
                                padding: '2px 8px',
                                borderRadius: '12px',
                                fontWeight: 500,
                              }}
                            >
                              #{tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <button
                      type="button"
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--secondary-text)',
                        cursor: 'pointer',
                        padding: '4px',
                      }}
                    >
                      {isExpanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                    </button>
                  </div>

                  {isExpanded && (
                    <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: '1px solid var(--border-color)' }}>
                      <MarkdownRenderer content={art.body_md} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {/* Fallback Static Cards / Overview */}
      {/* Apa Itu Penipuan Lowongan Kerja */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginBottom: '8px' }}>
        <div style={{
          width: '36px',
          height: '36px',
          borderRadius: '10px',
          background: 'rgba(56, 152, 236, 0.1)',
          color: '#3898EC',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: '8px'
        }}>
          <HelpCircle size={20} />
        </div>
        <h2 className="page-hero-title" style={{ fontSize: '18px', marginBottom: '8px' }}>
          Apa Itu Penipuan Lowongan Kerja?
        </h2>
      </div>

      <div className="edu-definition-box">
        <p className="edu-definition-text">
          <strong style={{ color: '#3898EC' }}>Penipuan lowongan kerja</strong> adalah modus kejahatan di mana pelaku membuat iklan pekerjaan palsu untuk menipu pencari kerja. Korban biasanya diminta membayar biaya tertentu, memberikan data pribadi, bahkan dieksploitasi.
        </p>
      </div>

      {/* Ciri-Ciri */}
      <h2 className="page-hero-title" style={{ fontSize: '18px', marginBottom: '4px' }}>
        Ciri-Ciri Lowongan Pekerjaan Palsu
      </h2>
      <p className="page-hero-subtitle" style={{ marginBottom: '16px' }}>
        Waspadai jika menemukan tanda-tanda berikut:
      </p>

      <div className="edu-grid">
        <div className="edu-card scam">
          <div className="edu-icon-badge" style={{ background: '#FFE4E6', color: '#E11D48' }}>
            <DollarSign size={18} />
          </div>
          <div className="edu-card-title">Gaji Tidak Realistis</div>
          <div className="edu-card-desc">
            Menawarkan gaji sangat tinggi untuk pekerjaan yang sederhana tanpa pengalaman.
          </div>
        </div>

        <div className="edu-card scam">
          <div className="edu-icon-badge" style={{ background: '#FFE4E6', color: '#E11D48' }}>
            <Building2 size={18} />
          </div>
          <div className="edu-card-title">Perusahaan Tidak Jelas</div>
          <div className="edu-card-desc">
            Nama perusahaan tidak bisa ditemukan di internet atau tidak memiliki website resmi.
          </div>
        </div>

        <div className="edu-card scam">
          <div className="edu-icon-badge" style={{ background: '#FFE4E6', color: '#E11D48' }}>
            <CreditCard size={18} />
          </div>
          <div className="edu-card-title">Meminta Biaya</div>
          <div className="edu-card-desc">
            Meminta uang pendaftaran, biaya training, atau biaya administrasi di awal.
          </div>
        </div>

        <div className="edu-card scam">
          <div className="edu-icon-badge" style={{ background: '#FFE4E6', color: '#E11D48' }}>
            <ShieldAlert size={18} />
          </div>
          <div className="edu-card-title">Garansi Pasti Diterima</div>
          <div className="edu-card-desc">
            Menjanjikan pasti diterima kerja tanpa proses seleksi yang wajar.
          </div>
        </div>
      </div>

      {/* Tips Pencegahan */}
      <h2 className="page-hero-title" style={{ fontSize: '18px', marginBottom: '4px' }}>
        Tips Pencegahan
      </h2>
      <p className="page-hero-subtitle" style={{ marginBottom: '16px' }}>
        Langkah sederhana untuk melindungi diri Anda:
      </p>

      <div className="edu-grid">
        <div className="edu-card tip">
          <div className="edu-icon-badge" style={{ background: '#DCFCE7', color: '#16A34A' }}>
            <Search size={18} />
          </div>
          <div className="edu-card-title">Riset Perusahaan</div>
          <div className="edu-card-desc">
            Selalu cek keberadaan perusahaan di Google, LinkedIn, dan situs resmi.
          </div>
        </div>

        <div className="edu-card tip">
          <div className="edu-icon-badge" style={{ background: '#DCFCE7', color: '#16A34A' }}>
            <Eye size={18} />
          </div>
          <div className="edu-card-title">Perhatikan Detail</div>
          <div className="edu-card-desc">
            Cek ejaan, logo, dan format komunikasi. Perusahaan profesional jarang melakukan kesalahan.
          </div>
        </div>

        <div className="edu-card tip">
          <div className="edu-icon-badge" style={{ background: '#DCFCE7', color: '#16A34A' }}>
            <Lock size={18} />
          </div>
          <div className="edu-card-title">Jangan Berikan Data Pribadi</div>
          <div className="edu-card-desc">
            Jangan kirim KTP, rekening bank, atau data sensitif sebelum resmi diterima.
          </div>
        </div>

        <div className="edu-card tip">
          <div className="edu-icon-badge" style={{ background: '#DCFCE7', color: '#16A34A' }}>
            <UserCheck size={18} />
          </div>
          <div className="edu-card-title">Verifikasi Kontak</div>
          <div className="edu-card-desc">
            Hubungi perusahaan melalui nomor resmi di website, bukan nomor yang diberikan perekrut.
          </div>
        </div>
      </div>
    </div>
  );
};
