import React, { useState, useRef, useEffect } from 'react';
import { UploadCloud, Loader2, CheckCircle2, AlertCircle, Sparkles, X } from 'lucide-react';
import { detectJobStream, type ProgressUpdate } from '../api';
import type { DetectResponse } from '../types';
import { ResultModal } from './ResultModal';

export const DetectPage: React.FC = () => {
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<ProgressUpdate | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<DetectResponse | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Helper untuk set file dan membuat preview URL
  const setUploadedFile = (newFile: File | null) => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setFile(newFile);
    if (newFile && newFile.type.startsWith('image/')) {
      setPreviewUrl(URL.createObjectURL(newFile));
    } else {
      setPreviewUrl(null);
    }
  };

  // Helper untuk fetch gambar dari URL/link jika pengguna paste URL gambar langsung
  const fetchImageFromUrl = async (url: string) => {
    try {
      setErrorMessage(null);
      const res = await fetch(url);
      if (!res.ok) throw new Error('Gagal mengunduh gambar dari tautan');
      const blob = await res.blob();
      if (!blob.type.startsWith('image/')) {
        throw new Error('Tautan bukan merupakan file gambar yang valid');
      }
      const filename = url.split('/').pop()?.split('?')[0] || 'pasted-image.png';
      const fetchedFile = new File([blob], filename, { type: blob.type });
      setUploadedFile(fetchedFile);
    } catch (err: any) {
      // Jika CORS atau gagal fetch, simpan URL ke dalam teks deskripsi
      setText((prev) => (prev ? `${prev}\n${url}` : url));
    }
  };

  // Global listener Ctrl+V / Paste dari clipboard
  useEffect(() => {
    const handlePaste = (e: ClipboardEvent) => {
      // Jika pengguna sedang fokus di input field biasa dan menempelkan teks non-image, biarkan default
      const target = e.target as HTMLElement;
      const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA';

      const items = e.clipboardData?.items;
      if (!items) return;

      // 1. Cek apakah ada file gambar di clipboard (misal: hasil screenshot Win+Shift+S / PrtSc)
      for (let i = 0; i < items.length; i++) {
        if (items[i].type.startsWith('image/')) {
          const blob = items[i].getAsFile();
          if (blob) {
            e.preventDefault();
            const extension = blob.type.split('/')[1] || 'png';
            const pastedFile = new File([blob], `screenshot-${Date.now()}.${extension}`, {
              type: blob.type,
            });
            setUploadedFile(pastedFile);
            return;
          }
        }
      }

      // 2. Jika bukan file gambar biner, periksa apakah clipboard berisi teks link gambar
      const pastedText = e.clipboardData?.getData('text')?.trim();
      if (pastedText && !isInput && /^(https?:\/\/.*\.(?:png|jpg|jpeg|webp|gif|bmp)(\?.*)?)$/i.test(pastedText)) {
        e.preventDefault();
        fetchImageFromUrl(pastedText);
      }
    };

    window.addEventListener('paste', handlePaste);
    return () => {
      window.removeEventListener('paste', handlePaste);
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setUploadedFile(e.target.files[0]);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setUploadedFile(e.dataTransfer.files[0]);
    } else {
      // Cek apakah drag-drop berupa link/URL
      const droppedUrl = e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain');
      if (droppedUrl && droppedUrl.startsWith('http')) {
        fetchImageFromUrl(droppedUrl.trim());
      }
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
    setProgress({ stage: 'init', message: 'Menghubungkan ke sistem analisis...', percent: 5 });

    const formData = new FormData();
    if (phone.trim()) formData.append('phone', phone.trim());
    if (email.trim()) formData.append('email', email.trim());
    if (company.trim()) formData.append('company', company.trim());
    if (text.trim()) formData.append('text', text.trim());
    if (file) formData.append('image', file);

    try {
      const data = await detectJobStream(formData, (update) => {
        setProgress(update);
      });
      setResult(data);
    } catch (err: any) {
      setErrorMessage(err.message || 'Terjadi kesalahan saat memproses deteksi');
    } finally {
      setLoading(false);
      setProgress(null);
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
              className={`upload-dropzone ${isDragging ? 'dragover' : ''}`}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              style={{ position: 'relative' }}
            >
              <input
                type="file"
                ref={fileInputRef}
                style={{ display: 'none' }}
                accept="image/png, image/jpeg, image/webp"
                onChange={handleFileChange}
              />
              {file ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px', width: '100%' }}>
                  {previewUrl && (
                    <div style={{ position: 'relative', maxWidth: '200px', maxHeight: '140px', overflow: 'hidden', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
                      <img src={previewUrl} alt="Preview Screenshot" style={{ width: '100%', height: 'auto', objectFit: 'contain', display: 'block' }} />
                    </div>
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div className="uploaded-preview-badge">
                      <CheckCircle2 size={16} />
                      <span>{file.name} ({(file.size / 1024).toFixed(1)} KB)</span>
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setUploadedFile(null);
                        if (fileInputRef.current) fileInputRef.current.value = '';
                      }}
                      style={{
                        background: 'rgba(239, 68, 68, 0.1)',
                        color: '#EF4444',
                        border: 'none',
                        borderRadius: '8px',
                        padding: '6px',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center'
                      }}
                      title="Hapus gambar"
                    >
                      <X size={16} />
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <UploadCloud size={28} className="upload-icon" />
                  <span className="upload-main-text">Klik, seret, atau tekan <strong>Ctrl + V</strong> untuk tempel</span>
                  <span className="upload-sub-text">Bisa langsung paste screenshot dari clipboard atau link gambar (PNG, JPG, WebP)</span>
                </>
              )}
            </div>
        </div>

        {loading && progress && (
          <div style={{
            background: 'var(--card-bg, #ffffff)',
            border: '1px solid var(--border-color, #E2E8F0)',
            borderRadius: '12px',
            padding: '16px',
            marginBottom: '16px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 600, color: 'var(--primary-blue, #2563EB)' }}>
                <Sparkles size={16} className="animate-spin" />
                <span>Progres Analisis AI & Verifikasi</span>
              </div>
              <span style={{ fontSize: '12.5px', fontWeight: 700, color: 'var(--primary-blue, #2563EB)' }}>
                {progress.percent}%
              </span>
            </div>

            {/* Progress Bar Container */}
            <div style={{
              width: '100%',
              height: '8px',
              backgroundColor: 'var(--border-color, #E2E8F0)',
              borderRadius: '999px',
              overflow: 'hidden',
              marginBottom: '10px'
            }}>
              <div style={{
                width: `${progress.percent}%`,
                height: '100%',
                backgroundColor: 'var(--primary-blue, #2563EB)',
                borderRadius: '999px',
                transition: 'width 0.4s ease-in-out',
              }} />
            </div>

            <p style={{
              margin: 0,
              fontSize: '12px',
              color: 'var(--secondary-text, #64748B)',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}>
              <Loader2 size={13} className="animate-spin" />
              <span>{progress.message}</span>
            </p>
          </div>
        )}

        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? (
            <>
              <Loader2 size={18} className="animate-spin" />
              <span>{progress ? `${progress.percent}% - Menganalisis...` : 'Menganalisis...'}</span>
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
