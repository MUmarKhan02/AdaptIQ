import { useState, useEffect, useCallback } from 'react'

const API = '/api'

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-CA', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function formatSize(kb) {
  return kb >= 1000 ? `${(kb / 1024).toFixed(1)} MB` : `${kb} KB`
}

function ConfirmModal({ filename, isAll, retentionLabel, onConfirm, onCancel }) {
  return (
    <>
      <div
        style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)', zIndex: 200 }}
        onClick={onCancel}
      />
      <div style={{
        position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
        zIndex: 210, background: 'var(--bg)', border: '1px solid var(--border)',
        borderRadius: 12, padding: '28px 28px 24px', width: 380, maxWidth: 'calc(100vw - 32px)',
        boxShadow: '0 24px 64px rgba(0,0,0,0.5)',
        animation: 'confirmIn 0.18s cubic-bezier(0.34,1.56,0.64,1)',
      }}>
        <style>{`@keyframes confirmIn { from { opacity:0; transform:translate(-50%,-48%) scale(0.95); } to { opacity:1; transform:translate(-50%,-50%) scale(1); } }`}</style>

        {/* Icon */}
        <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'rgba(255,95,87,0.12)', border: '1px solid rgba(255,95,87,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--danger)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3 6 5 6 21 6"/>
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
            <path d="M10 11v6"/><path d="M14 11v6"/>
            <path d="M9 6V4h6v2"/>
          </svg>
        </div>

        {/* Title */}
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 17, letterSpacing: '-0.02em', color: 'var(--text-primary)', marginBottom: 8 }}>
          {isAll ? `Clear all ${retentionLabel?.toLowerCase()}?` : 'Delete file?'}
        </div>

        {/* Body */}
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 22 }}>
          {isAll ? (
            <>Are you sure you want to delete <strong style={{ color: 'var(--text-primary)' }}>all {retentionLabel?.toLowerCase()}</strong>? This action cannot be undone.</>
          ) : (
            <>Are you sure you want to delete{' '}
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', wordBreak: 'break-all' }}>{filename}</span>
              ? This action cannot be undone.</>
          )}
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: 10 }}>
          <button
            onClick={onCancel}
            style={{ flex: 1, padding: '10px 0', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text-secondary)', fontSize: 13, fontWeight: 600, fontFamily: 'var(--font-body)', cursor: 'pointer', transition: 'all 0.15s' }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-raised)'; e.currentTarget.style.color = 'var(--text-primary)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface)'; e.currentTarget.style.color = 'var(--text-secondary)' }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            style={{ flex: 1, padding: '10px 0', borderRadius: 8, border: '1px solid rgba(255,95,87,0.4)', background: 'rgba(255,95,87,0.12)', color: 'var(--danger)', fontSize: 13, fontWeight: 600, fontFamily: 'var(--font-body)', cursor: 'pointer', transition: 'all 0.15s' }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--danger)'; e.currentTarget.style.color = '#fff' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,95,87,0.12)'; e.currentTarget.style.color = 'var(--danger)' }}
          >
            Delete
          </button>
        </div>
      </div>
    </>
  )
}

