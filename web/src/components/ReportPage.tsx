import React, { useState, useRef } from 'react';
import { UploadCloud, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { submitReport } from '../api';

export const ReportPage: React.FC = () => {
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);

  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successReportId, setSuccessReportId] = useState<string | null>(null);

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
      setErrorMessage('Harap isi minimal satu informasi lowongan yang ingin dilaporkan');
      return;
    }

    setErrorMessage(null);
    setLoading(true);

    const formData = new FormData();
    if (phone.trim()) formData.append('suspect_phone', phone.trim());
    if (email.trim()) formData.append('suspect_email', email.trim());
    if (company.trim()) formData.append('suspect_company', company.trim());
    if (text.trim()) formData.append('message_raw', text.trim());
    if (file) formData.append('screenshot', file);

    try {
      const data = await submitReport(formData);
      setSuccessReportId(data.id);
      // Reset form
      setPhone('');
      setEmail('');
      setCompany('');
      setText('');
      setFile(null);
    } catch (err: any) {
      setErrorMessage(err.message || 'Gagal mengirim laporan');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 className="page-hero-title">
        Laporkan <span className="highlight-danger">Lowongan</span><br />
        <span className="highlight-danger">Mencurigakan</span>
      </h1>
      <p className="page-hero-subtitle">
        Bantu lindungi pencari kerja lainnya dengan melaporkan lowongan yang Anda temui sebagai penipuan.
      </p>

      {successReportId && (
        <div style={{
          background: 'rgba(34, 197, 94, 0.1)',
          border: '1px solid #86EFAC',
          color: '#15803D',
          padding: '14px',
          borderRadius: '12px',
          fontSize: '13px',
          marginBottom: '20px',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'bold' }}>
            <CheckCircle2 size={18} />
            <span>Laporan Berhasil Terkirim!</span>
          </div>
          <span style={{ fontSize: '11.5px', opacity: 0.9 }}>
            ID Laporan: {successReportId}. Terima kasih telah berkontribusi menjaga keamanan komunitas kerja.
          </span>
        </div>
      )}

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
          <label className="form-label">Nomor HP Penipu</label>
          <input
            type="text"
            className="form-input"
            placeholder="08xxxxxxxxxx"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Email Penipu</label>
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
            placeholder="Salin teks lowongan yang mencurigakan di sini..."
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

        <button type="submit" className="btn-danger" disabled={loading}>
          {loading ? (
            <>
              <Loader2 size={18} className="animate-spin" />
              <span>Mengirim Laporan...</span>
            </>
          ) : (
            'Kirim Laporan'
          )}
        </button>
      </form>
    </div>
  );
};
