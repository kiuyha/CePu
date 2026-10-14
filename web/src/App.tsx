import { useState, useEffect } from 'react';
import { 
  Home, 
  Search, 
  BookOpen, 
  Flag, 
  Moon, 
  Sun, 
  Menu,
  X 
} from 'lucide-react';
import logoImg from './assets/logo.png';
import { LandingPage } from './components/LandingPage';
import { DetectPage } from './components/DetectPage';
import { EducationPage } from './components/EducationPage';
import { ReportPage } from './components/ReportPage';
import { AdminPage } from './components/AdminPage';

type Tab = 'home' | 'detect' | 'education' | 'report';

export function App() {
  const [activeTab, setActiveTab] = useState<Tab>('home');
  const [isAdminPath, setIsAdminPath] = useState<boolean>(() => {
    return typeof window !== 'undefined' && window.location.pathname.startsWith('/admin');
  });
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  useEffect(() => {
    const handlePopState = () => {
      setIsAdminPath(window.location.pathname.startsWith('/admin'));
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);
  
  // Theme state: defaults to system preference
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    if (typeof window !== 'undefined' && window.matchMedia) {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    return 'light';
  });

  // Listen to system theme change automatically
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = (e: MediaQueryListEvent) => {
      setTheme(e.matches ? 'dark' : 'light');
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, []);

  // Update HTML data-theme attribute
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light');
  };

  const handleNavigate = (tab: Tab) => {
    if (isAdminPath) {
      window.history.pushState({}, '', '/');
      setIsAdminPath(false);
    }
    setActiveTab(tab);
    setIsDrawerOpen(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className={`app-container ${isAdminPath ? 'admin-mode' : ''}`}>
      {/* Top Navbar (Disembunyikan saat di halaman admin) */}
      {!isAdminPath && (
        <header className="navbar">
          <div className="navbar-inner">
            <div className="navbar-brand" onClick={() => handleNavigate('home')}>
              <img 
                src={logoImg} 
                alt="CePu Logo" 
                className="brand-logo-img"
              />
              <span className="logo-text">CePu</span>
            </div>

            {/* Desktop Navigation Links */}
            <nav className="desktop-nav-links">
              <button 
                className={`desktop-nav-link ${activeTab === 'home' ? 'active' : ''}`}
                onClick={() => handleNavigate('home')}
              >
                <Home size={18} />
                <span>Beranda</span>
              </button>
              <button 
                className={`desktop-nav-link ${activeTab === 'detect' ? 'active' : ''}`}
                onClick={() => handleNavigate('detect')}
              >
                <Search size={18} />
                <span>Cek Keamanan</span>
              </button>
              <button 
                className={`desktop-nav-link ${activeTab === 'education' ? 'active' : ''}`}
                onClick={() => handleNavigate('education')}
              >
                <BookOpen size={18} />
                <span>Edukasi</span>
              </button>
              <button 
                className={`desktop-nav-link ${activeTab === 'report' ? 'active' : ''}`}
                onClick={() => handleNavigate('report')}
              >
                <Flag size={18} />
                <span>Laporkan</span>
              </button>
            </nav>

            {/* Header Action Buttons */}
            <div className="nav-actions">
              <button 
                className="theme-toggle-btn" 
                onClick={toggleTheme}
                title={`Switch to ${theme === 'light' ? 'Dark' : 'Light'} Mode`}
              >
                {theme === 'light' ? <Moon size={20} /> : <Sun size={20} />}
              </button>

              <button 
                className="menu-toggle-btn mobile-only"
                onClick={() => setIsDrawerOpen(true)}
                title="Menu"
              >
                <Menu size={22} />
              </button>
            </div>
          </div>
        </header>
      )}

      {/* Mobile Drawer Menu */}
      {!isAdminPath && isDrawerOpen && (
        <div className="drawer-overlay" onClick={() => setIsDrawerOpen(false)}>
          <div className="drawer-content" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
              <div className="navbar-brand">
                <img src={logoImg} alt="CePu" className="brand-logo-img" style={{ height: '40px', width: '40px' }} />
                <span className="logo-text">CePu</span>
              </div>
              <button 
                onClick={() => setIsDrawerOpen(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--secondary-text)' }}
              >
                <X size={22} />
              </button>
            </div>

            <button 
              className={`drawer-item ${activeTab === 'home' ? 'active' : ''}`}
              onClick={() => handleNavigate('home')}
            >
              <Home size={20} />
              <span>Beranda</span>
            </button>

            <button 
              className={`drawer-item ${activeTab === 'detect' ? 'active' : ''}`}
              onClick={() => handleNavigate('detect')}
            >
              <Search size={20} />
              <span>Cek Keamanan</span>
            </button>

            <button 
              className={`drawer-item ${activeTab === 'education' ? 'active' : ''}`}
              onClick={() => handleNavigate('education')}
            >
              <BookOpen size={20} />
              <span>Edukasi Penipuan</span>
            </button>

            <button 
              className={`drawer-item ${activeTab === 'report' ? 'active' : ''}`}
              onClick={() => handleNavigate('report')}
            >
              <Flag size={20} />
              <span>Laporkan Lowongan</span>
            </button>
          </div>
        </div>
      )}

      {/* Main Page Container */}
      <main className="main-content-wrapper">
        {isAdminPath ? (
          <AdminPage
            onBackToHome={() => {
              window.history.pushState({}, '', '/');
              setIsAdminPath(false);
              setActiveTab('education');
            }}
          />
        ) : (
          <div className="page-container">
            {activeTab === 'home' && <LandingPage onNavigate={handleNavigate} />}
            {activeTab === 'detect' && <DetectPage />}
            {activeTab === 'education' && <EducationPage />}
            {activeTab === 'report' && <ReportPage />}
          </div>
        )}
      </main>

      {/* Footer on Desktop (Disembunyikan di Admin) */}
      {!isAdminPath && (
        <footer className="desktop-footer">
          <div className="footer-inner">
            <p className="footer-copy">
              &copy; 2026 CePu. Sistem Deteksi dan Edukasi Dini Risiko Penipuan Lowongan Kerja.
            </p>
          </div>
        </footer>
      )}

      {/* Sticky Bottom Navigation Bar (Mobile Only - Disembunyikan di Admin) */}
      {!isAdminPath && (
        <nav className="bottom-nav mobile-only">
          <button 
            className={`nav-tab-btn ${activeTab === 'home' ? 'active' : ''}`}
            onClick={() => handleNavigate('home')}
          >
            <Home size={20} />
            <span>Beranda</span>
          </button>

          <button 
            className={`nav-tab-btn ${activeTab === 'detect' ? 'active' : ''}`}
            onClick={() => handleNavigate('detect')}
          >
            <Search size={20} />
            <span>Deteksi</span>
          </button>

          <button 
            className={`nav-tab-btn ${activeTab === 'education' ? 'active' : ''}`}
            onClick={() => handleNavigate('education')}
          >
            <BookOpen size={20} />
            <span>Edukasi</span>
          </button>

          <button 
            className={`nav-tab-btn ${activeTab === 'report' ? 'active' : ''}`}
            onClick={() => handleNavigate('report')}
          >
            <Flag size={20} />
            <span>Lapor</span>
          </button>
        </nav>
      )}
    </div>
  );
}

export default App;
