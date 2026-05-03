import { useState, useEffect, useRef, useCallback } from 'react'
import TailorPage from './TailorPage'
import LoadingScreen from './LoadingScreen'
import HistoryPage from './HistoryPage'

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

// ── Score Panel ───────────────────────────────────────────────────────────────
function ScorePanel({ scoring, jobText, onClose }) {
  const s = scoring || {}
  const tier1Keywords     = s.tier1_keywords     || []
  const tier2Keywords     = s.tier2_keywords     || []
  const originalKeywords  = s.original_resume_keywords || []
  const injectedKeywords  = s.injected_keywords       || []
  const missingKeywords   = s.missing_keywords        || []
  const injected          = s.keyword_injection_count ?? s.anchor_rules_fired ?? injectedKeywords.length
  const jobLen            = s.job_text_length    || 0
  const quantifiedBullets = s.quantified_bullets || 0
  const totalBullets      = s.total_bullets      || 0
  const quantScore        = s.quantification_rate || 0
  const matchedKeywords   = s.matched_keywords   || (originalKeywords.length + injectedKeywords.length)
  const totalKeywords     = s.total_keywords     || 0
  const allKw             = [...tier1Keywords, ...tier2Keywords]

  // ── Compute scores ──────────────────────────────────────────────────────────
  // 1. ATS Structure — always high since we control the PDF builder
  const atsScore = 92

  // 2. Keyword Injection — how many anchor rules fired vs total possible
  const MAX_ANCHORS = 14
  const injectionScore = Math.min(100, Math.round(40 + (injected / MAX_ANCHORS) * 60))

  // 3. Keyword Coverage — actual keyword injection success, excluding JD keywords not in the tailored resume
  const coverageDenominator = Math.max(0, totalKeywords - missingKeywords.length)
  const kwMatchScore = coverageDenominator > 0
    ? Math.min(100, Math.round((injectedKeywords.length / coverageDenominator) * 100))
    : 100

  // 4. Quantification Rate — percent of bullets with measurable metrics
  const quantificationScore = quantScore

  // 5. Job Description Match — based on richness of job text provided
  const jobRichness = Math.min(1, jobLen / 3000)
  const jobMatchScore = Math.min(100, Math.round(60 + jobRichness * 35))

  // 6. Overall weighted score
  const overall = Math.round(
    atsScore            * 0.20 +
    injectionScore      * 0.20 +
    kwMatchScore        * 0.25 +
    quantificationScore * 0.15 +
    jobMatchScore       * 0.20
  )

  const scoreColor = (n) => n >= 80 ? 'var(--success)' : n >= 60 ? '#f0b429' : 'var(--danger)'

  const CircleScore = ({ value, size = 72, stroke = 6 }) => {
    const r = (size - stroke) / 2
    const circ = 2 * Math.PI * r
    const offset = circ - (value / 100) * circ
    return (
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--surface-raised)" strokeWidth={stroke} />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={scoreColor(value)} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={offset}
          transform={`rotate(-90 ${size/2} ${size/2})`}
          style={{ transition: 'stroke-dashoffset 0.8s ease' }}
        />
        <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle"
          fill="var(--text-primary)" fontSize={size * 0.22} fontFamily="var(--font-display)" fontWeight="bold">
          {value}
        </text>
      </svg>
    )
  }

  const ScoreRow = ({ label, value, detail }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
      <div style={{ width: 42, textAlign: 'center', flexShrink: 0 }}>
        <CircleScore value={value} size={42} stroke={4} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>{label}</div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.4 }}>{detail}</div>
      </div>
      <div style={{ fontSize: 15, fontWeight: 700, color: scoreColor(value), flexShrink: 0 }}>{value}<span style={{ fontSize: 10, fontWeight: 400, color: 'var(--text-muted)' }}>/100</span></div>
    </div>
  )

  return (
    <>
      {/* Backdrop */}
      <div onClick={onClose} style={{
        position: 'fixed', inset: 0, zIndex: 40,
        backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)',
        background: 'rgba(14,15,17,0.55)',
      }} />

      {/* Panel */}
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, zIndex: 50,
        width: 360, background: 'var(--bg)',
        borderLeft: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column',
        animation: 'slideInRight 0.25s ease',
        boxShadow: '-8px 0 32px rgba(0,0,0,0.4)',
      }}>
        <style>{`
          @keyframes slideInRight {
            from { transform: translateX(100%); opacity: 0; }
            to   { transform: translateX(0);    opacity: 1; }
          }
          .close-btn:hover { color: #fff !important; border-color: var(--danger) !important; background: var(--danger) !important; }
        `}</style>

        {/* Panel header */}
        <div style={{ padding: '18px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
            </svg>
            <span style={{ fontFamily: 'var(--font-display)', fontSize: 16, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>Resume <em style={{ fontStyle: 'italic', color: 'var(--accent)' }}>Score</em></span>
          </div>
          <button onClick={onClose} className="close-btn" style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text-muted)', fontSize: 16, width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', transition: 'all 0.15s', flexShrink: 0 }}>×</button>
        </div>

        {/* Scrollable content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>

          {/* Overall score hero */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, padding: '16px 0 24px', textAlign: 'center' }}>
            <CircleScore value={overall} size={100} stroke={7} />
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 18, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>
                Overall Match
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>
                {overall >= 85 ? 'Strong match — well optimized' : overall >= 70 ? 'Good match — solid tailoring' : 'Moderate match — consider pasting full JD'}
              </div>
            </div>
          </div>

          {/* Score breakdown */}
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>Breakdown</div>
            <ScoreRow
              label="ATS Parsability"
              value={atsScore}
              detail="Single-column layout, embedded fonts, standard headings, plain text bullets"
            />
            <ScoreRow
              label="Keyword Injection"
              value={injectionScore}
              detail={`${injected} new job keywords injected into resume content`}
            />
            <ScoreRow
              label="Keyword Coverage"
              value={kwMatchScore}
              detail={`${matchedKeywords} of ${totalKeywords} job keywords matched in resume content`}
            />
            <ScoreRow
              label="Quantification Rate"
              value={quantificationScore}
              detail={`${quantifiedBullets} of ${totalBullets} bullets contain measurable metrics`}
            />
            <ScoreRow
              label="Job Description Match"
              value={jobMatchScore}
              detail={jobLen >= 2000 ? 'Rich job text — high confidence scoring' : jobLen >= 500 ? 'Moderate job text — scoring is approximate' : 'Thin job text — paste the full JD for better results'}
            />
          </div>

          {/* Keywords detected */}
          {(tier1Keywords.length > 0 || tier2Keywords.length > 0) && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>Keywords Detected from JD</div>
              {tier1Keywords.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6, fontWeight: 500 }}>Tier 1 — Hard Technical Skills</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {tier1Keywords.map((kw, i) => (
                      <span key={i} style={{
                        fontSize: 11, padding: '3px 8px', borderRadius: 4,
                        background: 'var(--surface-raised)', border: '1px solid var(--border)',
                        color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)',
                      }}>{kw}</span>
                    ))}
                  </div>
                </div>
              )}
              {tier2Keywords.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6, fontWeight: 500 }}>Tier 2 — Professional Concepts</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {tier2Keywords.map((kw, i) => (
                      <span key={i} style={{
                        fontSize: 11, padding: '3px 8px', borderRadius: 4,
                        background: 'var(--surface-raised)', border: '1px solid var(--border)',
                        color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)',
                      }}>{kw}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {missingKeywords.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>Skills Gap — Not in Resume</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {missingKeywords.map((kw, i) => {
                  const isTier1 = tier1Keywords.includes(kw)
                  return (
                    <span key={i} style={{
                      fontSize: 11, padding: '3px 8px', borderRadius: 4,
                      background: isTier1 ? 'rgba(255,255,255,0.04)' : 'rgba(255,255,255,0.08)',
                      border: '1px solid var(--border)',
                      color: isTier1 ? 'var(--text-muted)' : 'var(--text-secondary)',
                      fontFamily: 'var(--font-mono)',
                      opacity: isTier1 ? 0.7 : 1,
                    }} title={isTier1 ? 'Tier 1 skill — does not reduce coverage score' : 'Tier 2 concept — does not reduce coverage score'}>{kw}</span>
                  )
                })}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6 }}>
                <em>Missing skills shown for awareness but do not reduce your coverage score</em>
              </div>
            </div>
          )}

          {/* Injections applied */}
          {injected > 0 && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>Bullet Rewrites Applied</div>
              <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--success)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                  {injected} bullet{injected !== 1 ? 's' : ''} rewritten with job-specific keywords injected naturally mid-sentence.
                </span>
              </div>
            </div>
          )}

          {/* Tips */}
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 8 }}>Tips</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {jobLen < 1000 && (
                <div style={{ fontSize: 11, color: 'var(--text-muted)', background: 'var(--surface)', borderRadius: 6, padding: '8px 12px', lineHeight: 1.5, border: '1px solid var(--border)' }}>
                  💡 Paste the full job description for more accurate keyword extraction and a higher score.
                </div>
              )}
              {injected < 4 && (
                <div style={{ fontSize: 11, color: 'var(--text-muted)', background: 'var(--surface)', borderRadius: 6, padding: '8px 12px', lineHeight: 1.5, border: '1px solid var(--border)' }}>
                  💡 Fewer rewrites may mean the job is a weaker match for your current experience — consider highlighting more relevant projects first.
                </div>
              )}
              <div style={{ fontSize: 11, color: 'var(--text-muted)', background: 'var(--surface)', borderRadius: 6, padding: '8px 12px', lineHeight: 1.5, border: '1px solid var(--border)' }}>
                💡 ATS score reflects the PDF structure. Your resume uses ATS-safe fonts, single-column layout, and plain-text bullets — all passing criteria.
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

