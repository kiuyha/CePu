import React, { useState, useRef } from 'react';
import { UploadCloud, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { detectJob } from '../api';
import type { DetectResponse } from '../types';
import { ResultModal } from './ResultModal';

export const DetectPage: React.FC = () => {
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);

  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<DetectResponse | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!phone && !email && !company && !text && !file) {
      setErrorMessage('Harap isi minimal satu informasi (teks, nomor HP, email, perusahaan, atau gambar)');
      return;
    }

    setErrorMessage(null);
    setLoading(true);

    const formData = new FormData();
    if (phone.trim()) formData.append('phone', phone.trim());
    if (email.trim()) formData.append('email', email.trim());
    if (company.trim()) formData.append('company', company.trim());
    if (text.trim()) formData.append('text', text.trim());
    if (file) formData.append('image', file);

    try {
      const data = await detectJob(formData);
      setResult(data);
    } catch (err: any) {
      setErrorMessage(err.message || 'Terjadi kesalahan saat memproses deteksi');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 className="page-hero-title">
        Cek <span className="highlight-blue">Keamanan</span><br />
        <span className="highlight-blue">Lowongan Pekerjaan</span>
      </h1>
      <p className="page-hero-subtitle">
        Masukkan informasi lowongan kerja yang Anda terima dan kami akan menganalisis tingkat keamanannya.
      </p>

      {errorMessage && (
        <div style={{
          background: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid #FCA5A5',
          color: '#DC2626',
          padding: '12px',
          borderRadius: '10px',
          fontSize: '12.5px',
          marginBottom: '16px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px'
        }}>
          <AlertCircle size={16} />
          <span>{errorMessage}</span>
        </div>
      )}

      <form className="form-card" onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label">Nomor HP Perekrut</label>
          <input
            type="text"
            className="form-input"
            placeholder="08xxxxxxxxxx"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Email Perekrut</label>
          <input
            type="email"
            className="form-input"
            placeholder="cepu@gmail.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Nama Perusahaan</label>
          <input
            type="text"
            className="form-input"
            placeholder="PT Cepu"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Teks / Pesan Lowongan</label>
          <textarea
            className="form-textarea"
            placeholder="Salin teks lowongan yang ingin dicek di sini..."
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Screenshot Lowongan</label>
          <div
            className="upload-dropzone"
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
          >
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: 'none' }}
              accept="image/png, image/jpeg, image/webp"
              onChange={handleFileChange}
            />
            {file ? (
              <div className="uploaded-preview-badge">
                <CheckCircle2 size={16} />
                <span>{file.name} ({(file.size / 1024).toFixed(1)} KB)</span>
              </div>
            ) : (
              <>
                <UploadCloud size={28} className="upload-icon" />
                <span className="upload-main-text">Klik atau seret file ke sini</span>
                <span className="upload-sub-text">PNG, JPG, PDF (maks 5MB)</span>
              </>
            )}
          </div>
        </div>

        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? (
            <>
              <Loader2 size={18} className="animate-spin" />
              <span>Menganalisis...</span>
            </>
          ) : (
            'Deteksi Sekarang'
          )}
        </button>
      </form>

      {result && (
        <ResultModal
          result={result}
          onClose={() => setResult(null)}
        />
      )}
    </div>
  );
};
