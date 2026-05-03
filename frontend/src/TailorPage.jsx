import { useState, useEffect } from 'react'

const API = '/api'

export default function TailorPage({ resumeFilename, onBack, onProceed, errorMessage}) {
  const [activeTab, setActiveTab] = useState('url')
  const [panelOpen, setPanelOpen] = useState(false)
  const [genCover, setGenCover]     = useState(false)
  const [urlValue, setUrlValue] = useState('')
  const [descValue, setDescValue] = useState('')
  const [urlStatus, setUrlStatus] = useState(null) // null | 'loading' | 'valid' | 'error'
  const [urlError, setUrlError] = useState('')
  const [jobPreview, setJobPreview] = useState(null) // { title, description, url }
  const [showPreview, setShowPreview] = useState(false)
  const [quota, setQuota] = useState(null)

  const fetchQuota = async () => {
    try {
      const res = await fetch(`${API}/gemini-quota`)
      if (res.ok) setQuota(await res.json())
    } catch { /* silently ignore */ }
  }

  useEffect(() => { fetchQuota() }, [])

  const handleUrlChange = (e) => {
    setUrlValue(e.target.value)
    setUrlStatus(null)
    setUrlError('')
    setJobPreview(null)
    setShowPreview(false)
  }

  const validateAndFetch = async () => {
    const trimmed = urlValue.trim()
    if (!trimmed) return

    setUrlStatus('loading')
    setUrlError('')
    setJobPreview(null)
    setShowPreview(false)

    try {
      const res = await fetch(`${API}/fetch-job-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: trimmed }),
      })
      const data = await res.json()
      if (!res.ok) {
        setUrlStatus('error')
        setUrlError(data.detail || 'Could not validate this URL.')
      } else {
        setUrlStatus('valid')
        setJobPreview(data)
        setShowPreview(true)
      }
    } catch {
      setUrlStatus('error')
      setUrlError('Network error — make sure the backend is running.')
    }
  }

  const jobReady = activeTab === 'url' ? urlStatus === 'valid' : descValue.trim().length > 0
  const isReadyToProceed = jobReady

  const borderColor =
    urlStatus === 'valid' ? 'var(--success)' :
    urlStatus === 'error' ? 'var(--danger)' :
    'var(--border)'

  return (
    <div style={styles.layout}>
      <style>{`
        .file-chip:hover { border-color: rgba(255,255,255,0.25) !important; background: var(--surface-raised) !important; }
        .back-btn:hover { background: rgba(255,255,255,0.08) !important; border-color: rgba(255,255,255,0.25) !important; color: #ffffff !important; box-shadow: 0 0 0 1px rgba(255,255,255,0.12) !important; transform: translateY(-1px) !important; }
        .tailor-tab:hover { background: rgba(255,255,255,0.06) !important; color: var(--text-primary) !important; }
        .validate-btn:not(:disabled):hover,
        .preview-toggle:hover,
        .toggle-item:not(:disabled):hover { background: rgba(255,255,255,0.08) !important; border-color: rgba(255,255,255,0.25) !important; color: #ffffff !important; box-shadow: 0 0 0 1px rgba(255,255,255,0.12) !important; transform: translateY(-1px) !important; }
        .proceed-btn:hover { filter: brightness(1.12); }
        .url-clear-btn { color: var(--danger) !important; transition: all 0.15s; }
        .url-clear-btn:hover { color: #fff !important; background: var(--danger) !important; }
        .desc-clear-btn { transition: all 0.15s; }
        .desc-clear-btn:hover { color: #fff !important; background: var(--danger) !important; border-color: var(--danger) !important; }
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

      <main style={styles.main}>

        <div style={styles.topBar}>
          <button className="back-btn" style={styles.backBtn} onClick={onBack}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="19" y1="12" x2="5" y2="12"/>
              <polyline points="12 19 5 12 12 5"/>
            </svg>
            <span>Back</span>
          </button>
          <button className="file-chip" style={styles.fileChip} title={resumeFilename} onClick={() => setPanelOpen(true)}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
            <span style={styles.fileChipName}>{resumeFilename}</span>
          </button>
        </div>

        <section style={styles.hero}>
          <h1 style={styles.heroTitle}>Add the<br /><em style={styles.heroItalic}>job details.</em></h1>
          <p style={styles.heroSub}>Paste a job posting URL or the full description — we'll tailor your resume to match.</p>
        </section>

        <section style={styles.section}>
          <div style={styles.tabBar}>
            <button
              className="tailor-tab"
              style={{ ...styles.tab, ...(activeTab === 'url' ? styles.tabActive : styles.tabInactive) }}
              onClick={() => setActiveTab('url')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
              </svg>
              Job URL
            </button>
            <button
              className="tailor-tab"
              style={{ ...styles.tab, ...(activeTab === 'description' ? styles.tabActive : styles.tabInactive) }}
              onClick={() => setActiveTab('description')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="17" y1="10" x2="3" y2="10"/>
                <line x1="21" y1="6" x2="3" y2="6"/>
                <line x1="21" y1="14" x2="3" y2="14"/>
                <line x1="17" y1="18" x2="3" y2="18"/>
              </svg>
              Job Description
            </button>
          </div>

          <div style={styles.tabContent}>
            {activeTab === 'url' ? (
              <div style={styles.inputGroup}>
                <label style={styles.inputLabel}>Paste the job posting URL</label>

                {/* URL input row */}
                <div style={{ ...styles.inputWrapper, borderColor }}>
                  <span style={styles.inputIcon}>
                    {urlStatus === 'loading' ? (
                      <span style={styles.spinner} />
                    ) : urlStatus === 'valid' ? (
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--success)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="20 6 9 17 4 12"/>
                      </svg>
                    ) : urlStatus === 'error' ? (
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--danger)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                      </svg>
                    ) : (
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
                      </svg>
                    )}
                  </span>
                  <input
                    style={styles.urlInput}
                    type="url"
                    placeholder="https://jobs.example.com/software-engineer"
                    value={urlValue}
                    onChange={handleUrlChange}
                    onKeyDown={(e) => e.key === 'Enter' && validateAndFetch()}
                    spellCheck={false}
                  />
                  {urlValue && (
                    <button className="url-clear-btn" style={styles.clearBtn} onClick={() => { setUrlValue(''); setUrlStatus(null); setUrlError(''); setJobPreview(null); setShowPreview(false) }} title="Clear">×</button>
                  )}
                </div>

                {/* Validate button */}
                {urlValue.trim() && urlStatus !== 'valid' && (
                  <button
                    className="validate-btn"
                    style={{ ...styles.validateBtn, ...(urlStatus === 'loading' ? styles.validateBtnLoading : {}) }}
                    onClick={validateAndFetch}
                    disabled={urlStatus === 'loading'}
                  >
                    {urlStatus === 'loading' ? 'Checking…' : 'Validate URL'}
                  </button>
                )}

                {/* Error message */}
                {urlStatus === 'error' && (
                  <div style={styles.errorBanner}>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                    </svg>
                    {urlError}
                  </div>
                )}

                {/* Preview toggle + panel */}
                {urlStatus === 'valid' && jobPreview && (
                  <div style={styles.previewSection}>
                    <button className="preview-toggle" style={styles.previewToggle} onClick={() => setShowPreview(v => !v)}>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                        <circle cx="12" cy="12" r="3"/>
                      </svg>
                      {showPreview ? 'Hide preview' : 'Show preview'}
                      <svg
                        width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                        style={{ transition: 'transform 0.2s', transform: showPreview ? 'rotate(180deg)' : 'rotate(0deg)' }}
                      >
                        <polyline points="6 9 12 15 18 9"/>
                      </svg>
                    </button>

                    {showPreview && (
                      <div style={styles.previewCard}>
                        <div style={styles.previewHeader}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--success)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="20 6 9 17 4 12"/>
                          </svg>
                          <span style={styles.previewConfirmed}>Job posting confirmed</span>
                        </div>
                        {jobPreview.title && (
                          <p style={styles.previewTitle}>{jobPreview.title}</p>
                        )}
                        {jobPreview.description && (
                          <p style={styles.previewDesc}>{jobPreview.description}</p>
                        )}
                        <a
                          href={jobPreview.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={styles.previewLink}
                        >
                          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{jobPreview.url}</span>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                            <polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
                          </svg>
                        </a>
                      </div>
                    )}
                  </div>
                )}

                {!urlStatus && (
                  <p style={styles.inputHint}>Works with LinkedIn, Greenhouse, Lever, Workday, and most job boards.</p>
                )}
              </div>
            ) : (
              <div style={styles.inputGroup}>
                <label style={styles.inputLabel}>Paste the full job description</label>
                <textarea
                  style={styles.textarea}
                  placeholder="Paste the job title, responsibilities, requirements, and any other details from the posting…"
                  value={descValue}
                  onChange={(e) => setDescValue(e.target.value)}
                  spellCheck={false}
                />
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <p style={{ ...styles.inputHint, margin: 0 }}>
                    {descValue.length > 0
                      ? `${descValue.trim().split(/\s+/).length} words · ${descValue.length} characters`
                      : 'The more detail you include, the better the tailoring.'}
                  </p>
                  {descValue.length > 0 && (
                    <button
                      className="desc-clear-btn"
                      onClick={() => setDescValue('')}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 5,
                        background: 'none', border: '1px solid var(--danger)',
                        borderRadius: 'var(--radius-sm)', color: 'var(--danger)',
                        fontSize: 12, fontFamily: 'var(--font-body)', fontWeight: 500,
                        padding: '4px 10px', cursor: 'pointer',
                      }}
                    >
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                      </svg>
                      Clear
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </section>
        {errorMessage && (
          <div style={styles.errorBanner}>
            <span>✕</span>
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Generate toggles — cover letter only */}
        <section style={styles.section}>
          <p style={styles.toggleLabel}>Also generate</p>
          <div style={styles.toggleRow}>

            {/* Cover letter toggle */}
            <button
              className="toggle-item"
              style={{
                ...styles.toggleItem,
                ...(jobReady ? styles.toggleItemEnabled : styles.toggleItemDisabled),
                ...(jobReady && genCover ? styles.toggleItemActive : {}),
              }}
              disabled={!jobReady}
              onClick={() => jobReady && setGenCover(v => !v)}
            >
              <div style={{
                ...styles.toggleCheck,
                ...(jobReady && genCover ? styles.toggleCheckOn : {}),
              }}>
                {jobReady && genCover && (
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                )}
              </div>
              <div style={styles.toggleContent}>
                <span style={styles.toggleTitle}>Cover Letter</span>
                <span style={styles.toggleSub}>Personalised to the job posting</span>
              </div>
            </button>

          </div>
        </section>

        <section style={styles.section}>
          {/* Gemini quota indicator */}
          {quota && (() => {
            const pct     = quota.remaining / quota.limit
            const hrs     = Math.floor(quota.resets_in_s / 3600)
            const mins    = Math.floor((quota.resets_in_s % 3600) / 60)
            const resetStr = hrs > 0 ? `${hrs}h ${mins}m` : `${mins}m`
            const color   = pct > 0.4 ? 'var(--success)' : pct > 0.1 ? '#f0a500' : 'var(--danger)'
            const barW    = Math.max(2, Math.round(pct * 100))
            return (
              <div style={styles.quotaBar}>
                <div style={styles.quotaTop}>
                  <span style={styles.quotaLabel}>
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{marginRight:5,opacity:0.7}}>
                      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
                    </svg>
                    gemini api · daily usage
                  </span>
                  <span style={{ ...styles.quotaCount, color }}>
                    {quota.remaining.toLocaleString()} / {quota.limit.toLocaleString()} remaining
                  </span>
                </div>
                <div style={styles.quotaTrack}>
                  <div style={{ ...styles.quotaFill, width: `${barW}%`, background: color }} />
                </div>
                <span style={styles.quotaReset}>resets in {resetStr}</span>
              </div>
            )
          })()}

          <button
            className= "proceed-btn"
            style={{ ...styles.proceedBtn, ...(isReadyToProceed ? styles.proceedBtnActive : styles.proceedBtnDisabled) }}
            disabled={!isReadyToProceed}
            onClick={() => {
              const jobText = activeTab === 'url'
                ? (jobPreview?.body_text || `JOB TITLE: ${jobPreview?.title}\n\nDESCRIPTION: ${jobPreview?.description}`)
                : descValue
              const jobTitle = activeTab === 'url' ? (jobPreview?.title || urlValue) : 'Job Description'
              onProceed(jobText, jobTitle, true, genCover)
              // Refresh quota after a short delay to capture the new calls
              setTimeout(fetchQuota, 3000)
            }}
          >
            <span>{genCover ? 'Tailor My Resume & Cover Letter' : 'Tailor My Resume'}</span>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="5" y1="12" x2="19" y2="12"/>
              <polyline points="12 5 19 12 12 19"/>
            </svg>
          </button>
        </section>

      </main>

      <footer style={styles.footer}>
        <span style={styles.footerText}>resume tailor · personal workspace</span>
      </footer>
      {/* PDF side panel — same pattern as HistoryPage */}
      {panelOpen && (
        <>
          <div
            style={{
              position: 'fixed', inset: 0,
              background: 'rgba(0,0,0,0.55)',
              backdropFilter: 'blur(4px)',
              WebkitBackdropFilter: 'blur(4px)',
              zIndex: 110,
            }}
            onClick={() => setPanelOpen(false)}
          />
          <div style={{
            position: 'fixed', top: 0, right: 0, bottom: 0,
            width: '75vw', minWidth: 600,
            background: 'var(--bg)',
            borderLeft: '1px solid var(--border)',
            display: 'flex', flexDirection: 'column',
            zIndex: 120,
            animation: 'slideInPanel 0.28s cubic-bezier(0.4,0,0.2,1)',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '12px 18px', borderBottom: '1px solid var(--border)',
              flexShrink: 0, gap: 12,
            }}>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 11,
                color: 'var(--text-secondary)', overflow: 'hidden',
                textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1,
              }}>{resumeFilename}</span>
              <button
                onClick={() => setPanelOpen(false)}
                style={{
                  background: 'none', border: '1px solid var(--border)',
                  borderRadius: 6, width: 28, height: 28,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  cursor: 'pointer', color: 'var(--text-muted)',
                  flexShrink: 0, outline: 'none',
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18"/>
                  <line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
            <iframe
              src={`${API}/preview-resume/${encodeURIComponent(resumeFilename)}#zoom=100`}
              style={{ flex: 1, border: 'none', width: '100%', background: '#111' }}
              title="Resume preview"
            />
          </div>
        </>
      )}
    </div>
  )
}

const styles = {
  layout: { minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' },
  header: { borderBottom: '1px solid var(--border)', padding: '0 24px' },
  headerInner: { maxWidth: 680, margin: '0 auto', height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  logo: { display: 'flex', alignItems: 'center', gap: 8 },
  logoIcon: { fontSize: 18, color: 'var(--accent)' },
  logoText: { fontFamily: 'var(--font-display)', fontSize: 20, color: 'var(--text-primary)', letterSpacing: '-0.02em' },
  logoAccent: { fontStyle: 'italic', color: 'var(--accent)' },
  headerTag: { fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' },
  main: { flex: 1, maxWidth: 680, width: '100%', margin: '0 auto', padding: '40px 24px 80px', display: 'flex', flexDirection: 'column', gap: 40 },
  topBar: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  backBtn: { display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)', fontSize: 13, padding: '6px 12px', cursor: 'pointer', fontFamily: 'var(--font-body)', transition: 'all 0.2s ease' },
  fileChip: { display: 'flex', alignItems: 'center', gap: 7, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 20, padding: '5px 12px' },
  fileChipName: { fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent)', maxWidth: 300, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  hero: { paddingBottom: 4 },
  heroTitle: { fontFamily: 'var(--font-display)', fontSize: 'clamp(36px, 6vw, 54px)', lineHeight: 1.1, letterSpacing: '-0.03em', color: 'var(--text-primary)', marginBottom: 16 },
  heroItalic: { fontStyle: 'italic', color: 'var(--accent)' },
  heroSub: { fontSize: 16, color: 'var(--text-secondary)', lineHeight: 1.6, maxWidth: 480 },
  section: { display: 'flex', flexDirection: 'column', gap: 12 },
  tabBar: { display: 'flex', gap: 6, background: 'var(--surface)', border: '1px solid transparent', borderRadius: 'var(--radius)', padding: 4 },
  tab: { flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, padding: '9px 16px', borderRadius: 7, border: 'none', fontSize: 13, fontFamily: 'var(--font-body)', fontWeight: 500, cursor: 'pointer', transition: 'all 0.15s' },
  tabActive: { background: 'var(--surface-raised)', color: 'var(--text-primary)', boxShadow: '0 1px 3px rgba(0,0,0,0.3)' },
  tabInactive: { background: 'transparent', color: 'var(--text-muted)' },
  tabContent: { background: 'var(--surface)', border: '1px solid transparent', borderRadius: 'var(--radius)', padding: '24px' },
  inputGroup: { display: 'flex', flexDirection: 'column', gap: 10 },
  inputLabel: { fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 500, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)' },
  inputWrapper: { display: 'flex', alignItems: 'center', background: 'var(--surface-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', overflow: 'hidden', transition: 'border-color 0.2s' },
  inputIcon: { padding: '0 12px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', flexShrink: 0 },
  urlInput: { flex: 1, background: 'none', border: 'none', outline: 'none', color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-mono)', padding: '12px 0' },
  clearBtn: { background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 18, lineHeight: 1, padding: '0 12px', cursor: 'pointer', flexShrink: 0 },
  validateBtn: { alignSelf: 'flex-start', background: 'var(--surface-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)', fontSize: 13, fontFamily: 'var(--font-body)', fontWeight: 500, padding: '8px 16px', cursor: 'pointer', transition: 'all 0.15s' },
  validateBtnLoading: { opacity: 0.6, cursor: 'default' },
  errorBanner: { display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', borderRadius: 'var(--radius-sm)', background: 'var(--danger-dim)', border: '1px solid rgba(255,95,87,0.25)', color: 'var(--danger)', fontSize: 13 },
  previewSection: { display: 'flex', flexDirection: 'column', gap: 8 },
  previewToggle: { alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)', fontSize: 12, fontFamily: 'var(--font-body)', padding: '6px 12px', cursor: 'pointer' },
  previewCard: { background: 'var(--surface-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '16px', display: 'flex', flexDirection: 'column', gap: 8 },
  previewHeader: { display: 'flex', alignItems: 'center', gap: 7 },
  previewConfirmed: { fontSize: 12, color: 'var(--success)', fontWeight: 500, fontFamily: 'var(--font-mono)' },
  previewTitle: { fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.4 },
  previewDesc: { fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 },
  previewLink: { display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--accent)', textDecoration: 'none', overflow: 'hidden' },
  inputHint: { fontSize: 12, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' },
  textarea: { width: '100%', minHeight: 220, background: 'var(--surface-raised)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-body)', lineHeight: 1.6, padding: '14px', resize: 'vertical', outline: 'none', boxSizing: 'border-box' },
  proceedBtn: { display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, width: '100%', padding: '14px 24px', borderRadius: 'var(--radius)', border: 'none', fontSize: 14, fontFamily: 'var(--font-body)', fontWeight: 600, cursor: 'pointer', transition: 'all 0.2s ease' },
  proceedBtnActive: { background: 'var(--accent)', color: '#0e0f11' },
  proceedBtnDisabled: { background: 'var(--surface-raised)', color: 'var(--text-muted)', cursor: 'not-allowed', border: '1px solid var(--border)' },
  footer: { borderTop: '1px solid var(--border)', padding: '16px 24px', textAlign: 'center' },
  footerText: { fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.06em' },
  spinner: { display: 'block', width: 14, height: 14, border: '2px solid var(--border)', borderTop: '2px solid var(--accent)', borderRadius: '50%', animation: 'spin 0.8s linear infinite' },

  // ── Generate toggles ──────────────────────────────────────────────────────
  toggleLabel: {
    fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 500,
    letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)',
  },
  toggleRow: {
    display: 'flex', gap: 10,
  },
  toggleItem: {
    flex: 1, display: 'flex', alignItems: 'center', gap: 12,
    padding: '14px 16px',
    borderRadius: 'var(--radius)', border: '1px solid var(--border)',
    background: 'var(--surface)', cursor: 'pointer',
    textAlign: 'left', transition: 'all 0.15s',
    fontFamily: 'var(--font-body)',
  },
  toggleItemDisabled: {
    opacity: 0.35, cursor: 'not-allowed',
  },
  toggleItemEnabled: {
    opacity: 1, cursor: 'pointer',
  },
  toggleItemActive: {
    borderColor: 'var(--accent)', background: 'var(--accent-dim)',
  },
  toggleCheck: {
    width: 18, height: 18, borderRadius: 5,
    border: '1.5px solid var(--border)',
    background: 'var(--surface-raised)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    flexShrink: 0, transition: 'all 0.15s',
  },
  toggleCheckOn: {
    background: 'var(--accent)', borderColor: 'var(--accent)', color: '#0e0f11',
  },
  toggleContent: {
    display: 'flex', flexDirection: 'column', gap: 2,
  },
  toggleTitle: {
    fontSize: 13, fontWeight: 600, color: 'var(--text-primary)',
  },
  toggleSub: {
    fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)',
  },

  // ── Gemini quota bar ──────────────────────────────────────────────────────
  quotaBar: {
    display: 'flex', flexDirection: 'column', gap: 6,
    padding: '10px 14px',
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-sm)',
  },
  quotaTop: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  },
  quotaLabel: {
    display: 'flex', alignItems: 'center',
    fontFamily: 'var(--font-mono)', fontSize: 10,
    letterSpacing: '0.08em', textTransform: 'uppercase',
    color: 'var(--text-muted)',
  },
  quotaCount: {
    fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
  },
  quotaTrack: {
    height: 3, borderRadius: 99,
    background: 'var(--surface-raised)',
    overflow: 'hidden',
  },
  quotaFill: {
    height: '100%', borderRadius: 99,
    transition: 'width 0.4s ease',
  },
  quotaReset: {
    fontFamily: 'var(--font-mono)', fontSize: 10,
    color: 'var(--text-muted)', letterSpacing: '0.04em',
  },
}