import React, { useState, useEffect, useRef } from 'react';
import {
  Home,
  LayoutDashboard,
  FileText,
  Building2,
  AlertTriangle,
  ShieldAlert,
  LogOut,
  Plus,
  Trash2,
  Save,
  Bold,
  Italic,
  Heading1,
  Heading2,
  List,
  Code,
  Undo2,
  Redo2,
  CheckCircle,
  Eye,
  EyeOff,
  AlertCircle,
  Lock,
  User,
  Search,
  RefreshCw,
  Check,
  X,
  ChevronsLeft,
  ChevronsRight,
  Menu,
  Pencil,
  Calendar,
  Clock,
  Tag,
  FileSearch,
} from 'lucide-react';
import logoImg from '../assets/logo.png';
import {
  adminLogin,
  adminGetOverview,
  adminGetDetections,
  adminGetReports,
  adminUpdateReportStatus,
  adminGetCompanies,
  adminToggleCompanyFlag,
  adminGetBlacklists,
  adminGetEducationArticles,
  adminCreateEducationArticle,
  adminUpdateEducationArticle,
  adminDeleteEducationArticle,
} from '../api';
import type {
  AdminOverview,
  AdminDetectionRecord,
  AdminReportRecord,
  AdminCompanyRecord,
  AdminBlacklistRecord,
  EducationArticle,
} from '../types';
import { MarkdownRenderer } from './MarkdownRenderer';

interface AdminPageProps {
  onBackToHome: () => void;
}

type AdminTab = 'overview' | 'detections' | 'reports' | 'companies' | 'blacklists' | 'education';

type DetailSelection =
  | { kind: 'detection'; data: AdminDetectionRecord }
  | { kind: 'report'; data: AdminReportRecord }
  | { kind: 'company'; data: AdminCompanyRecord }
  | { kind: 'blacklist'; data: AdminBlacklistRecord }
  | null;

const TAB_META: Record<AdminTab, { title: string; desc: string }> = {
  overview: { title: 'Ringkasan', desc: 'Metrik utama & laporan terbaru yang butuh tindakan' },
  detections: { title: 'Log Deteksi', desc: 'Riwayat analisis risiko — klik baris untuk detail penuh' },
  reports: { title: 'Laporan Aduan', desc: 'Verifikasi laporan masuk — klik baris untuk detail penuh' },
  companies: { title: 'Registri Perusahaan', desc: 'Data legalitas PT — klik baris untuk detail penuh' },
  blacklists: { title: 'Blacklist Intel', desc: 'Nomor & kontak terindikasi — klik baris untuk detail' },
  education: { title: 'Kelola Edukasi', desc: 'Tulis & publikasikan artikel panduan' },
};