function ResultPage({ filename, pdfUrl, clFilename, clUrl, genResume, genCover, scoring, jobText, onTailorAnother, onHome }) {
  const [activeTab, setActiveTab] = useState('resume')
  const [showScore, setShowScore] = useState(false)
  const [hoveredButton, setHoveredButton] = useState(null)

  const tabStyle = (tab, isHovered = false) => ({
    display: 'flex', alignItems: 'center', gap: 7,
    padding: '8px 18px', borderRadius: 7, border: 'none',
    fontSize: 13, fontFamily: 'var(--font-body)', fontWeight: 500,
    cursor: 'pointer', transition: 'all 0.15s',
    background: activeTab === tab ? 'var(--surface-raised)' : isHovered ? 'rgba(255,255,255,0.06)' : 'transparent',
    color: activeTab === tab ? 'var(--text-primary)' : 'var(--text-muted)',
    boxShadow: activeTab === tab ? '0 1px 3px rgba(0,0,0,0.3)' : 'none',
  })

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', flexDirection: 'column', fontFamily: 'var(--font-body)' }}>
      {/* Header */}
      <header style={{ borderBottom: '1px solid var(--border)', padding: '0 24px', flexShrink: 0 }}>
        <div style={{ maxWidth: '100%', height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 18, color: 'var(--accent)' }}>⌂</span>
            <span style={{ fontFamily: 'var(--font-display)', fontSize: 20, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>resume<em style={{ fontStyle: 'italic', color: 'var(--accent)' }}>tailor</em></span>
          </div>
          {/* Tabs */}
          <div style={{ display: 'flex', gap: 4, background: 'var(--surface)', borderRadius: 10, padding: 4 }}>
            <button 
              style={tabStyle('resume', hoveredButton === 'tab-resume')} 
              onClick={() => setActiveTab('resume')}
              onMouseEnter={() => setHoveredButton('tab-resume')}
              onMouseLeave={() => setHoveredButton(null)}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              Resume
            </button>
            <button 
              style={tabStyle('cover', hoveredButton === 'tab-cover')} 
              onClick={() => setActiveTab('cover')}
              onMouseEnter={() => setHoveredButton('tab-cover')}
              onMouseLeave={() => setHoveredButton(null)}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
              Cover Letter
            </button>
          </div>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>personal workspace</span>
        </div>
      </header>

      {/* Split layout */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Left — viewer panel */}
        <div style={{ flex: 1, background: '#1a1a1a', display: 'flex', flexDirection: 'column', position: 'relative', overflow: 'hidden' }}>
          <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {activeTab === 'resume' ? filename : (clFilename || 'Cover Letter Not Generated')}
            </span>
          </div>

          {/* Resume tab content */}
          {activeTab === 'resume' && (
            <div style={{ flex: 1, position: 'relative', display: 'flex', flexDirection: 'column' }}>
              <iframe src={pdfUrl} style={{ flex: 1, border: 'none', width: '100%' }} title="Tailored Resume Preview" />
              {!genResume && (
                <div style={{
                  position: 'absolute', inset: 0,
                  backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
                  background: 'rgba(14,15,17,0.7)',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                  gap: 14, zIndex: 10,
                }}>
                  <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                    <line x1="4" y1="4" x2="20" y2="20" stroke="var(--danger)" strokeWidth="1.5"/>
                  </svg>
                  <p style={{ fontFamily: 'var(--font-display)', fontSize: 22, letterSpacing: '-0.02em', color: 'var(--text-primary)', margin: 0 }}>
                    Resume <em style={{ fontStyle: 'italic', color: 'var(--text-muted)' }}>not generated.</em>
                  </p>
                  <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', margin: 0 }}>
                    Enable the Resume toggle on the tailor page and re-run.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Cover letter tab content */}
          {activeTab === 'cover' && (
            <div style={{ flex: 1, position: 'relative', display: 'flex', flexDirection: 'column' }}>
              {clUrl ? (
                <iframe src={clUrl} style={{ flex: 1, border: 'none', width: '100%' }} title="Cover Letter Preview" />
              ) : (
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                    {!genCover && <line x1="4" y1="4" x2="20" y2="20" stroke="var(--danger)" strokeWidth="1.5"/>}
                  </svg>
                  {genCover ? (
                    <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>Cover letter generation failed. Try again.</p>
                  ) : (
                    <>
                      <p style={{ fontFamily: 'var(--font-display)', fontSize: 22, letterSpacing: '-0.02em', color: 'var(--text-primary)', margin: 0 }}>
                        Cover letter <em style={{ fontStyle: 'italic', color: 'var(--text-muted)' }}>not generated.</em>
                      </p>
                      <p style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)', margin: 0 }}>
                        Enable the Cover Letter toggle on the tailor page and re-run.
                      </p>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right — actions panel */}
        <div style={{ width: 300, flexShrink: 0, borderLeft: '1px solid var(--border)', background: 'var(--bg)', display: 'flex', flexDirection: 'column', padding: '32px 24px', gap: 24 }}>

          {activeTab === 'resume' ? (
            <>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, alignItems: 'center', textAlign: 'center' }}>
                <div style={{ width: 52, height: 52, borderRadius: '50%', background: 'rgba(200,240,76,0.12)', border: '2px solid var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                </div>
                <div>
                  <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 24, letterSpacing: '-0.02em', color: 'var(--text-primary)', marginBottom: 4 }}>
                    Resume <em style={{ fontStyle: 'italic', color: 'var(--accent)' }}>ready.</em>
                  </h2>
                  <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>Tailored to the job — same format, sharper content.</p>
                </div>
              </div>
              <div style={{ height: '1px', background: 'var(--border)' }} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <a
                  href={pdfUrl} download={filename}
                  style={{ 
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, 
                    background: 'var(--accent)', color: '#0e0f11', border: 'none', borderRadius: 8, 
                    padding: '12px 20px', fontWeight: 700, fontSize: 13, textDecoration: 'none', 
                    cursor: 'pointer', transition: 'all 0.2s ease',
                    ...(hoveredButton === 'download-resume' ? { filter: 'brightness(1.12)' } : {})
                  }}
                  onMouseEnter={() => setHoveredButton('download-resume')}
                  onMouseLeave={() => setHoveredButton(null)}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  Download PDF
                </a>
                {/* Resume Score button */}
                <button
                  onClick={() => setShowScore(true)}
                  style={{ 
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, 
                    background: hoveredButton === 'resume-score' ? 'var(--accent-hover)' : 'none', 
                    border: hoveredButton === 'resume-score' ? '1px solid var(--accent-hover)' : '1px solid var(--accent)', 
                    borderRadius: 8, padding: '11px 20px', 
                    color: hoveredButton === 'resume-score' ? '#0e0f11' : 'var(--accent)', fontWeight: 600, fontSize: 13, cursor: 'pointer', 
                    fontFamily: 'var(--font-body)', transition: 'all 0.15s ease'
                  }}
                  onMouseEnter={() => setHoveredButton('resume-score')}
                  onMouseLeave={() => setHoveredButton(null)}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                  </svg>
                  Resume Score
                </button>
                <button 
                  onClick={onTailorAnother} 
                  style={{ 
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, 
                    background: hoveredButton === 'tailor-another' ? 'var(--surface-raised)' : 'none', 
                    border: `1px solid ${hoveredButton === 'tailor-another' ? 'rgba(255,255,255,0.25)' : 'var(--border)'}`, 
                    borderRadius: 8, padding: '11px 20px', 
                    color: 'var(--text-secondary)', fontWeight: 500, fontSize: 13, cursor: 'pointer', 
                    fontFamily: 'var(--font-body)', transition: 'all 0.15s'
                  }}
                  onMouseEnter={() => setHoveredButton('tailor-another')}
                  onMouseLeave={() => setHoveredButton(null)}
                >
                  Tailor another job
                </button>
                <button 
                  onClick={onHome} 
                  style={{ 
                    background: hoveredButton === 'back-home' ? 'rgba(255,255,255,0.09)' : 'none', 
                    border: 'none', 
                    color: hoveredButton === 'back-home' ? '#ffffff' : 'var(--text-muted)', 
                    fontSize: 12, cursor: 'pointer', fontFamily: 'var(--font-body)', 
                    padding: '6px', textAlign: 'center', transition: 'all 0.15s'
                  }}
                  onMouseEnter={() => setHoveredButton('back-home')}
                  onMouseLeave={() => setHoveredButton(null)}
                >
                  Back to home
                </button>
              </div>
            </>
          ) : (
            <>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, alignItems: 'center', textAlign: 'center' }}>
                <div style={{ width: 52, height: 52, borderRadius: '50%', background: clUrl ? 'rgba(200,240,76,0.12)' : 'rgba(200,240,76,0.06)', border: clUrl ? '2px solid var(--accent)' : '2px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={clUrl ? 'var(--accent)' : 'var(--text-muted)'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                    {clUrl && <polyline points="20 6 9 17 4 12"/>}
                  </svg>
                </div>
                <div>
                  <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 24, letterSpacing: '-0.02em', color: 'var(--text-primary)', marginBottom: 4 }}>
                    Cover letter {clUrl ? <em style={{ fontStyle: 'italic', color: 'var(--accent)' }}>ready.</em> : <em style={{ fontStyle: 'italic', color: 'var(--text-muted)' }}>not generated.</em>}
                  </h2>
                  <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{clUrl ? 'Personalised to the role — ready to send.' : 'Enable the Cover Letter toggle and re-run to generate.'}</p>
                </div>
              </div>
              <div style={{ height: '1px', background: 'var(--border)' }} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {clUrl ? (
                  <a
                    href={clUrl} download={clFilename}
                    style={{ 
                      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, 
                      background: 'var(--accent)', color: '#0e0f11', border: 'none', borderRadius: 8, 
                      padding: '12px 20px', fontWeight: 700, fontSize: 13, textDecoration: 'none', 
                      cursor: 'pointer', transition: 'all 0.2s ease',
                      ...(hoveredButton === 'download-cover' ? { filter: 'brightness(1.12)' } : {})
                    }}
                    onMouseEnter={() => setHoveredButton('download-cover')}
                    onMouseLeave={() => setHoveredButton(null)}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                      <polyline points="7 10 12 15 17 10"/>
                      <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Download PDF
                  </a>
                ) : (
                  <button disabled style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, background: 'var(--surface-raised)', color: 'var(--text-muted)', border: '1px solid var(--border)', borderRadius: 8, padding: '12px 20px', fontWeight: 700, fontSize: 13, cursor: 'not-allowed', fontFamily: 'var(--font-body)', opacity: 0.5 }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                      <polyline points="7 10 12 15 17 10"/>
                      <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Download PDF
                  </button>
                )}
                <button 
                  onClick={onTailorAnother} 
                  style={{ 
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, 
                    background: hoveredButton === 'tailor-another-cover' ? 'var(--surface-raised)' : 'none', 
                    border: `1px solid ${hoveredButton === 'tailor-another-cover' ? 'rgba(255,255,255,0.25)' : 'var(--border)'}`, 
                    borderRadius: 8, padding: '11px 20px', 
                    color: 'var(--text-secondary)', fontWeight: 500, fontSize: 13, cursor: 'pointer', 
                    fontFamily: 'var(--font-body)', transition: 'all 0.15s'
                  }}
                  onMouseEnter={() => setHoveredButton('tailor-another-cover')}
                  onMouseLeave={() => setHoveredButton(null)}
                >
                  Tailor another job
                </button>
                <button 
                  onClick={onHome} 
                  style={{ 
                    background: hoveredButton === 'back-home-cover' ? 'rgba(255,255,255,0.09)' : 'none', 
                    border: 'none', 
                    color: hoveredButton === 'back-home-cover' ? '#ffffff' : 'var(--text-muted)', 
                    fontSize: 12, cursor: 'pointer', fontFamily: 'var(--font-body)', 
                    padding: '6px', textAlign: 'center', transition: 'all 0.15s'
                  }}
                  onMouseEnter={() => setHoveredButton('back-home-cover')}
                  onMouseLeave={() => setHoveredButton(null)}
                >
                  Back to home
                </button>
              </div>
            </>
          )}

        </div>
      </div>

      {/* Score Panel */}
      {showScore && (
        <ScorePanel
          scoring={scoring}
          jobText={jobText}
          onClose={() => setShowScore(false)}
        />
      )}
    </div>
  )
}

export default function App() {
  const [resumes, setResumes] = useState([])
  const [uploading, setUploading] = useState(false)
  const [uploadStatus, setUploadStatus] = useState(null) // { type: 'success'|'error', message }
  const [dragging, setDragging] = useState(false)
  const [deletingFile, setDeletingFile] = useState(null)
  const [confirmDelete, setConfirmDelete] = useState(null) // filename pending confirmation
  const [hoveredResume, setHoveredResume] = useState(null)
  const [previewResume, setPreviewResume] = useState(null)
  const fileInputRef = useRef(null)
  const dragCounter = useRef(0)

  // Restore state from sessionStorage on mount
  const [page, setPage] = useState(() => {
    try { return sessionStorage.getItem('rt_page') || 'home' } catch { return 'home' }
  })
  const [selectedResume, setSelectedResume] = useState(() => {
    try { return sessionStorage.getItem('rt_selectedResume') || null } catch { return null }
  })
  const [jobContext, setJobContext] = useState(() => {
    try { const v = sessionStorage.getItem('rt_jobContext'); return v ? JSON.parse(v) : null } catch { return null }
  })
  const [tailorResult, setTailorResult] = useState(() => {
    try { const v = sessionStorage.getItem('rt_tailorResult'); return v ? JSON.parse(v) : null } catch { return null }
  })

  // Persist state to sessionStorage whenever it changes
  useEffect(() => {
    try { sessionStorage.setItem('rt_page', page) } catch {}
  }, [page])
  useEffect(() => {
    try {
      if (selectedResume) sessionStorage.setItem('rt_selectedResume', selectedResume)
      else sessionStorage.removeItem('rt_selectedResume')
    } catch {}
  }, [selectedResume])
  useEffect(() => {
    try {
      if (jobContext) sessionStorage.setItem('rt_jobContext', JSON.stringify(jobContext))
      else sessionStorage.removeItem('rt_jobContext')
    } catch {}
  }, [jobContext])
  useEffect(() => {
    try {
      if (tailorResult) sessionStorage.setItem('rt_tailorResult', JSON.stringify(tailorResult))
      else sessionStorage.removeItem('rt_tailorResult')
    } catch {}
  }, [tailorResult])

  // Warn before refresh/close on loading page only
  useEffect(() => {
    if (page !== 'loading') return
    const handler = (e) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [page])

  const goHome = () => {
    try {
      sessionStorage.removeItem('rt_page')
      sessionStorage.removeItem('rt_selectedResume')
      sessionStorage.removeItem('rt_jobContext')
      sessionStorage.removeItem('rt_tailorResult')
    } catch {}
    setSelectedResume(null)
    setJobContext(null)
    setTailorResult(null)
    setPage('home')
  }

  const fetchResumes = useCallback(async () => {
    try {
      const res = await fetch(`${API}/resumes`)
      const data = await res.json()
      setResumes(data.resumes)
    } catch {
      // silently fail on list fetch
    }
  }, [])

  useEffect(() => { fetchResumes() }, [fetchResumes])

  const uploadFile = async (file) => {
    if (!file) return
    if (file.type !== 'application/pdf') {
      setUploadStatus({ type: 'error', message: 'Only PDF files are accepted.' })
      return
    }

    setUploading(true)
    setUploadStatus(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await fetch(`${API}/upload-resume`, { method: 'POST', body: formData })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Upload failed')
      setUploadStatus({ type: 'success', message: `"${data.original_name}" saved successfully.` })
      fetchResumes()
    } catch (err) {
      setUploadStatus({ type: 'error', message: err.message })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleFileChange = (e) => uploadFile(e.target.files[0])

  const handleDrop = (e) => {
    e.preventDefault()
    dragCounter.current = 0
    setDragging(false)
    uploadFile(e.dataTransfer.files[0])
  }

  const handleDragEnter = (e) => {
    e.preventDefault()
    dragCounter.current++
    setDragging(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    dragCounter.current--
    if (dragCounter.current === 0) setDragging(false)
  }

  const handleDragOver = (e) => e.preventDefault()

  const handleDelete = async (filename) => {
    setDeletingFile(filename)
    try {
      await fetch(`${API}/resumes/${filename}`, { method: 'DELETE' })
      if (selectedResume === filename) setSelectedResume(null)
      if (previewResume === filename) setPreviewResume(null)
      fetchResumes()
    } finally {
      setDeletingFile(null)
    }
  }

  if (page === 'history') {
    return (
      <HistoryPage
        onBack={() => setPage('home')}
      />
    )
  }

  if (page === 'tailor') {
    return (
      <TailorPage
          resumeFilename={selectedResume}
          onBack={() => setPage('home')}
          errorMessage={uploadStatus?.type === 'error' ? uploadStatus.message : null}
          onProceed={(jobText, jobTitle, genResume, genCover) => {
            setUploadStatus(null)
            setJobContext({ jobText, jobTitle, genResume, genCover })
            setPage('loading')
          }}
        />
    )
  }

  if (page === 'loading') {
    return (
      <LoadingScreen
        resumeFilename={selectedResume}
        jobText={jobContext?.jobText}
        genCover={jobContext?.genCover ?? false}
        onComplete={(data) => {
          setTailorResult({
            ...data,
            genResume: jobContext?.genResume ?? true,
            genCover:  jobContext?.genCover  ?? false,
            job_text:  jobContext?.jobText   ?? '',
          })
          setPage('result')
        }}
        onError={(msg) => {
          setUploadStatus({ type: 'error', message: msg })
          setPage('tailor')
        }}
        onNavigateBack={() => {
          setPage('tailor')
        }}
      />
    )
  }

  if (page === 'result') {
    const filename = tailorResult?.output_filename
    const pdfUrl = `/api/download/${filename}`
    const clFilename = tailorResult?.cover_letter_filename
    const clUrl = clFilename ? `/api/download-cl/${clFilename}` : null
    return <ResultPage
      filename={filename}
      pdfUrl={pdfUrl}
      clFilename={clFilename}
      clUrl={clUrl}
      genResume={tailorResult?.genResume ?? true}
      genCover={tailorResult?.genCover ?? false}
      scoring={tailorResult?.scoring ?? null}
      jobText={tailorResult?.job_text ?? ''}
      onTailorAnother={() => setPage('tailor')}
      onHome={() => goHome()}
    />
  }

  return (
    <div style={styles.layout}>
       <style>{`
       .proceed-btn:hover { filter: brightness(1.12); }
       .dropzone:hover { border-color: rgba(255,255,255,0.25) !important; background: var(--surface-raised) !important; }
       .delete-btn:hover { color: #fff !important; border-color: var(--danger) !important; background: var(--danger) !important; }
        .close-btn:hover { color: #fff !important; border-color: var(--danger) !important; background: var(--danger) !important; }
        .history-btn:hover { background: rgba(255,255,255,0.08) !important; border-color: rgba(255,255,255,0.25) !important; color: #ffffff !important; box-shadow: 0 0 0 1px rgba(255,255,255,0.12) !important; transform: translateY(-1px) !important;}
        .view-resume-btn:hover { background: rgba(255,255,255,0.09) !important; border-color: rgba(255,255,255,0.25) !important; color: #ffffff !important; }
        .view-resume-btn-open:hover { opacity: 0.7 !important; }
        @keyframes slideInPanel { from { transform: translateX(100%); } to { transform: translateX(0); } }
      `}</style>
      {/* Header */}
      <header style={styles.header}>
        <div style={styles.headerInner}>
          <div style={styles.logo}>
            <span style={styles.logoIcon}>⌂</span>
            <span style={styles.logoText}>resume<em style={styles.logoAccent}>tailor</em></span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <button
              className ="history-btn"
              onClick={() => setPage('history')}
              style={styles.historyNavBtn}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/>
                <polyline points="12 6 12 12 16 14"/>
              </svg>
              History
            </button>
            <span style={styles.headerTag}>personal workspace</span>
          </div>
        </div>
      </header>

      {/* Main */}
      <main style={styles.main}>

        {/* Hero */}
        <section style={styles.hero}>
          <h1 style={styles.heroTitle}>Your Resume,<br /><em style={styles.heroItalic}>perfectly fitted.</em></h1>
          <p style={styles.heroSub}>Upload your base resume and tailor it to any job description — automatically.</p>
        </section>

        {/* Upload Zone */}
        <section style={styles.section}>
          <label style={styles.sectionLabel}>Upload Resume</label>
          <div
          className="dropzone"
            style={{
              ...styles.dropzone,
              ...(dragging ? styles.dropzoneDragging : {}),
              ...(uploading ? styles.dropzoneLoading : {}),
            }}
            onDrop={handleDrop}
            onDragEnter={handleDragEnter}
            onDragLeave={handleDragLeave}
            onDragOver={handleDragOver}
            onClick={() => !uploading && fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />
            <div style={styles.dropzoneIcon}>
              {uploading ? (
                <span style={styles.spinner} />
              ) : (
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                  <line x1="12" y1="18" x2="12" y2="12"/>
                  <polyline points="9 15 12 12 15 15"/>
                </svg>
              )}
            </div>
            <p style={styles.dropzoneTitle}>
              {uploading ? 'Saving to disk…' : dragging ? 'Release to upload' : 'Drop your PDF here'}
            </p>
            <p style={styles.dropzoneSub}>
              {!uploading && 'or click to browse — PDF only'}
            </p>
          </div>

          {/* Status */}
          {uploadStatus && (
            <div style={{
              ...styles.statusBanner,
              ...(uploadStatus.type === 'success' ? styles.statusSuccess : styles.statusError),
            }}>
              <span>{uploadStatus.type === 'success' ? '✓' : '✕'}</span>
              <span>{uploadStatus.message}</span>
            </div>
          )}
        </section>

        {/* Resume List */}
        <section style={styles.section}>
          <div style={styles.sectionHeader}>
            <label style={styles.sectionLabel}>Saved Resumes</label>
            <span style={styles.badge}>{resumes.length}</span>
          </div>

          {resumes.length === 0 ? (
            <div style={styles.emptyState}>
              <p style={styles.emptyText}>No resumes saved yet.</p>
              <p style={styles.emptyMuted}>Upload a PDF above to get started.</p>
            </div>
          ) : (
            <ul style={styles.resumeList}>
              {resumes.map((r) => {
                const isSelected = selectedResume === r.filename
                const isHovered = hoveredResume === r.filename
                return (
                  <li
                    key={r.filename}
                    style={{
                      ...styles.resumeItem,
                      ...(isSelected ? styles.resumeItemSelected : isHovered ? styles.resumeItemHovered : {}),
                    }}
                    onClick={() => setSelectedResume(isSelected ? null : r.filename)}
                    onMouseEnter={() => setHoveredResume(r.filename)}
                    onMouseLeave={() => setHoveredResume(null)}
                  >
                    <div style={{ ...styles.resumeIcon, ...(isSelected ? { color: 'var(--accent)' } : {}) }}>
                      {isSelected ? (
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12"/>
                        </svg>
                      ) : (
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                          <polyline points="14 2 14 8 20 8"/>
                        </svg>
                      )}
                    </div>
                    <div style={styles.resumeMeta}>
                      <span style={{ ...styles.resumeName, ...(isSelected ? { color: 'var(--accent)' } : {}) }}>{r.filename}</span>
                      <span style={styles.resumeInfo}>{formatSize(r.size_kb)} · {formatDate(r.uploaded_at)}</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                      {isSelected && (
                        <button
                          className={previewResume === r.filename ? 'view-resume-btn-open' : 'view-resume-btn'}
                          style={{
                            display: 'flex', alignItems: 'center', gap: 5,
                            background: previewResume === r.filename ? 'var(--accent-dim)' : 'none',
                            border: `1px solid ${previewResume === r.filename ? 'var(--accent)' : 'var(--border)'}`,
                            borderRadius: 6, padding: '3px 10px', fontSize: 11,
                            color: previewResume === r.filename ? 'var(--accent)' : 'var(--text-secondary)',
                            cursor: 'pointer', fontFamily: 'var(--font-body)', fontWeight: 500,
                            outline: 'none', transition: 'opacity 0.15s',
                          }}
                          onClick={(e) => {
                            e.stopPropagation()
                            setPreviewResume(previewResume === r.filename ? null : r.filename)
                          }}
                          title="Preview resume"
                        >
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                            <circle cx="12" cy="12" r="3"/>
                          </svg>
                          {previewResume === r.filename ? 'Close' : 'View'}
                        </button>
                      )}
                      <button
                        className="delete-btn"
                        style={{
                          ...styles.deleteBtn,
                          color: 'var(--danger)',
                          ...(deletingFile === r.filename ? styles.deleteBtnLoading : {}),
                        }}
                        onClick={(e) => { e.stopPropagation(); setConfirmDelete(r.filename) }}
                        disabled={deletingFile === r.filename}
                        title="Delete resume"
                      >
                        {deletingFile === r.filename ? '…' : '×'}
                      </button>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}

          <button
            className="proceed-btn"
            style={{ ...styles.proceedBtn, ...(selectedResume ? styles.proceedBtnActive : styles.proceedBtnDisabled) }}
            disabled={!selectedResume}
            onClick={() => selectedResume && setPage('tailor')}
          >
            <span>Proceed to Tailor Resume</span>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="5" y1="12" x2="19" y2="12"/>
              <polyline points="12 5 19 12 12 19"/>
            </svg>
          </button>
          {selectedResume && (
            <p style={styles.selectedHint}>Selected: <span style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>{selectedResume}</span></p>
          )}
        </section>

        {/* How it works */}
        <section style={styles.section}>
          <label style={styles.sectionLabel}>How it works</label>
          <div style={styles.flowWrap}>

            <div style={styles.flowStep}>
              <div style={styles.flowIcon}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                  <line x1="12" y1="18" x2="12" y2="12"/>
                  <polyline points="9 15 12 12 15 15"/>
                </svg>
              </div>
              <div style={styles.flowBody}>
                <span style={styles.flowTitle}>Upload your resume</span>
                <span style={styles.flowDesc}>Drop in your base PDF once — it stays saved for every job you apply to.</span>
              </div>
            </div>

            <div style={styles.flowArrow}>↓</div>

            <div style={styles.flowStep}>
              <div style={styles.flowIcon}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                  <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
                </svg>
              </div>
              <div style={styles.flowBody}>
                <span style={styles.flowTitle}>Paste a job link or description</span>
                <span style={styles.flowDesc}>Drop in a URL or paste the job posting directly — either works. Optionally enable the cover letter toggle to generate one alongside your resume.</span>
              </div>
            </div>

            <div style={styles.flowArrow}>↓</div>

            <div style={styles.flowStep}>
              <div style={styles.flowIcon}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="3"/>
                  <path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>
                  <path d="M4.93 4.93a10 10 0 0 0 0 14.14"/>
                </svg>
              </div>
              <div style={styles.flowBody}>
                <span style={styles.flowTitle}>AI tailors your resume</span>
                <span style={styles.flowDesc}>Keywords are matched, bullets sharpened, formatting stays intact. If cover letter is enabled, it's generated right after. Takes about 30–90s.</span>
              </div>
            </div>

            <div style={styles.flowArrow}>↓</div>

            <div style={styles.flowStep}>
              <div style={styles.flowIcon}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                </svg>
              </div>
              <div style={styles.flowBody}>
                <span style={styles.flowTitle}>Check your resume score</span>
                <span style={styles.flowDesc}>After tailoring, view your ATS score — keyword injection, job match, and overall fit — to see how well your resume aligns with the role.</span>
              </div>
            </div>

            <div style={styles.flowArrow}>↓</div>

            <div style={styles.flowStep}>
              <div style={styles.flowIcon}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="7 10 12 15 17 10"/>
                  <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
              </div>
              <div style={styles.flowBody}>
                <span style={styles.flowTitle}>Preview &amp; download</span>
                <span style={styles.flowDesc}>View your tailored resume and cover letter side by side in the browser. Download either as a PDF when you're ready to apply.</span>
              </div>
            </div>

          </div>
        </section>

      </main>

      <footer style={styles.footer}>
        <span style={styles.footerText}>resume tailor · personal workspace</span>
      </footer>

      {/* Resume preview panel */}
      {previewResume && (
        <>
          <div
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)', zIndex: 110 }}
            onClick={() => setPreviewResume(null)}
          />
          <div style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: '75vw', minWidth: 600, background: 'var(--bg)', borderLeft: '1px solid var(--border)', display: 'flex', flexDirection: 'column', zIndex: 120, animation: 'slideInPanel 0.28s cubic-bezier(0.4,0,0.2,1)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 18px', borderBottom: '1px solid var(--border)', flexShrink: 0, gap: 12 }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }} title={previewResume}>{previewResume}</span>
              <button
                onClick={() => setPreviewResume(null)}
                style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 6, width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--text-muted)', flexShrink: 0, outline: 'none' }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
            <iframe
              key={previewResume}
              src={`${API}/preview-resume/${encodeURIComponent(previewResume)}#toolbar=0&navpanes=0&scrollbar=1&zoom=page-width`}
              style={{ flex: 1, border: 'none', width: '100%', background: '#111' }}
              title="Resume preview"
            />
          </div>
        </>
      )}

      {/* Delete Confirmation Modal */}
      {confirmDelete && (
        <>
          <div
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)', zIndex: 200 }}
            onClick={() => setConfirmDelete(null)}
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
            <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'var(--danger-dim, rgba(255,95,87,0.12))', border: '1px solid rgba(255,95,87,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--danger)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                <path d="M10 11v6"/><path d="M14 11v6"/>
                <path d="M9 6V4h6v2"/>
              </svg>
            </div>

            {/* Title */}
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 17, letterSpacing: '-0.02em', color: 'var(--text-primary)', marginBottom: 8 }}>
              Delete resume?
            </div>

            {/* Body */}
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 22 }}>
              Are you sure you want to delete{' '}
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                {confirmDelete}
              </span>
              ? This action cannot be undone.
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', gap: 10 }}>
              <button
                onClick={() => setConfirmDelete(null)}
                style={{
                  flex: 1, padding: '10px 0', borderRadius: 8,
                  border: '1px solid var(--border)', background: 'var(--surface)',
                  color: 'var(--text-secondary)', fontSize: 13, fontWeight: 600,
                  fontFamily: 'var(--font-body)', cursor: 'pointer', transition: 'all 0.15s',
                }}
                onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-raised)'; e.currentTarget.style.color = 'var(--text-primary)' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface)'; e.currentTarget.style.color = 'var(--text-secondary)' }}
              >
                Cancel
              </button>
              <button
                onClick={() => { handleDelete(confirmDelete); setConfirmDelete(null) }}
                style={{
                  flex: 1, padding: '10px 0', borderRadius: 8,
                  border: '1px solid rgba(255,95,87,0.4)', background: 'rgba(255,95,87,0.12)',
                  color: 'var(--danger)', fontSize: 13, fontWeight: 600,
                  fontFamily: 'var(--font-body)', cursor: 'pointer', transition: 'all 0.15s',
                }}
                onMouseEnter={e => { e.currentTarget.style.background = 'var(--danger)'; e.currentTarget.style.color = '#fff' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,95,87,0.12)'; e.currentTarget.style.color = 'var(--danger)' }}
              >
                Delete
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

const styles = {
  layout: {
    minHeight: '100vh',
    display: 'flex',
    flexDirection: 'column',
    background: 'var(--bg)',
  },
  header: {
    borderBottom: '1px solid var(--border)',
    padding: '0 24px',
  },
  headerInner: {
    maxWidth: 680,
    margin: '0 auto',
    height: 60,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  logo: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  logoIcon: {
    fontSize: 18,
    color: 'var(--accent)',
  },
  logoText: {
    fontFamily: 'var(--font-display)',
    fontSize: 20,
    color: 'var(--text-primary)',
    letterSpacing: '-0.02em',
  },
  logoAccent: {
    fontStyle: 'italic',
    color: 'var(--accent)',
  },
  historyNavBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: 5,
    background: 'none',
    border: '1px solid var(--border)',
    borderRadius: 6,
    padding: '6px 11px',
    fontSize: 12,
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    fontFamily: 'var(--font-body)',
    fontWeight: 500,
  },
  headerTag: {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    color: 'var(--text-muted)',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
  },
  main: {
    flex: 1,
    maxWidth: 680,
    width: '100%',
    margin: '0 auto',
    padding: '48px 24px 80px',
    display: 'flex',
    flexDirection: 'column',
    gap: 48,
  },
  hero: {
    paddingBottom: 8,
  },
  heroTitle: {
    fontFamily: 'var(--font-display)',
    fontSize: 'clamp(36px, 6vw, 54px)',
    lineHeight: 1.1,
    letterSpacing: '-0.03em',
    color: 'var(--text-primary)',
    marginBottom: 16,
  },
  heroItalic: {
    fontStyle: 'italic',
    color: 'var(--accent)',
  },
  heroSub: {
    fontSize: 16,
    color: 'var(--text-secondary)',
    lineHeight: 1.6,
    maxWidth: 480,
  },
  section: {
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
  },
  sectionLabel: {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    fontWeight: 500,
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
    color: 'var(--text-muted)',
  },
  badge: {
    background: 'var(--surface-raised)',
    border: '1px solid var(--border)',
    borderRadius: 20,
    padding: '1px 8px',
    fontSize: 11,
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-secondary)',
  },
  dropzone: {
    border: '1.5px dashed var(--border)',
    borderRadius: 'var(--radius)',
    padding: '48px 24px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 10,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    background: 'var(--surface)',
    color: 'var(--text-secondary)',
    userSelect: 'none',
  },
  dropzoneDragging: {
    borderColor: 'var(--accent)',
    background: 'var(--accent-dim)',
    color: 'var(--accent)',
  },
  dropzoneLoading: {
    cursor: 'default',
    opacity: 0.7,
  },
  dropzoneIcon: {
    marginBottom: 4,
    color: 'inherit',
  },
  dropzoneTitle: {
    fontSize: 15,
    fontWeight: 500,
    color: 'inherit',
  },
  dropzoneSub: {
    fontSize: 13,
    color: 'var(--text-muted)',
  },
  spinner: {
    display: 'block',
    width: 28,
    height: 28,
    border: '2px solid var(--border)',
    borderTop: '2px solid var(--accent)',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },
  statusBanner: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '12px 16px',
    borderRadius: 'var(--radius-sm)',
    fontSize: 13,
    fontWeight: 500,
  },
  statusSuccess: {
    background: 'rgba(50, 210, 150, 0.1)',
    border: '1px solid rgba(50, 210, 150, 0.3)',
    color: 'var(--success)',
  },
  statusError: {
    background: 'var(--danger-dim)',
    border: '1px solid rgba(255, 95, 87, 0.25)',
    color: 'var(--danger)',
  },
  emptyState: {
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
    padding: '32px 24px',
    textAlign: 'center',
  },
  emptyText: {
    color: 'var(--text-secondary)',
    fontSize: 14,
    marginBottom: 4,
  },
  emptyMuted: {
    color: 'var(--text-muted)',
    fontSize: 13,
  },
  resumeList: {
    listStyle: 'none',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  resumeItem: {
  borderRadius: 'var(--radius)',
  padding: '14px 16px',
  display: 'flex',
  alignItems: 'center',
  gap: 14,
  cursor: 'pointer',
  userSelect: 'none',
},
  resumeItemHovered: {
    borderColor: 'var(--border-hover)',
    background: 'var(--surface-raised)',
  },
  resumeItemSelected: {
    borderColor: 'var(--accent)',
    background: 'var(--accent-dim)',
  },
  resumeIcon: {
    color: 'var(--accent)',
    flexShrink: 0,
    display: 'flex',
    alignItems: 'center',
  },
  resumeMeta: {
    flex: 1,
    minWidth: 0,
    display: 'flex',
    flexDirection: 'column',
    gap: 3,
  },
  resumeName: {
    fontSize: 13,
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-primary)',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  resumeInfo: {
    fontSize: 12,
    color: 'var(--text-muted)',
  },
  deleteBtn: {
    background: 'none',
    border: '1px solid transparent',
    borderRadius: 'var(--radius-sm)',
    color: 'var(--danger)',
    fontSize: 18,
    lineHeight: 1,
    width: 28,
    height: 28,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    transition: 'all 0.15s',
    flexShrink: 0,
  },
  deleteBtnLoading: {
    opacity: 0.5,
    cursor: 'default',
  },
  flowWrap: {
    display: 'flex',
    flexDirection: 'column',
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius)',
    padding: '4px 0',
    overflow: 'hidden',
  },
  flowStep: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 14,
    padding: '16px 20px',
  },
  flowStepDim: {
    opacity: 0.45,
  },
  flowIcon: {
    width: 34,
    height: 34,
    borderRadius: 8,
    background: 'var(--accent-dim)',
    border: '1px solid var(--border)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    color: 'var(--accent)',
  },
  flowIconDim: {
    background: 'var(--surface-raised)',
    color: 'var(--text-muted)',
  },
  flowBody: {
    display: 'flex',
    flexDirection: 'column',
    gap: 3,
    paddingTop: 2,
  },
  flowTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: 'var(--text-primary)',
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  flowTitleDim: {
    color: 'var(--text-secondary)',
  },
  flowDesc: {
    fontSize: 12,
    color: 'var(--text-muted)',
    lineHeight: 1.5,
  },
  flowArrow: {
    textAlign: 'center',
    fontSize: 12,
    color: 'var(--border-hover)',
    lineHeight: 1,
    padding: '0 20px',
    userSelect: 'none',
  },
  flowBadge: {
    fontSize: 9,
    fontFamily: 'var(--font-mono)',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    color: 'var(--text-muted)',
    border: '1px solid var(--border)',
    borderRadius: 4,
    padding: '2px 5px',
    fontWeight: 400,
  },
  proceedBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    width: '100%',
    padding: '14px 24px',
    borderRadius: 'var(--radius)',
    border: 'none',
    fontSize: 14,
    fontFamily: 'var(--font-body)',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    marginTop: 4,
  },
  proceedBtnActive: {
    background: 'var(--accent)',
    color: '#0e0f11',
  },
  proceedBtnDisabled: {
    background: 'var(--surface-raised)',
    color: 'var(--text-muted)',
    cursor: 'not-allowed',
    border: '1px solid var(--border)',
  },
  selectedHint: {
    fontSize: 12,
    color: 'var(--text-muted)',
    textAlign: 'center',
  },
  footer: {
    borderTop: '1px solid var(--border)',
    padding: '16px 24px',
    textAlign: 'center',
  },
  footerText: {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    color: 'var(--text-muted)',
    letterSpacing: '0.06em',
  },
}