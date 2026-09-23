import React, { useState, useRef, useEffect } from 'react';
import { UploadCloud, Loader2, CheckCircle2, AlertCircle, X } from 'lucide-react';
import { submitReport } from '../api';

export const ReportPage: React.FC = () => {
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successReportId, setSuccessReportId] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const setUploadedFile = (newFile: File | null) => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(newFile);
    if (newFile && newFile.type.startsWith('image/')) {
      setPreviewUrl(URL.createObjectURL(newFile));
    } else {
      setPreviewUrl(null);
    }
  };

  const fetchImageFromUrl = async (url: string) => {
    try {
      setErrorMessage(null);
      const res = await fetch(url);
      if (!res.ok) throw new Error('Gagal mengunduh gambar');
      const blob = await res.blob();
      if (!blob.type.startsWith('image/')) throw new Error('Bukan file gambar');
      const filename = url.split('/').pop()?.split('?')[0] || 'pasted-image.png';
      setUploadedFile(new File([blob], filename, { type: blob.type }));
    } catch {
      setText((prev) => (prev ? `${prev}\n${url}` : url));
    }
  };

  useEffect(() => {
    const handlePaste = (e: ClipboardEvent) => {
      const target = e.target as HTMLElement;
      const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA';
      const items = e.clipboardData?.items;
      if (!items) return;

      for (let i = 0; i < items.length; i++) {
        if (items[i].type.startsWith('image/')) {
          const blob = items[i].getAsFile();
          if (blob) {
            e.preventDefault();
            const extension = blob.type.split('/')[1] || 'png';
            setUploadedFile(new File([blob], `screenshot-${Date.now()}.${extension}`, { type: blob.type }));
            return;
          }
        }
      }

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
      const droppedUrl = e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain');
      if (droppedUrl && droppedUrl.startsWith('http')) {
        fetchImageFromUrl(droppedUrl.trim());
      }
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