function slugify(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)+/g, '')
    .slice(0, 80);
}

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('id-ID', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('id-ID', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
}

export const AdminPage: React.FC<AdminPageProps> = ({ onBackToHome }) => {
  const [token, setToken] = useState<string | null>(() => {
    return typeof window !== 'undefined' ? localStorage.getItem('cepu_admin_token') : null;
  });
  const [adminUser, setAdminUser] = useState<string>(() => {
    return typeof window !== 'undefined' ? localStorage.getItem('cepu_admin_user') || 'Admin' : 'Admin';
  });

  // Login form
  const [usernameInput, setUsernameInput] = useState('');
  const [passwordInput, setPasswordInput] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  // Sidebar
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarMobileOpen, setSidebarMobileOpen] = useState(false);

  const [activeTab, setActiveTab] = useState<AdminTab>('overview');

  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [detections, setDetections] = useState<AdminDetectionRecord[]>([]);
  const [reports, setReports] = useState<AdminReportRecord[]>([]);
  const [companies, setCompanies] = useState<AdminCompanyRecord[]>([]);
  const [blacklists, setBlacklists] = useState<AdminBlacklistRecord[]>([]);
  const [articles, setArticles] = useState<EducationArticle[]>([]);

  const [loadingData, setLoadingData] = useState(false);
  const [dataError, setDataError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const [companySearch, setCompanySearch] = useState('');
  const [reportFilter, setReportFilter] = useState('');
  const [detectionFilter, setDetectionFilter] = useState('');

  // Detail modal
  const [detail, setDetail] = useState<DetailSelection>(null);

  // Education editor
  const [selectedArticleId, setSelectedArticleId] = useState<string | null>(null);
  const [articleTitle, setArticleTitle] = useState('');
  const [articleSlug, setArticleSlug] = useState('');
  const [articleBodyMd, setArticleBodyMd] = useState('');
  const [articleTags, setArticleTags] = useState('');
  const [articlePublished, setArticlePublished] = useState(true);
  const [savingArticle, setSavingArticle] = useState(false);
  const [articleSearch, setArticleSearch] = useState('');
  const [eduViewMode, setEduViewMode] = useState<'split' | 'edit' | 'preview'>('split');
  const [eduModalOpen, setEduModalOpen] = useState(false);

  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);
  const isUndoRedoAction = useRef<boolean>(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Close modal on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setDetail(null);
        setEduModalOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Auto-dismiss success toast
  useEffect(() => {
    if (!actionSuccess) return;
    const t = setTimeout(() => setActionSuccess(null), 4000);
    return () => clearTimeout(t);
  }, [actionSuccess]);

  const handleLogout = () => {
    localStorage.removeItem('cepu_admin_token');
    localStorage.removeItem('cepu_admin_user');
    setToken(null);
    setDetail(null);
  };

  const loadCurrentTabData = async (overrides?: { detection?: string; report?: string; company?: string }) => {
    if (!token) return;
    setLoadingData(true);
    setDataError(null);
    try {
      if (activeTab === 'overview') {
        const [ovData, repData, detData] = await Promise.all([
          adminGetOverview(token),
          adminGetReports(token),
          adminGetDetections(token),
        ]);
        setOverview(ovData);
        setReports(repData.slice(0, 5));
        setDetections(detData.slice(0, 5));
      } else if (activeTab === 'detections') {
        const f = overrides?.detection ?? detectionFilter;
        const data = await adminGetDetections(token, f || undefined);
        setDetections(data);
      } else if (activeTab === 'reports') {
        const f = overrides?.report ?? reportFilter;
        const data = await adminGetReports(token, f || undefined);
        setReports(data);
      } else if (activeTab === 'companies') {
        const q = overrides?.company ?? companySearch;
        const data = await adminGetCompanies(token, q || undefined);
        setCompanies(data);
      } else if (activeTab === 'blacklists') {
        const data = await adminGetBlacklists(token);
        setBlacklists(data);
      } else if (activeTab === 'education') {
        const data = await adminGetEducationArticles();
        setArticles(data);
      }
    } catch (err: any) {
      setDataError(err.message || 'Gagal memuat data dari server.');
      if (err.message && err.message.includes('401')) handleLogout();
    } finally {
      setLoadingData(false);
    }
  };

  useEffect(() => {
    if (!token) return;
    loadCurrentTabData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, activeTab]);

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginLoading(true);
    setLoginError(null);
    try {
      const res = await adminLogin(usernameInput.trim(), passwordInput);
      localStorage.setItem('cepu_admin_token', res.token);
      localStorage.setItem('cepu_admin_user', res.username);
      setToken(res.token);
      setAdminUser(res.username);
    } catch (err: any) {
      setLoginError(err.message || 'Login gagal. Cek username & password.');
    } finally {
      setLoginLoading(false);
    }
  };

  const handleUpdateReport = async (reportId: string, newStatus: string) => {
    if (!token) return;
    try {
      await adminUpdateReportStatus(token, reportId, newStatus);
      setActionSuccess(`Laporan #${reportId.slice(0, 8)} → ${newStatus}`);
      setDetail(null);
      loadCurrentTabData();
    } catch (err: any) {
      alert(err.message || 'Gagal mengupdate laporan.');
    }
  };

  const handleToggleFlag = async (companyId: string, currentFlag: boolean) => {
    if (!token) return;
    try {
      await adminToggleCompanyFlag(token, companyId, !currentFlag);
      setActionSuccess('Status flag perusahaan diperbarui.');
      setDetail(null);
      loadCurrentTabData();
    } catch (err: any) {
      alert(err.message || 'Gagal mengubah status perusahaan.');
    }
  };

  // ---------- Article editor (popup modal) ----------
  const openEditArticle = (art: EducationArticle) => {
    setSelectedArticleId(art.id);
    setArticleTitle(art.title);
    setArticleSlug(art.slug);
    setArticleBodyMd(art.body_md);
    setArticleTags((art.tags || []).join(', '));
    setArticlePublished(art.published);
    setHistory([art.body_md]);
    setHistoryIndex(0);
    setActionSuccess(null);
    setEduModalOpen(true);
  };

  const openNewArticle = () => {
    setSelectedArticleId(null);
    setArticleTitle('');
    setArticleSlug('');
    const tpl = `## Pendahuluan\n\nTuliskan penjelasan edukasi di sini. Fokus pada satu topik agar mudah dipahami.\n\n### Poin penting\n- Poin pertama\n- Poin kedua\n\nGunakan **tebal** untuk penekanan dan \`kode\` bila perlu.`;
    setArticleBodyMd(tpl);
    setArticleTags('');
    setArticlePublished(true);
    setHistory([tpl]);
    setHistoryIndex(0);
    setActionSuccess(null);
    setEduModalOpen(true);
  };

  const closeEduModal = () => setEduModalOpen(false);

  const handleBodyChange = (newText: string) => {
    setArticleBodyMd(newText);
    if (!isUndoRedoAction.current) {
      const next = history.slice(0, historyIndex + 1);
      next.push(newText);
      if (next.length > 80) next.shift();
      setHistory(next);
      setHistoryIndex(next.length - 1);
    }
    isUndoRedoAction.current = false;
  };

  const handleUndo = () => {
    if (historyIndex > 0) {
      isUndoRedoAction.current = true;
      setHistoryIndex(historyIndex - 1);
      setArticleBodyMd(history[historyIndex - 1]);
    }
  };

  const handleRedo = () => {
    if (historyIndex < history.length - 1) {
      isUndoRedoAction.current = true;
      setHistoryIndex(historyIndex + 1);
      setArticleBodyMd(history[historyIndex + 1]);
    }
  };

  const applyFormat = (prefix: string, suffix = '', placeholder = '') => {
    const ta = textareaRef.current;
    if (!ta) return;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const cur = articleBodyMd;
    const sel = cur.substring(start, end) || placeholder;
    const next = cur.substring(0, start) + `${prefix}${sel}${suffix}` + cur.substring(end);
    handleBodyChange(next);
    setTimeout(() => {
      ta.focus();
      ta.setSelectionRange(start + prefix.length, start + prefix.length + sel.length);
    }, 10);
  };

  const handleTitleChange = (v: string) => {
    setArticleTitle(v);
    if (!selectedArticleId) setArticleSlug(slugify(v));
  };

  const handleSaveArticle = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!articleTitle.trim() || !articleBodyMd.trim()) {
      alert('Judul dan isi artikel tidak boleh kosong.');
      return;
    }
    try {
      setSavingArticle(true);
      const tags = articleTags.split(',').map((t) => t.trim()).filter(Boolean);
      const payload = {
        title: articleTitle.trim(),
        slug: articleSlug.trim() || slugify(articleTitle),
        body_md: articleBodyMd,
        tags,
        published: articlePublished,
      };
      if (selectedArticleId) {
        await adminUpdateEducationArticle(selectedArticleId, payload);
        setActionSuccess('Artikel berhasil diperbarui.');
      } else {
        const created = await adminCreateEducationArticle(payload);
        setSelectedArticleId(created.id);
        setArticleSlug(created.slug);
        setActionSuccess('Artikel baru berhasil dibuat.');
      }
      const data = await adminGetEducationArticles();
      setArticles(data);
      setEduModalOpen(false);
    } catch (err: any) {
      alert(err.message || 'Gagal menyimpan artikel.');
    } finally {
      setSavingArticle(false);
    }
  };

  const handleDeleteArticle = async () => {
    if (!selectedArticleId) return;
    if (!confirm('Hapus artikel ini secara permanen?')) return;
    try {
      setSavingArticle(true);
      await adminDeleteEducationArticle(selectedArticleId);
      setActionSuccess('Artikel telah dihapus.');
      setEduModalOpen(false);
      setSelectedArticleId(null);
      const data = await adminGetEducationArticles();
      setArticles(data);
    } catch (err: any) {
      alert(err.message || 'Gagal menghapus artikel.');
    } finally {
      setSavingArticle(false);
    }
  };

  const filteredArticles = articles.filter((a) => {
    const q = articleSearch.trim().toLowerCase();
    if (!q) return true;
    return (
      a.title.toLowerCase().includes(q) ||
      a.slug.toLowerCase().includes(q) ||
      (a.tags || []).join(' ').toLowerCase().includes(q)
    );
  });

  const wordCount = articleBodyMd.trim() ? articleBodyMd.trim().split(/\s+/).length : 0;

  const switchTab = (t: AdminTab) => {
    setActiveTab(t);
    setDetail(null);
    setDataError(null);
    setSidebarMobileOpen(false);
  };

  // ================= LOGIN =================
  if (!token) {
    return (
      <div className="admin-login-wrapper">
        <div className="admin-login-card">
          <div className="admin-login-brand">
            <img src={logoImg} alt="CePu Logo" className="admin-login-logo" />
            <h1>CePu Admin Portal</h1>
            <p>Masuk untuk mengelola data deteksi, laporan, dan konten</p>
          </div>

          {loginError && (
            <div className="alert-box error admin-alert">
              <AlertCircle size={18} />
              <span>{loginError}</span>
            </div>
          )}

          <form onSubmit={handleLoginSubmit} className="admin-login-form">
            <div className="form-group">
              <label className="form-label admin-label">
                <User size={15} />
                <span>Username Admin</span>
              </label>
              <input
                type="text"
                className="form-input"
                placeholder="admin"
                value={usernameInput}
                onChange={(e) => setUsernameInput(e.target.value)}
                required
                autoComplete="username"
              />
            </div>

            <div className="form-group">
              <label className="form-label admin-label">
                <Lock size={15} />
                <span>Password</span>
              </label>
              <div className="password-field">
                <input
                  type={showPassword ? 'text' : 'password'}
                  className="form-input password-input"
                  placeholder="••••••••"
                  value={passwordInput}
                  onChange={(e) => setPasswordInput(e.target.value)}
                  required
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  className="password-toggle"
                  onClick={() => setShowPassword((v) => !v)}
                  title={showPassword ? 'Sembunyikan password' : 'Tampilkan password'}
                  aria-label={showPassword ? 'Sembunyikan password' : 'Tampilkan password'}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button type="submit" className="btn-primary admin-login-submit" disabled={loginLoading}>
              {loginLoading ? 'Memverifikasi...' : 'Masuk ke Portal Admin'}
            </button>

            <button type="button" className="admin-back-link" onClick={onBackToHome}>
              ← Kembali ke Beranda Utama
            </button>
          </form>
        </div>
      </div>
    );
  }

  // ================= DASHBOARD =================
  return (
    <div className={`admin-app-layout ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      {sidebarMobileOpen && (
        <div className="admin-sidebar-overlay" onClick={() => setSidebarMobileOpen(false)} />
      )}

      {/* SIDEBAR */}
      <aside className={`admin-portal-sidebar ${sidebarMobileOpen ? 'mobile-open' : ''}`}>
        <div className="sidebar-top-row">
          <div className="sidebar-brand-box" onClick={onBackToHome} title="Klik untuk kembali ke website">
            <img src={logoImg} alt="CePu Logo" className="sidebar-logo-img" />
            {!sidebarCollapsed && (
              <div className="sidebar-brand-text">
                <span className="brand-title">CePu Admin</span>
              </div>
            )}
          </div>
          <button
            className="sidebar-collapse-icon"
            onClick={() => setSidebarCollapsed((v) => !v)}
            title={sidebarCollapsed ? 'Perluas sidebar' : 'Ciutkan sidebar'}
            aria-label={sidebarCollapsed ? 'Perluas sidebar' : 'Ciutkan sidebar'}
          >
            {sidebarCollapsed ? <ChevronsRight size={17} /> : <ChevronsLeft size={17} />}
          </button>
        </div>

        <nav className="sidebar-nav-list">
          <button className={`sidebar-nav-btn ${activeTab === 'overview' ? 'active' : ''}`} onClick={() => switchTab('overview')} title="Overview & Stats">
            <LayoutDashboard size={18} />
            {!sidebarCollapsed && <span>Overview</span>}
          </button>
          <button className={`sidebar-nav-btn ${activeTab === 'detections' ? 'active' : ''}`} onClick={() => switchTab('detections')} title="Log Deteksi">
            <FileSearch size={18} />
            {!sidebarCollapsed && <span>Log Deteksi</span>}
          </button>
          <button className={`sidebar-nav-btn ${activeTab === 'reports' ? 'active' : ''}`} onClick={() => switchTab('reports')} title="Laporan Aduan">
            <AlertTriangle size={18} />
            {!sidebarCollapsed && <span>Laporan</span>}
          </button>
          <button className={`sidebar-nav-btn ${activeTab === 'companies' ? 'active' : ''}`} onClick={() => switchTab('companies')} title="Registri PT">
            <Building2 size={18} />
            {!sidebarCollapsed && <span>Perusahaan</span>}
          </button>
          <button className={`sidebar-nav-btn ${activeTab === 'blacklists' ? 'active' : ''}`} onClick={() => switchTab('blacklists')} title="Intel Blacklist">
            <ShieldAlert size={18} />
            {!sidebarCollapsed && <span>Blacklist</span>}
          </button>
          <button className={`sidebar-nav-btn ${activeTab === 'education' ? 'active' : ''}`} onClick={() => switchTab('education')} title="Kelola Edukasi">
            <FileText size={18} />
            {!sidebarCollapsed && <span>Edukasi</span>}
          </button>
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-user-box">
            <div className="sidebar-user-info">
              <div className="user-avatar-badge">{adminUser.charAt(0).toUpperCase()}</div>
              {!sidebarCollapsed && (
                <div className="user-meta">
                  <div className="user-name">{adminUser}</div>
                  <div className="user-role">Superadmin</div>
                </div>
              )}
            </div>
            <button className="sidebar-logout-btn" onClick={handleLogout} title="Keluar">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      {/* MAIN */}
      <main className="admin-portal-content">
        <div className="admin-content-header">
          <div className="admin-header-left">
            <button className="icon-btn mobile-menu-btn" onClick={() => setSidebarMobileOpen(true)} title="Menu">
              <Menu size={20} />
            </button>
            <div>
              <h2>{TAB_META[activeTab].title}</h2>
              <p>{TAB_META[activeTab].desc}</p>
            </div>
          </div>
          <div className="admin-header-actions">
            <button className="btn-secondary btn-sm" onClick={() => loadCurrentTabData()} disabled={loadingData}>
              <RefreshCw size={15} className={loadingData ? 'spin-icon' : ''} />
              <span>Segarkan</span>
            </button>
            <button className="btn-secondary btn-sm" onClick={onBackToHome}>
              <Home size={15} />
              <span className="hide-sm">Lihat Web</span>
            </button>
          </div>
        </div>

        {actionSuccess && (
          <div className="alert-box success admin-alert">
            <div className="alert-left">
              <CheckCircle size={18} />
              <span>{actionSuccess}</span>
            </div>
            <X size={16} className="alert-close" onClick={() => setActionSuccess(null)} />
          </div>
        )}
        {dataError && (
          <div className="alert-box error admin-alert">
            <AlertCircle size={18} />
            <span>{dataError}</span>
          </div>
        )}

        {loadingData && (
          <div className="admin-loading-bar">
            <RefreshCw size={16} className="spin-icon" />
            <span>Memuat data...</span>
          </div>
        )}

        {/* OVERVIEW */}
        {activeTab === 'overview' && overview && (
          <div className="admin-stack">
            <div className="admin-stats-grid">
              <div className="stat-metric-card">
                <div className="stat-top"><span className="stat-label">Total Deteksi</span><FileSearch size={18} className="stat-ic blue" /></div>
                <div className="stat-number">{overview.detections}</div>
                <div className="stat-desc">Analisis via Web & WA</div>
              </div>
              <div className="stat-metric-card">
                <div className="stat-top"><span className="stat-label">Laporan Masuk</span><AlertTriangle size={18} className="stat-ic red" /></div>
                <div className="stat-number">{overview.reports}</div>
                <div className="stat-desc danger">{overview.pending_reports} menunggu review</div>
              </div>
              <div className="stat-metric-card">
                <div className="stat-top"><span className="stat-label">Perusahaan</span><Building2 size={18} className="stat-ic green" /></div>
                <div className="stat-number">{overview.companies}</div>
                <div className="stat-desc">Cache CompanyHouse.id</div>
              </div>
              <div className="stat-metric-card">
                <div className="stat-top"><span className="stat-label">Blacklist Intel</span><ShieldAlert size={18} className="stat-ic amber" /></div>
                <div className="stat-number">{overview.blacklists}</div>
                <div className="stat-desc">{overview.articles} artikel edukasi live</div>
              </div>
            </div>

            <div className="admin-table-container">
              <div className="table-head">
                <span className="table-title">Laporan terbaru perlu tindakan</span>
                <button className="link-btn" onClick={() => switchTab('reports')}>Lihat semua →</button>
              </div>
              <div className="table-scroll">
                <table className="admin-data-table">
                  <thead>
                    <tr><th>Tanggal</th><th>Kontak terlapor</th><th>Perusahaan</th><th>Status</th><th></th></tr>
                  </thead>
                  <tbody>
                    {reports.length === 0 ? (
                      <tr><td colSpan={5} className="empty-cell">Tidak ada laporan.</td></tr>
                    ) : reports.map((r) => (
                      <tr key={r.id} className="clickable-row" onClick={() => setDetail({ kind: 'report', data: r })}>
                        <td className="nowrap">{formatDate(r.created_at)}</td>
                        <td>{r.suspect_phone || r.suspect_email || '-'}</td>
                        <td>{r.suspect_company || '-'}</td>
                        <td><span className={`status-pill ${r.status}`}>{r.status.replace('_', ' ')}</span></td>
                        <td><span className="row-hint"><Eye size={15} /> Detail</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* DETECTIONS */}
        {activeTab === 'detections' && (
          <div className="admin-table-container">
            <div className="table-head wrap">
              <span className="table-title">Log deteksi ({detections.length}) <span className="table-hint">— klik baris untuk detail</span></span>
              <select
                className="form-input form-input-sm"
                value={detectionFilter}
                onChange={(e) => {
                  const v = e.target.value;
                  setDetectionFilter(v);
                  loadCurrentTabData({ detection: v });
                }}
              >
                <option value="">Semua kategori</option>
                <option value="tinggi">Tinggi</option>
                <option value="sedang">Sedang</option>
                <option value="rendah">Rendah</option>
              </select>
            </div>
            <div className="table-scroll">
              <table className="admin-data-table">
                <thead>
                  <tr><th>Waktu</th><th>Channel</th><th>Skor</th><th>Kategori</th><th>Cuplikan teks</th><th></th></tr>
                </thead>
                <tbody>
                  {detections.length === 0 ? (
                    <tr><td colSpan={6} className="empty-cell">Belum ada log deteksi.</td></tr>
                  ) : detections.map((d) => (
                    <tr key={d.id} className="clickable-row" onClick={() => setDetail({ kind: 'detection', data: d })}>
                      <td className="nowrap">{formatDateTime(d.created_at)}</td>
                      <td><span className="channel-badge">{d.channel}</span></td>
                      <td><strong>{(d.risk_score ?? 0).toFixed(2)}</strong></td>
                      <td><span className={`category-tag ${d.category || 'sedang'}`}>{d.category || '—'}</span></td>
                      <td className="truncate-cell">{d.text_input || d.ocr_text || '(tanpa teks)'}</td>
                      <td><span className="row-hint"><Eye size={15} /></span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* REPORTS */}
        {activeTab === 'reports' && (
          <div className="admin-table-container">
            <div className="table-head wrap">
              <span className="table-title">Laporan masuk ({reports.length}) <span className="table-hint">— klik baris untuk detail</span></span>
              <select
                className="form-input form-input-sm"
                value={reportFilter}
                onChange={(e) => {
                  const v = e.target.value;
                  setReportFilter(v);
                  loadCurrentTabData({ report: v });
                }}
              >
                <option value="">Semua status</option>
                <option value="pending">Pending</option>
                <option value="verified_scam">Verified Scam</option>
                <option value="false_alarm">False Alarm</option>
              </select>
            </div>
            <div className="table-scroll">
              <table className="admin-data-table">
                <thead>
                  <tr><th>Tanggal</th><th>Kontak terduga</th><th>Perusahaan</th><th>Modus</th><th>Status</th><th></th></tr>
                </thead>
                <tbody>
                  {reports.length === 0 ? (
                    <tr><td colSpan={6} className="empty-cell">Tidak ada laporan.</td></tr>
                  ) : reports.map((r) => (
                    <tr key={r.id} className="clickable-row" onClick={() => setDetail({ kind: 'report', data: r })}>
                      <td>
                        <div className="cell-main">{formatDate(r.created_at)}</div>
                        <div className="cell-sub">#{r.id.slice(0, 8)}</div>
                      </td>
                      <td>
                        {r.suspect_phone && <div className="cell-main">{r.suspect_phone}</div>}
                        {r.suspect_email && <div className="cell-sub">{r.suspect_email}</div>}
                        {!r.suspect_phone && !r.suspect_email && <span className="muted">—</span>}
                      </td>
                      <td>{r.suspect_company || <span className="muted">—</span>}</td>
                      <td className="truncate-cell">{r.message_raw || '(tanpa pesan)'}</td>
                      <td><span className={`status-pill ${r.status}`}>{r.status.replace('_', ' ')}</span></td>
                      <td><span className="row-hint"><Eye size={15} /></span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* COMPANIES */}
        {activeTab === 'companies' && (
          <div className="admin-table-container">
            <div className="table-head wrap">
              <span className="table-title">Registri perusahaan ({companies.length})</span>
              <div className="table-tools">
                <input
                  type="text"
                  className="form-input form-input-sm search-input"
                  placeholder="Cari nama PT..."
                  value={companySearch}
                  onChange={(e) => setCompanySearch(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && loadCurrentTabData()}
                />
                <button className="btn-primary btn-sm" onClick={() => loadCurrentTabData()}>
                  <Search size={14} />
                </button>
              </div>
            </div>
            <div className="table-scroll">
              <table className="admin-data-table">
                <thead>
                  <tr><th>Nama resmi</th><th>No. AHU</th><th>Legalitas</th><th>Flag</th><th>Sumber</th><th></th></tr>
                </thead>
                <tbody>
                  {companies.length === 0 ? (
                    <tr><td colSpan={6} className="empty-cell">Tidak ada data perusahaan.</td></tr>
                  ) : companies.map((c) => (
                    <tr key={c.id} className="clickable-row" onClick={() => setDetail({ kind: 'company', data: c })}>
                      <td className="cell-main">{c.legal_name}</td>
                      <td className="mono">{c.ahu_no || '—'}</td>
                      <td><span className={c.registered ? 'ok-text' : 'bad-text'}>{c.registered ? 'Terdaftar' : 'Belum ada data'}</span></td>
                      <td>{c.is_flagged_scam ? <span className="status-pill verified_scam">Flagged</span> : <span className="muted">Aman</span>}</td>
                      <td><span className="source-tag">{c.source}</span></td>
                      <td><span className="row-hint"><Eye size={15} /></span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* BLACKLISTS */}
        {activeTab === 'blacklists' && (
          <div className="admin-table-container">
            <div className="table-head">
              <span className="table-title">Blacklist intel ({blacklists.length}) <span className="table-hint">— klik baris untuk detail</span></span>
            </div>
            <div className="table-scroll">
              <table className="admin-data-table">
                <thead>
                  <tr><th>Tipe</th><th>Nilai (masked)</th><th>Laporan</th><th>Terakhir</th><th>Status</th><th></th></tr>
                </thead>
                <tbody>
                  {blacklists.length === 0 ? (
                    <tr><td colSpan={6} className="empty-cell">Belum ada entri blacklist.</td></tr>
                  ) : blacklists.map((b) => (
                    <tr key={b.id} className="clickable-row" onClick={() => setDetail({ kind: 'blacklist', data: b })}>
                      <td><span className="channel-badge">{b.kind}</span></td>
                      <td className="mono cell-main">{b.value_masked}</td>
                      <td><strong>{b.report_count}x</strong></td>
                      <td className="nowrap">{formatDateTime(b.last_reported_at)}</td>
                      <td><span className={b.active ? 'bad-text' : 'muted'}>{b.active ? 'Aktif (diblokir)' : 'Non-aktif'}</span></td>
                      <td><span className="row-hint"><Eye size={15} /></span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* EDUCATION — records table */}
        {activeTab === 'education' && (
          <div className="admin-stack">
            <div className="admin-table-container">
              <div className="table-head wrap">
                <span className="table-title">Artikel edukasi ({filteredArticles.length}) <span className="table-hint">— klik baris untuk mengedit</span></span>
                <div className="table-tools">
                  <input
                    type="text"
                    className="form-input form-input-sm search-input"
                    placeholder="Cari judul, slug, tag..."
                    value={articleSearch}
                    onChange={(e) => setArticleSearch(e.target.value)}
                  />
                  <button className="btn-primary btn-sm" onClick={openNewArticle}>
                    <Plus size={14} />
                    <span>Tulis Artikel</span>
                  </button>
                </div>
              </div>
              <div className="table-scroll">
                <table className="admin-data-table">
                  <thead>
                    <tr><th>Judul</th><th>Slug</th><th>Tags</th><th>Status</th><th></th></tr>
                  </thead>
                  <tbody>
                    {filteredArticles.length === 0 ? (
                      <tr><td colSpan={5} className="empty-cell">Belum ada artikel. Klik “Tulis Artikel” untuk membuat yang baru.</td></tr>
                    ) : filteredArticles.map((art) => (
                      <tr key={art.id} className="clickable-row" onClick={() => openEditArticle(art)}>
                        <td className="cell-main">{art.title}</td>
                        <td className="mono muted">/{art.slug}</td>
                        <td>
                          {(art.tags || []).length === 0 ? (
                            <span className="muted">—</span>
                          ) : (
                            <div className="tag-row">
                              {(art.tags || []).slice(0, 3).map((t, i) => (
                                <span key={i} className="source-tag">{t}</span>
                              ))}
                              {(art.tags || []).length > 3 && (
                                <span className="muted">+{(art.tags || []).length - 3}</span>
                              )}
                            </div>
                          )}
                        </td>
                        <td>
                          <span className={`mini-badge ${art.published ? 'live' : 'draft'}`}>
                            {art.published ? 'Live' : 'Draft'}
                          </span>
                        </td>
                        <td>
                          <button
                            className="btn-secondary btn-sm btn-edit"
                            onClick={(e) => { e.stopPropagation(); openEditArticle(art); }}
                          >
                            <Pencil size={14} />
                            <span>Edit</span>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {eduModalOpen && (
              <div className="admin-modal-overlay" onClick={closeEduModal}>
                <div className="admin-modal-card wide" onClick={(e) => e.stopPropagation()}>
                  <div className="admin-modal-head">
                    <div>
                      <h3>{selectedArticleId ? 'Edit artikel' : 'Tulis artikel baru'}</h3>
                      <p className="modal-sub">Tulis dengan Markdown — pratinjau tampil langsung di bawah.</p>
                    </div>
                    <button className="icon-btn" onClick={closeEduModal} title="Tutup">
                      <X size={18} />
                    </button>
                  </div>
                  <form onSubmit={handleSaveArticle} className="edu-form edu-modal-form">
                <div className="edu-form-head">
                  <div>
                    <p className="muted" style={{ margin: 0 }}>Lengkapi metadata, tulis isi dengan Markdown, lalu pratinjau sebelum menyimpan.</p>
                  </div>
                  <label className="publish-switch">
                    <input
                      type="checkbox"
                      checked={articlePublished}
                      onChange={(e) => setArticlePublished(e.target.checked)}
                    />
                    <span className="switch-ui" />
                    <span className="switch-label">{articlePublished ? 'Published' : 'Draft'}</span>
                  </label>
                </div>

                <div className="edu-meta-grid">
                  <div className="form-group">
                    <label className="form-label">Judul artikel</label>
                    <input
                      type="text"
                      className="form-input"
                      placeholder="cth: Waspada tawaran gaji fantastis"
                      value={articleTitle}
                      onChange={(e) => handleTitleChange(e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Slug URL</label>
                    <input
                      type="text"
                      className="form-input mono"
                      placeholder="otomatis-dari-judul"
                      value={articleSlug}
                      onChange={(e) => setArticleSlug(slugify(e.target.value))}
                    />
                  </div>
                  <div className="form-group full">
                    <label className="form-label">Tags <span className="label-hint">(pisahkan dengan koma)</span></label>
                    <input
                      type="text"
                      className="form-input"
                      placeholder="tips, waspada, gaji"
                      value={articleTags}
                      onChange={(e) => setArticleTags(e.target.value)}
                    />
                  </div>
                </div>

                <div className="edu-view-toggle">
                  <div className="seg-control">
                    {(['edit', 'split', 'preview'] as const).map((m) => (
                      <button
                        key={m}
                        type="button"
                        className={`seg-btn ${eduViewMode === m ? 'active' : ''}`}
                        onClick={() => setEduViewMode(m)}
                      >
                        {m === 'edit' ? 'Tulis' : m === 'split' ? 'Split' : 'Pratinjau'}
                      </button>
                    ))}
                  </div>
                  <span className="word-count">{wordCount} kata • {articleBodyMd.length} karakter</span>
                </div>

                <div className="admin-editor-toolbar">
                  <button type="button" className="toolbar-btn" title="Undo" onClick={handleUndo} disabled={historyIndex <= 0}>
                    <Undo2 size={16} />
                  </button>
                  <button type="button" className="toolbar-btn" title="Redo" onClick={handleRedo} disabled={historyIndex >= history.length - 1}>
                    <Redo2 size={16} />
                  </button>
                  <div className="toolbar-divider" />
                  <button type="button" className="toolbar-btn" title="Tebal" onClick={() => applyFormat('**', '**', 'tebal')}>
                    <Bold size={16} />
                  </button>
                  <button type="button" className="toolbar-btn" title="Miring" onClick={() => applyFormat('*', '*', 'miring')}>
                    <Italic size={16} />
                  </button>
                  <button type="button" className="toolbar-btn" title="Heading" onClick={() => applyFormat('## ', '', 'Subjudul')}>
                    <Heading1 size={16} />
                  </button>
                  <button type="button" className="toolbar-btn" title="Sub-heading" onClick={() => applyFormat('### ', '', 'Poin')}>
                    <Heading2 size={16} />
                  </button>
                  <button type="button" className="toolbar-btn" title="List" onClick={() => applyFormat('- ', '', 'Poin')}>
                    <List size={16} />
                  </button>
                  <button type="button" className="toolbar-btn" title="Kode" onClick={() => applyFormat('`', '`', 'kode')}>
                    <Code size={16} />
                  </button>
                </div>

                <div className={`admin-split-view mode-${eduViewMode}`}>
                  {(eduViewMode === 'edit' || eduViewMode === 'split') && (
                    <div className="admin-editor-column">
                      <div className="split-column-header"><FileText size={14} /><span>Markdown</span></div>
                      <textarea
                        ref={textareaRef}
                        className="admin-textarea"
                        value={articleBodyMd}
                        onChange={(e) => handleBodyChange(e.target.value)}
                        placeholder="Tulis isi artikel dengan format Markdown..."
                        required
                      />
                    </div>
                  )}
                  {(eduViewMode === 'preview' || eduViewMode === 'split') && (
                    <div className="admin-preview-column">
                      <div className="split-column-header"><Eye size={14} /><span>Pratinjau live</span></div>
                      <div className="admin-preview-content">
                        <h1 className="preview-title">{articleTitle || 'Judul artikel'}</h1>
                        <div className="preview-meta">
                          <span><Calendar size={12} /> {new Date().toLocaleDateString('id-ID')}</span>
                          <span><Tag size={12} /> {articleTags || 'tanpa tag'}</span>
                        </div>
                        {articleBodyMd.trim()
                          ? <MarkdownRenderer content={articleBodyMd} />
                          : <p className="muted">Belum ada isi — mulai mengetik di editor.</p>}
                      </div>
                    </div>
                  )}
                </div>

                <div className="admin-footer-bar">
                  <div>
                    {selectedArticleId && (
                      <button type="button" className="btn-danger-ghost btn-sm" onClick={handleDeleteArticle} disabled={savingArticle}>
                        <Trash2 size={15} />
                        <span>Hapus</span>
                      </button>
                    )}
                  </div>
                  <div className="modal-actions">
                    <button type="button" className="btn-secondary btn-sm" onClick={closeEduModal}>
                      Batal
                    </button>
                    <button type="submit" className="btn-primary btn-sm" disabled={savingArticle}>
                      <Save size={16} />
                      <span>{savingArticle ? 'Menyimpan...' : selectedArticleId ? 'Simpan perubahan' : 'Terbitkan artikel'}</span>
                    </button>
                  </div>
                </div>
                  </form>
                </div>
              </div>
            )}
          </div>
        )}
      </main>

      {/* DETAIL MODAL */}
      {detail && (
        <div className="admin-modal-overlay" onClick={() => setDetail(null)}>
          <div className="admin-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="admin-modal-head">
              <div>
                <h3>
                  {detail.kind === 'detection' && 'Detail Deteksi'}
                  {detail.kind === 'report' && 'Detail Laporan'}
                  {detail.kind === 'company' && 'Detail Perusahaan'}
                  {detail.kind === 'blacklist' && 'Detail Blacklist'}
                </h3>
                <p className="modal-sub mono">
                  {detail.kind === 'detection' && `#${detail.data.id.slice(0, 12)}`}
                  {detail.kind === 'report' && `#${detail.data.id.slice(0, 12)}`}
                  {detail.kind === 'company' && `${detail.data.legal_name}`}
                  {detail.kind === 'blacklist' && `${detail.data.kind} • ${detail.data.value_masked}`}
                </p>
              </div>
              <button className="icon-btn" onClick={() => setDetail(null)} title="Tutup">
                <X size={18} />
              </button>
            </div>

            <div className="admin-modal-body">
              {detail.kind === 'detection' && (
                <>
                  <div className="detail-grid">
                    <div className="detail-item"><span>Waktu</span><strong>{formatDateTime(detail.data.created_at)}</strong></div>
                    <div className="detail-item"><span>Channel</span><strong><span className="channel-badge">{detail.data.channel}</span></strong></div>
                    <div className="detail-item"><span>Skor risiko</span><strong>{(detail.data.risk_score ?? 0).toFixed(3)}</strong></div>
                    <div className="detail-item"><span>Kategori</span><strong><span className={`category-tag ${detail.data.category || 'sedang'}`}>{detail.data.category || '—'}</span></strong></div>
                    <div className="detail-item"><span>P-BERT</span><strong>{detail.data.p_bert ?? '—'}</strong></div>
                    <div className="detail-item"><span>V-Company</span><strong>{detail.data.v_company ?? '—'}</strong></div>
                    <div className="detail-item"><span>V-Phone</span><strong>{detail.data.v_phone ?? '—'}</strong></div>
                    <div className="detail-item"><span>V-Email</span><strong>{detail.data.v_email ?? '—'}</strong></div>
                    <div className="detail-item"><span>Model</span><strong className="mono">{detail.data.model_version || '—'}</strong></div>
                    <div className="detail-item"><span>Waktu proses</span><strong>{detail.data.processing_ms ?? '—'} ms</strong></div>
                  </div>
                  <div className="detail-block">
                    <h4>Teks input</h4>
                    <p className="detail-text">{detail.data.text_input || '(kosong)'}</p>
                  </div>
                  {detail.data.ocr_text && (
                    <div className="detail-block">
                      <h4>Hasil OCR</h4>
                      <p className="detail-text">{detail.data.ocr_text}</p>
                    </div>
                  )}
                  {!!detail.data.reasons?.length && (
                    <div className="detail-block">
                      <h4>Alasan ({detail.data.reasons.length})</h4>
                      <ul className="detail-list">
                        {detail.data.reasons.map((r, i) => <li key={i}>{r}</li>)}
                      </ul>
                    </div>
                  )}
                  {!!detail.data.degraded_sources?.length && (
                    <div className="detail-block">
                      <h4>Sumber terdegradasi</h4>
                      <div className="tag-row">
                        {detail.data.degraded_sources.map((s, i) => <span key={i} className="source-tag">{s}</span>)}
                      </div>
                    </div>
                  )}
                </>
              )}

              {detail.kind === 'report' && (
                <>
                  <div className="detail-grid">
                    <div className="detail-item"><span>Dibuat</span><strong>{formatDateTime(detail.data.created_at)}</strong></div>
                    <div className="detail-item"><span>Channel</span><strong><span className="channel-badge">{detail.data.channel}</span></strong></div>
                    <div className="detail-item"><span>Status</span><strong><span className={`status-pill ${detail.data.status}`}>{detail.data.status.replace('_', ' ')}</span></strong></div>
                    <div className="detail-item"><span>Reviewer</span><strong>{detail.data.reviewer || '—'}</strong></div>
                  </div>
                  <div className="detail-grid">
                    <div className="detail-item"><span>No. terduga</span><strong>{detail.data.suspect_phone || '—'}</strong></div>
                    <div className="detail-item"><span>Email terduga</span><strong className="break">{detail.data.suspect_email || '—'}</strong></div>
                    <div className="detail-item"><span>Perusahaan</span><strong>{detail.data.suspect_company || '—'}</strong></div>
                    <div className="detail-item"><span>Kontak pelapor</span><strong className="break">{detail.data.contact_optional || '—'}</strong></div>
                  </div>
                  <div className="detail-block">
                    <h4>Isi pesan / modus</h4>
                    <p className="detail-text">{detail.data.message_raw || '(tidak ada pesan)'}</p>
                  </div>
                  {detail.data.screenshot_path && (
                    <div className="detail-block">
                      <h4>Lampiran</h4>
                      <p className="mono break">{detail.data.screenshot_path}</p>
                    </div>
                  )}
                  {detail.data.note && (
                    <div className="detail-block">
                      <h4>Catatan reviewer</h4>
                      <p className="detail-text">{detail.data.note}</p>
                    </div>
                  )}
                  <div className="modal-actions">
                    <button className="btn-action-verify" onClick={() => handleUpdateReport(detail.data.id, 'verified_scam')}>
                      <Check size={14} /> Tandai Scam
                    </button>
                    <button className="btn-action-dismiss" onClick={() => handleUpdateReport(detail.data.id, 'false_alarm')}>
                      <X size={14} /> False Alarm
                    </button>
                    <button className="btn-secondary btn-sm" onClick={() => handleUpdateReport(detail.data.id, 'pending')}>
                      <Clock size={14} /> Pending
                    </button>
                  </div>
                </>
              )}

              {detail.kind === 'company' && (
                <>
                  <div className="detail-grid">
                    <div className="detail-item full"><span>Nama resmi</span><strong>{detail.data.legal_name}</strong></div>
                    <div className="detail-item"><span>Nama normalisasi</span><strong className="mono">{detail.data.name_norm}</strong></div>
                    <div className="detail-item"><span>No. AHU</span><strong className="mono">{detail.data.ahu_no || '—'}</strong></div>
                    <div className="detail-item"><span>Terdaftar</span><strong className={detail.data.registered ? 'ok-text' : 'bad-text'}>{detail.data.registered ? 'Ya' : 'Tidak'}</strong></div>
                    <div className="detail-item"><span>Flag scam</span><strong>{detail.data.is_flagged_scam ? 'Ya — flagged' : 'Tidak'}</strong></div>
                    <div className="detail-item"><span>Sumber</span><strong><span className="source-tag">{detail.data.source}</span></strong></div>
                    <div className="detail-item"><span>Diperbarui</span><strong>{formatDateTime(detail.data.updated_at)}</strong></div>
                  </div>
                  <div className="modal-actions">
                    <button
                      className={detail.data.is_flagged_scam ? 'btn-secondary btn-sm' : 'btn-danger-ghost btn-sm'}
                      onClick={() => handleToggleFlag(detail.data.id, detail.data.is_flagged_scam)}
                    >
                      {detail.data.is_flagged_scam ? 'Cabut flag scam' : 'Tandai sebagai scam'}
                    </button>
                  </div>
                </>
              )}

              {detail.kind === 'blacklist' && (
                <>
                  <div className="detail-grid">
                    <div className="detail-item"><span>Tipe</span><strong><span className="channel-badge">{detail.data.kind}</span></strong></div>
                    <div className="detail-item"><span>Status</span><strong className={detail.data.active ? 'bad-text' : 'muted'}>{detail.data.active ? 'Aktif (diblokir)' : 'Non-aktif'}</strong></div>
                    <div className="detail-item"><span>Nilai masked</span><strong className="mono">{detail.data.value_masked}</strong></div>
                    <div className="detail-item"><span>Jumlah laporan</span><strong>{detail.data.report_count}x</strong></div>
                    <div className="detail-item full"><span>Terakhir dilaporkan</span><strong>{formatDateTime(detail.data.last_reported_at)}</strong></div>
                  </div>
                  {!!detail.data.sources?.length && (
                    <div className="detail-block">
                      <h4>Sumber</h4>
                      <div className="tag-row">
                        {detail.data.sources.map((s, i) => <span key={i} className="source-tag">{s}</span>)}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