function HistoryList({
  history, loading, ttlDays,
  selectedFile, viewingFile, panelOpen, deleting, confirm,
  downloadBase, emptyLabel, emptyMuted, retentionLabel,
  onCardClick, onView, onDeleteOne, onClearAll, onConfirm, onCancelConfirm,
}) {
  return (
    <>
      {confirm && (
        <ConfirmModal
          filename={confirm.filename}
          isAll={confirm.type === 'all'}
          retentionLabel={retentionLabel}
          onConfirm={onConfirm}
          onCancel={onCancelConfirm}
        />
      )}

      <div style={styles.tabControls}>
        <span style={styles.countBadge}>{history.length}</span>
        {history.length > 0 && (
          <button
            className="hist-act clear-all"
            style={{ 
              ...styles.clearAllBtn,
              ...(deleting === 'all' ? styles.btnDisabled : {})
            }}
            onClick={onClearAll}
            disabled={deleting === 'all'}
          >
            {deleting === 'all' ? 'Clearing…' : 'Clear all'}
          </button>
        )}
      </div>

      <div style={styles.retentionNote}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, opacity: 0.7 }}>
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        {retentionLabel} are automatically deleted after <strong>{ttlDays} days</strong>. Download anything you want to keep.
      </div>

      {loading ? (
        <div style={styles.emptyState}><p style={styles.emptyText}>Loading…</p></div>
      ) : history.length === 0 ? (
        <div style={styles.emptyState}>
          <div style={styles.emptyIcon}>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <p style={styles.emptyText}>{emptyLabel}</p>
          <p style={styles.emptyMuted}>{emptyMuted}</p>
        </div>
      ) : (
        <ul style={styles.list}>
          {history.map((item) => {
            const sel     = selectedFile === item.filename
            const del     = deleting === item.filename
            const viewing = viewingFile === item.filename && panelOpen
            return (
              <li
                key={item.filename}
                className={`hist-card${sel ? ' hist-card-selected' : ''}`}
                style={{
                  ...styles.card,
                  ...(sel ? (viewing ? styles.cardViewing : styles.cardSelected) : {}),
                  ...(del ? styles.cardDeleting : {}),
                }}
                onClick={() => onCardClick(item.filename)}
              >
                <div style={styles.cardTop}>
                  <div style={{ ...styles.cardIcon, ...(sel ? styles.cardIconSelected : {}) }}>
                    {sel ? (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="20 6 9 17 4 12"/>
                      </svg>
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                      </svg>
                    )}
                  </div>
                  <div style={styles.cardMeta}>
                    <span style={{ ...styles.cardName, ...(sel ? styles.cardNameSelected : {}) }}>
                      {item.filename}
                    </span>
                    <span style={styles.cardSub}>
                      {formatSize(item.size_kb)} · {formatDate(item.created_at)}
                    </span>
                  </div>
                </div>

                {sel && (
                  <div style={styles.cardActions}>
                    <a
                      className="hist-act btn-download"
                      href={`${downloadBase}/${encodeURIComponent(item.filename)}`}
                      download={item.filename}
                      style={styles.cardBtn}
                      onClick={e => e.stopPropagation()}
                    >
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                        <polyline points="7 10 12 15 17 10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
                      </svg>
                      Download
                    </a>
                    <button
                      className={`hist-act btn-view${viewing ? ' btn-view-open' : ''}`}
                      style={{ ...styles.cardBtn, ...(viewing ? styles.cardBtnViewActive : {}) }}
                      onClick={e => { e.stopPropagation(); onView(item.filename) }}
                    >
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                        <circle cx="12" cy="12" r="3"/>
                      </svg>
                      {viewing ? 'Close' : 'View'}
                    </button>
                    <button
                      className="hist-act btn-delete"
                      style={{ ...styles.cardBtn, ...styles.cardBtnDelete, ...(del ? styles.btnDisabled : {}) }}
                      onClick={e => { e.stopPropagation(); onDeleteOne(item.filename) }}
                      disabled={del}
                    >
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="3 6 5 6 21 6"/>
                        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                        <path d="M10 11v6M14 11v6"/>
                      </svg>
                      {del ? 'Deleting…' : 'Delete'}
                    </button>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </>
  )
}

export default function HistoryPage({ onBack }) {
  const [activeTab, setActiveTab] = useState('resume')
  const [hoveredTab, setHoveredTab] = useState(null)

  const switchTab = (tab) => {
    setActiveTab(tab)
    if (tab === 'cover') {
      setResumeSelected(null)
      setResumePanelOpen(false)
      setTimeout(() => setResumeViewing(null), 300)
    } else {
      setClSelected(null)
      setClPanelOpen(false)
      setTimeout(() => setClViewing(null), 300)
    }
  }

  const [resumeHistory, setResumeHistory]     = useState([])
  const [resumeTtl, setResumeTtl]             = useState(14)
  const [resumeLoading, setResumeLoading]     = useState(true)
  const [resumeSelected, setResumeSelected]   = useState(null)
  const [resumeViewing, setResumeViewing]     = useState(null)
  const [resumePanelOpen, setResumePanelOpen] = useState(false)
  const [resumeConfirm, setResumeConfirm]     = useState(null)
  const [resumeDeleting, setResumeDeleting]   = useState(null)

  const [clHistory, setClHistory]     = useState([])
  const [clTtl, setClTtl]             = useState(14)
  const [clLoading, setClLoading]     = useState(true)
  const [clSelected, setClSelected]   = useState(null)
  const [clViewing, setClViewing]     = useState(null)
  const [clPanelOpen, setClPanelOpen] = useState(false)
  const [clConfirm, setClConfirm]     = useState(null)
  const [clDeleting, setClDeleting]   = useState(null)

  const fetchResumeHistory = useCallback(async () => {
    try {
      const res = await fetch(`${API}/history`)
      const data = await res.json()
      setResumeHistory(data.history)
      if (data.ttl_days) setResumeTtl(data.ttl_days)
    } catch { setResumeHistory([]) }
    finally { setResumeLoading(false) }
  }, [])

  const fetchClHistory = useCallback(async () => {
    try {
      const res = await fetch(`${API}/history-cl`)
      const data = await res.json()
      setClHistory(data.history)
      if (data.ttl_days) setClTtl(data.ttl_days)
    } catch { setClHistory([]) }
    finally { setClLoading(false) }
  }, [])

  useEffect(() => { fetchResumeHistory(); fetchClHistory() }, [fetchResumeHistory, fetchClHistory])

  useEffect(() => {
    if (resumeSelected && !resumeHistory.find(h => h.filename === resumeSelected)) setResumeSelected(null)
    if (resumeViewing && !resumeHistory.find(h => h.filename === resumeViewing)) {
      setResumePanelOpen(false); setTimeout(() => setResumeViewing(null), 300)
    }
  }, [resumeHistory, resumeSelected, resumeViewing])

  useEffect(() => {
    if (clSelected && !clHistory.find(h => h.filename === clSelected)) setClSelected(null)
    if (clViewing && !clHistory.find(h => h.filename === clViewing)) {
      setClPanelOpen(false); setTimeout(() => setClViewing(null), 300)
    }
  }, [clHistory, clSelected, clViewing])

  const handleResumeCardClick = (f) => {
    if (resumeSelected === f) { setResumeSelected(null); if (resumeViewing === f) { setResumePanelOpen(false); setTimeout(() => setResumeViewing(null), 300) } }
    else setResumeSelected(f)
  }
  const handleResumeView = (f) => {
    if (resumeViewing === f && resumePanelOpen) { setResumePanelOpen(false); setTimeout(() => setResumeViewing(null), 300) }
    else { setResumeViewing(f); setResumePanelOpen(true) }
  }
  const handleResumeConfirm = async () => {
    const c = resumeConfirm; setResumeConfirm(null)
    if (c.type === 'one') {
      setResumeDeleting(c.filename)
      try { await fetch(`${API}/history/${encodeURIComponent(c.filename)}`, { method: 'DELETE' }); setResumeHistory(h => h.filter(f => f.filename !== c.filename)) }
      finally { setResumeDeleting(null) }
    } else {
      setResumeDeleting('all')
      try { await fetch(`${API}/history`, { method: 'DELETE' }); setResumeHistory([]); setResumeSelected(null) }
      finally { setResumeDeleting(null) }
    }
  }

  const handleClCardClick = (f) => {
    if (clSelected === f) { setClSelected(null); if (clViewing === f) { setClPanelOpen(false); setTimeout(() => setClViewing(null), 300) } }
    else setClSelected(f)
  }
  const handleClView = (f) => {
    if (clViewing === f && clPanelOpen) { setClPanelOpen(false); setTimeout(() => setClViewing(null), 300) }
    else { setClViewing(f); setClPanelOpen(true) }
  }
  const handleClConfirm = async () => {
    const c = clConfirm; setClConfirm(null)
    if (c.type === 'one') {
      setClDeleting(c.filename)
      try { await fetch(`${API}/history-cl/${encodeURIComponent(c.filename)}`, { method: 'DELETE' }); setClHistory(h => h.filter(f => f.filename !== c.filename)) }
      finally { setClDeleting(null) }
    } else {
      setClDeleting('all')
      try { await fetch(`${API}/history-cl`, { method: 'DELETE' }); setClHistory([]); setClSelected(null) }
      finally { setClDeleting(null) }
    }
  }

  const isResume    = activeTab === 'resume'
  const panelOpen   = isResume ? resumePanelOpen : clPanelOpen
  const viewingFile = isResume ? resumeViewing : clViewing
  const viewBase    = isResume ? `${API}/download` : `${API}/download-cl`

  const handleClosePanel = () => {
    if (isResume) { setResumePanelOpen(false); setTimeout(() => setResumeViewing(null), 300) }
    else { setClPanelOpen(false); setTimeout(() => setClViewing(null), 300) }
  }

  return (
    <div style={styles.layout}>
      <style>{`
    .hist-card { -webkit-tap-highlight-color: transparent; }
    .hist-card:focus { outline: none; }
    .hist-card:focus-visible { outline: none; }
    .hist-card:not(.hist-card-selected):hover { background: rgba(255,255,255,0.06) !important; }
    .hist-card:active { background-color: inherit !important; box-shadow: none !important; transform: none !important; }
    .hist-act:focus { outline: none; }
    .hist-act:focus-visible { outline: none !important; box-shadow: none !important; }
    .hist-act.clear-all { border-color: rgba(255,95,87,0.7) !important; color: var(--danger) !important; }
    .hist-act.back-to-home:hover { background: rgba(255,255,255,0.09) !important; border-color: rgba(255,255,255,0.25) !important; color: #ffffff !important; box-shadow: 0 0 0 1px rgba(255,255,255,0.12) !important; transform: translateY(-1px) !important;}
    .hist-act:not(.clear-all):hover { background: var(--surface-raised) !important; border-color: rgba(255,255,255,0.25) !important; }
    .hist-act.clear-all:hover { background: rgba(255, 95, 87, 0.18) !important; border-color: rgba(255, 95, 87, 0.7) !important; color: #ff6b65 !important; }
    .hist-tab:focus { outline: none; }
    .btn-download:not([aria-disabled="true"]):hover { background: rgba(255,255,255,0.09) !important; border-color: rgba(255,255,255,0.25) !important; color: #ffffff !important; }
    .btn-view:not([aria-disabled="true"]):not(.btn-view-open):hover { background: rgba(255,255,255,0.09) !important; border-color: rgba(255,255,255,0.25) !important; color: #ffffff !important; }
    .btn-view.btn-view-open:hover { opacity: 0.7 !important; }
    .btn-delete:not(:disabled):hover { background: rgba(255, 95, 87, 0.18) !important; border-color: rgba(255, 95, 87, 0.7) !important; color: #ff6b65 !important; }
    @keyframes slideInPanel { from { transform: translateX(100%); } to { transform: translateX(0); } }
      `}</style>

      <header style={styles.header}>
        <div style={styles.headerInner}>
          <div style={styles.logo}>
            <span style={styles.logoIcon}>⌂</span>
            <span style={styles.logoText}>resume<em style={styles.logoAccent}>tailor</em></span>
          </div>
          <span style={styles.headerTag}>personal workspace</span>
        </div>
      </header>

      <div style={styles.body}>
        <div style={styles.content}>

          <div style={styles.titleRow}>
            <div style={styles.titleLeft}>
              <button className="hist-act back-to-home" style={styles.backBtn} onClick={onBack}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="19" y1="12" x2="5" y2="12"/>
                  <polyline points="12 19 5 12 12 5"/>
                </svg>
                Home
              </button>
              <h1 style={styles.pageTitle}>History</h1>
            </div>
          </div>

          {/* Tabs */}
          <div style={styles.tabBar}>
            <button
              className="hist-tab"
              style={{ 
                ...styles.tab, 
                ...(activeTab === 'resume' ? styles.tabActive : hoveredTab === 'resume' ? styles.tabHovered : styles.tabInactive) 
              }}
              onClick={() => switchTab('resume')}
              onMouseEnter={() => setHoveredTab('resume')}
              onMouseLeave={() => setHoveredTab(null)}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              Resumes
              <span style={{ ...styles.tabBadge, ...(activeTab === 'resume' ? styles.tabBadgeActive : {}) }}>{resumeHistory.length}</span>
            </button>

            <button
              className="hist-tab"
              style={{
                ...styles.tab,
                ...(activeTab === 'cover' ? styles.tabActive : hoveredTab === 'cover' ? styles.tabHovered : styles.tabInactive)
              }}
              onClick={() => switchTab('cover')}
              onMouseEnter={() => setHoveredTab('cover')}
              onMouseLeave={() => setHoveredTab(null)}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
              Cover Letters
              <span style={{ ...styles.tabBadge, ...(activeTab === 'cover' ? styles.tabBadgeActive : {}) }}>{clHistory.length}</span>
            </button>
          </div>

          {activeTab === 'resume' && (
            <HistoryList
              history={resumeHistory} loading={resumeLoading} ttlDays={resumeTtl}
              selectedFile={resumeSelected} viewingFile={resumeViewing} panelOpen={resumePanelOpen}
              deleting={resumeDeleting} confirm={resumeConfirm}
              downloadBase={`${API}/download`}
              emptyLabel="No tailored resumes yet."
              emptyMuted="Generate one from the home page to see it here."
              retentionLabel="Tailored resumes"
              onCardClick={handleResumeCardClick} onView={handleResumeView}
              onDeleteOne={(f) => setResumeConfirm({ type: 'one', filename: f })}
              onClearAll={() => setResumeConfirm({ type: 'all' })}
              onConfirm={handleResumeConfirm} onCancelConfirm={() => setResumeConfirm(null)}
            />
          )}

          {activeTab === 'cover' && (
            <HistoryList
              history={clHistory} loading={clLoading} ttlDays={clTtl}
              selectedFile={clSelected} viewingFile={clViewing} panelOpen={clPanelOpen}
              deleting={clDeleting} confirm={clConfirm}
              downloadBase={`${API}/download-cl`}
              emptyLabel="No cover letters yet."
              emptyMuted="Enable the Cover Letter toggle when tailoring to generate one."
              retentionLabel="Cover letters"
              onCardClick={handleClCardClick} onView={handleClView}
              onDeleteOne={(f) => setClConfirm({ type: 'one', filename: f })}
              onClearAll={() => setClConfirm({ type: 'all' })}
              onConfirm={handleClConfirm} onCancelConfirm={() => setClConfirm(null)}
            />
          )}

        </div>

        {panelOpen && (
          <>
            <div style={styles.backdrop} onClick={handleClosePanel} />
            <div style={styles.viewerPanel}>
              <div style={styles.viewerHeader}>
                <span style={styles.viewerTitle} title={viewingFile}>{viewingFile || ''}</span>
                <button className="hist-act" style={styles.viewerClose} onClick={handleClosePanel}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"/>
                    <line x1="6" y1="6" x2="18" y2="18"/>
                  </svg>
                </button>
              </div>
              {viewingFile && (
                <iframe
                  key={viewingFile}
                  src={`${viewBase}/${encodeURIComponent(viewingFile)}#zoom=page-width`}
                  style={styles.viewerIframe}
                  title="Preview"
                />
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

const styles = {
  layout: { minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' },
  header: { borderBottom: '1px solid var(--border)', padding: '0 24px', flexShrink: 0 },
  headerInner: { maxWidth: '100%', height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  logo: { display: 'flex', alignItems: 'center', gap: 8 },
  logoIcon: { fontSize: 18, color: 'var(--accent)' },
  logoText: { fontFamily: 'var(--font-display)', fontSize: 20, color: 'var(--text-primary)', letterSpacing: '-0.02em' },
  logoAccent: { fontStyle: 'italic', color: 'var(--accent)' },
  headerTag: { fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' },

  body: { flex: 1, display: 'flex', overflow: 'hidden', position: 'relative' },
  content: { flex: 1, maxWidth: 720, margin: '0 auto', padding: '40px 24px 80px', display: 'flex', flexDirection: 'column', gap: 12, width: '100%' },

  titleRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
  titleLeft: { display: 'flex', alignItems: 'center', gap: 12 },
  backBtn: { display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: '1px solid var(--border)', borderRadius: 6, padding: '6px 10px', fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer', fontFamily: 'var(--font-body)', outline: 'none', WebkitTapHighlightColor: 'transparent', transition: 'all 0.2s ease' },
  pageTitle: { fontFamily: 'var(--font-display)', fontSize: 28, letterSpacing: '-0.02em', color: 'var(--text-primary)', fontWeight: 700 },

  tabBar: { display: 'flex', gap: 4, background: 'var(--surface)', border: '1px solid transparent', borderRadius: 'var(--radius)', padding: 4, marginBottom: 4 },
  tab: { flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, padding: '9px 16px', borderRadius: 7, border: 'none', fontSize: 13, fontFamily: 'var(--font-body)', fontWeight: 500, cursor: 'pointer', transition: 'all 0.15s', outline: 'none', WebkitTapHighlightColor: 'transparent' },
  tabActive: { background: 'var(--surface-raised)', color: 'var(--text-primary)', boxShadow: '0 1px 3px rgba(0,0,0,0.3)' },
  tabInactive: { background: 'transparent', color: 'var(--text-muted)' },
  tabHovered: { background: 'rgba(255,255,255,0.06)', color: 'var(--text-muted)' },
  tabBadge: { fontSize: 10, fontFamily: 'var(--font-mono)', background: 'var(--surface-raised)', border: '1px solid var(--border)', borderRadius: 20, padding: '1px 7px', color: 'var(--text-muted)', marginLeft: 2 },
  tabBadgeActive: { background: 'var(--accent-dim)', borderColor: 'var(--accent)', color: 'var(--accent)' },

  tabControls: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', minHeight: 28 },
  countBadge: { background: 'var(--surface-raised)', border: '1px solid var(--border)', borderRadius: 20, padding: '2px 9px', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' },
  clearAllBtn: { background: 'none', border: '1px solid rgba(255, 95, 87, 0.7)', borderRadius: 6, padding: '7px 14px', fontSize: 12, color: 'var(--danger)', cursor: 'pointer', fontFamily: 'var(--font-body)', fontWeight: 500, outline: 'none', WebkitTapHighlightColor: 'transparent' },
  btnDisabled: { opacity: 0.4, cursor: 'default', pointerEvents: 'none' },

  retentionNote: { display: 'flex', alignItems: 'flex-start', gap: 8, padding: '9px 13px', background: 'rgba(200,240,76,0.05)', border: '1px solid rgba(200,240,76,0.15)', borderRadius: 'var(--radius-sm, 6px)', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', lineHeight: 1.5 },

  emptyState: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, padding: '64px 24px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', textAlign: 'center' },
  emptyIcon: { color: 'var(--text-muted)', marginBottom: 4 },
  emptyText: { fontSize: 14, color: 'var(--text-secondary)', fontWeight: 500 },
  emptyMuted: { fontSize: 13, color: 'var(--text-muted)' },

  list: { listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 },
  card: { background: 'var(--surface)', border: 'none', borderRadius: 'var(--radius)', padding: '12px 16px', cursor: 'pointer', userSelect: 'none', transition: 'background 0.15s, border-color 0.15s, opacity 0.2s', WebkitTapHighlightColor: 'transparent', outline: 'none' },
  cardSelected: { background: 'var(--accent-dim)', borderColor: 'var(--accent)' },
  cardViewing: { background: 'var(--accent-dim)', borderColor: 'var(--accent)' },
  cardDeleting: { opacity: 0.35, pointerEvents: 'none' },
  cardTop: { display: 'flex', alignItems: 'center', gap: 12 },
  cardIcon: { color: 'var(--text-muted)', flexShrink: 0, display: 'flex', alignItems: 'center' },
  cardIconSelected: { color: 'var(--accent)' },
  cardMeta: { display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 },
  cardName: { fontSize: 13, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', wordBreak: 'break-all' },
  cardNameSelected: { color: 'var(--accent)' },
  cardSub: { fontSize: 11, color: 'var(--text-muted)' },

  cardActions: { display: 'flex', gap: 6, paddingTop: 10, paddingLeft: 28 },
  cardBtn: { display: 'flex', alignItems: 'center', gap: 5, background: 'none', border: '1px solid var(--border)', borderRadius: 6, padding: '4px 10px', fontSize: 11, fontFamily: 'var(--font-body)', color: 'var(--text-secondary)', cursor: 'pointer', textDecoration: 'none', fontWeight: 500, outline: 'none', WebkitTapHighlightColor: 'transparent', transition: 'opacity 0.15s' },
  cardBtnViewActive: { borderColor: 'var(--accent)', color: 'var(--accent)', background: 'var(--accent-dim)' },
  cardBtnDelete: { color: 'var(--danger)', borderColor: 'rgba(255, 95, 87, 0.3)' },

  backdrop: { position: 'fixed', inset: 0, background: 'rgba(0, 0, 0, 0.55)', backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)', zIndex: 110 },
  viewerPanel: { position: 'fixed', top: 0, right: 0, bottom: 0, width: '75vw', minWidth: 600, background: 'var(--bg)', borderLeft: '1px solid var(--border)', display: 'flex', flexDirection: 'column', zIndex: 120, animation: 'slideInPanel 0.28s cubic-bezier(0.4, 0, 0.2, 1)' },
  viewerHeader: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 18px', borderBottom: '1px solid var(--border)', flexShrink: 0, gap: 12 },
  viewerTitle: { fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 },
  viewerClose: { background: 'none', border: '1px solid var(--border)', borderRadius: 6, width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--text-muted)', flexShrink: 0, outline: 'none', WebkitTapHighlightColor: 'transparent' },
  viewerIframe: { flex: 1, border: 'none', width: '100%', background: '#111' },
}