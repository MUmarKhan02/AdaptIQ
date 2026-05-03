import { useState, useEffect, useRef } from 'react'

const RESUME_STAGES = [
  { at: 0,   label: 'Fetching job posting…',      detail: 'Reading the page content' },
  { at: 12,  label: 'Parsing job requirements…',   detail: 'Identifying skills & keywords' },
  { at: 24,  label: 'Extracting resume content…',  detail: 'Reading your PDF' },
  { at: 36,  label: 'Analysing alignment…',        detail: 'Matching your experience to the role' },
  { at: 50,  label: 'Generating tailored resume…', detail: 'AI is rewriting your content' },
  { at: 62,  label: 'Refining language…',          detail: 'Polishing keywords & phrasing' },
  { at: 74,  label: 'Almost there…',               detail: 'Finalising your resume' },
  { at: 88,  label: 'Wrapping up…',                detail: 'Saving output' },
]

const COVER_STAGES = [
  { at: 0,   label: 'Fetching job posting…',      detail: 'Reading the page content' },
  { at: 10,  label: 'Parsing job requirements…',   detail: 'Identifying skills & keywords' },
  { at: 20,  label: 'Extracting resume content…',  detail: 'Reading your PDF' },
  { at: 30,  label: 'Analysing alignment…',        detail: 'Matching your experience to the role' },
  { at: 40,  label: 'Generating tailored resume…', detail: 'AI is rewriting your content' },
  { at: 50,  label: 'Resume ready — writing cover letter…', detail: 'Starting cover letter generation' },
  { at: 60,  label: 'Crafting opening…',           detail: 'Personalising the introduction' },
  { at: 70,  label: 'Writing body paragraphs…',    detail: 'Aligning your experience to the role' },
  { at: 80,  label: 'Polishing closing…',          detail: 'Finalising tone & call to action' },
  { at: 90,  label: 'Saving cover letter…',        detail: 'Building your PDF' },
  { at: 96,  label: 'Almost done…',                detail: 'Finishing up' },
]

function getStage(stages, pct) {
  let current = stages[0]
  for (const s of stages) {
    if (pct >= s.at) current = s
    else break
  }
  return current
}

function CircleProgress({ percent }) {
  const r = 88
  const circ = 2 * Math.PI * r
  const offset = circ - (percent / 100) * circ
  return (
    <div style={styles.circleWrap}>
      <div style={{ ...styles.ring, ...styles.ring1 }} />
      <div style={{ ...styles.ring, ...styles.ring2 }} />
      <div style={{ ...styles.ring, ...styles.ring3 }} />
      <svg width="220" height="220" viewBox="0 0 220 220" style={styles.svg}>
        <circle cx="110" cy="110" r={r} fill="none" stroke="var(--surface-raised)" strokeWidth="6" />
        <circle
          cx="110" cy="110" r={r} fill="none"
          stroke="var(--accent)" strokeWidth="6" strokeLinecap="round"
          strokeDasharray={circ} strokeDashoffset={offset}
          transform="rotate(-90 110 110)"
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
      </svg>
      <div style={styles.circleCenter}>
        <span style={styles.percentNum}>{Math.round(percent)}</span>
        <span style={styles.percentSign}>%</span>
      </div>
    </div>
  )
}

export default function LoadingScreen({ resumeFilename, jobText, genCover, onComplete, onError, onNavigateBack }) {
  const [progress, setProgress]   = useState(0)
  const [done, setDone]           = useState(false)
  const [elapsed, setElapsed]     = useState(0)
  const [finalTime, setFinalTime] = useState(null)

  const progressRef  = useRef(0)
  const finishedRef  = useRef(false)
  const hasFired     = useRef(false)
  const animFrameRef = useRef(null)
  const abortRef     = useRef(null)
  const startTimeRef = useRef(null)

  const stages = genCover ? COVER_STAGES : RESUME_STAGES
  const stage  = getStage(stages, progress)

  // Smooth animation toward a target percentage
  const animateTo = (targetPct) => {
    if (animFrameRef.current) {
      clearInterval(animFrameRef.current)
      animFrameRef.current = null
    }
    const start    = progressRef.current
    const delta    = targetPct - start
    if (delta <= 0) return
    const duration = Math.max(400, Math.min(800, delta * 20))
    const fps      = 60
    const interval = 1000 / fps
    const steps    = Math.ceil(duration / interval)
    let step = 0
    animFrameRef.current = setInterval(() => {
      step++
      const eased   = start + delta * (step / steps)
      const clamped = Math.min(eased, targetPct)
      progressRef.current = clamped
      setProgress(clamped)
      if (step >= steps) {
        clearInterval(animFrameRef.current)
        animFrameRef.current = null
      }
    }, interval)
  }

  // Elapsed timer
  useEffect(() => {
    if (done) return
    const t = setInterval(() => setElapsed(s => s + 1), 1000)
    return () => clearInterval(t)
  }, [done])

  useEffect(() => {
    if (hasFired.current) return
    hasFired.current = true

    // Time-based easing ticker:
    // Targets ~92% (resume) or ~93% (cover) over an expected duration of 55s.
    // Uses an ease-out curve: progress = cap * (1 - e^(-t/tau))
    // This moves quickly at first and decelerates near the cap — no hard stall.
    //
    // tau controls the curve shape. Chosen so that at t=55s we're at ~92–93%:
    //   cap * (1 - e^(-55/tau)) = 0.92 * cap  →  tau = -55 / ln(0.08) ≈ 22
    // cap: how high the bar climbs before the API responds
    // tau: controls the ease-out curve shape.
    //   Formula: progress = cap * (1 - e^(-t/tau))
    //   Tuned so the bar reaches ~90% just as the expected completion time arrives:
    //     Resume only  → ~20s  → tau ≈ 8
    //     With cover   → ~55s  → tau ≈ 22
    const cap = genCover ? 93 : 92
    const tau = genCover ? 5 : 8

    startTimeRef.current = Date.now()

    const ticker = setInterval(() => {
      if (finishedRef.current) { clearInterval(ticker); return }
      const elapsed = (Date.now() - startTimeRef.current) / 1000
      const next = cap * (1 - Math.exp(-elapsed / tau))
      // Never let it go backwards (defensive)
      if (next > progressRef.current) {
        progressRef.current = next
        setProgress(next)
      }
    }, 120)

    // Handle page refresh — abort the request and go back
    const handleBeforeUnload = (e) => {
      if (finishedRef.current) return
      e.preventDefault()
      e.returnValue = ''
      if (abortRef.current) abortRef.current.abort()
      clearInterval(ticker)
      if (animFrameRef.current) clearInterval(animFrameRef.current)
      if (onNavigateBack) onNavigateBack()
    }
    window.addEventListener('beforeunload', handleBeforeUnload)

    async function run() {
      try {
        abortRef.current = new AbortController()

        const res = await fetch('/api/tailor-resume', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            resume_filename: resumeFilename,
            job_text: jobText,
            gen_cover: genCover ?? false,
          }),
          signal: abortRef.current.signal,
        })

        if (!res.ok) {
          const text = await res.text()
          throw new Error(`Server error (${res.status}): ${text.slice(0, 200)}`)
        }

        const data = await res.json()

        if (!data.success) {
          throw new Error(data.detail || data.message || 'Something went wrong.')
        }

        // Success — animate to 100% then hand off
        clearInterval(ticker)
        finishedRef.current = true
        animateTo(100)
        setTimeout(() => {
          setElapsed(e => { setFinalTime(e); return e })
          setDone(true)
          setTimeout(() => onComplete(data), 900)
        }, 800)

      } catch (err) {
        clearInterval(ticker)
        finishedRef.current = true
        if (animFrameRef.current) clearInterval(animFrameRef.current)
        if (err.name === 'AbortError') return
        onError(err.message || 'Something went wrong.')
      }
    }

    run()

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
      clearInterval(ticker)
      if (animFrameRef.current) clearInterval(animFrameRef.current)
      if (abortRef.current) abortRef.current.abort()
    }
  }, [])

  const displayStages = genCover ? COVER_STAGES : RESUME_STAGES
  const displayLabel  = done
    ? (genCover ? 'Resume & cover letter ready.' : 'Resume ready.')
    : stage.label
  const displayDetail = done ? 'Opening your results…' : stage.detail

  return (
    <div style={styles.layout}>
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
        <CircleProgress percent={progress} />

        <div style={styles.textBlock}>
          <p style={styles.stageLabel}>{displayLabel}</p>
          <p style={styles.stageDetail}>{displayDetail}</p>
          <p style={styles.elapsedText}>
            {done
              ? `Completed in ${finalTime}s`
              : elapsed < 5 ? 'Starting up…' : `${elapsed}s elapsed`}
          </p>
        </div>

        <div style={styles.stageList}>
          {displayStages.map((s, i) => {
            const isActive = stage.at === s.at && !done
            const isPast   = progress > s.at && stage.at !== s.at
            return (
              <div key={i} style={styles.stageRow}>
                <div style={{
                  ...styles.stageDot,
                  ...(isPast || done ? styles.stageDotDone : {}),
                  ...(isActive ? styles.stageDotActive : {}),
                }} />
                <span style={{
                  ...styles.stageText,
                  ...(isActive ? styles.stageTextActive : {}),
                  ...(isPast || done ? styles.stageTextDone : {}),
                }}>{s.label}</span>
              </div>
            )
          })}
        </div>
      </main>
    </div>
  )
}

const styles = {
  layout:      { minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' },
  header:      { borderBottom: '1px solid var(--border)', padding: '0 24px' },
  headerInner: { maxWidth: 680, margin: '0 auto', height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  logo:        { display: 'flex', alignItems: 'center', gap: 8 },
  logoIcon:    { fontSize: 18, color: 'var(--accent)' },
  logoText:    { fontFamily: 'var(--font-display)', fontSize: 20, color: 'var(--text-primary)', letterSpacing: '-0.02em' },
  logoAccent:  { fontStyle: 'italic', color: 'var(--accent)' },
  headerTag:   { fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' },
  main:        { flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 40, padding: '60px 24px' },
  circleWrap:  { position: 'relative', width: 220, height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center' },
  ring:        { position: 'absolute', borderRadius: '50%', border: '1.5px solid var(--accent)', animation: 'pulse-ring 2.4s ease-out infinite' },
  ring1:       { width: 220, height: 220, opacity: 0.25, animationDelay: '0s' },
  ring2:       { width: 260, height: 260, opacity: 0.15, animationDelay: '0.6s' },
  ring3:       { width: 300, height: 300, opacity: 0.08, animationDelay: '1.2s' },
  svg:         { position: 'absolute', top: 0, left: 0 },
  circleCenter:{ position: 'relative', display: 'flex', alignItems: 'baseline', gap: 2, zIndex: 1 },
  percentNum:  { fontFamily: 'var(--font-display)', fontSize: 64, lineHeight: 1, color: 'var(--text-primary)', letterSpacing: '-0.04em' },
  percentSign: { fontFamily: 'var(--font-mono)', fontSize: 22, color: 'var(--accent)', fontWeight: 500 },
  textBlock:   { textAlign: 'center', display: 'flex', flexDirection: 'column', gap: 6 },
  stageLabel:  { fontSize: 18, fontWeight: 600, color: 'var(--text-primary)', fontFamily: 'var(--font-body)' },
  stageDetail: { fontSize: 13, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' },
  elapsedText: { fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', letterSpacing: '0.04em', marginTop: 4 },
  stageList:   { display: 'flex', flexDirection: 'column', gap: 10, minWidth: 280 },
  stageRow:    { display: 'flex', alignItems: 'center', gap: 10 },
  stageDot:    { width: 6, height: 6, borderRadius: '50%', background: 'var(--surface-raised)', border: '1px solid var(--border)', flexShrink: 0, transition: 'all 0.3s' },
  stageDotActive: { background: 'var(--accent)', border: '1px solid var(--accent)', boxShadow: '0 0 6px var(--accent)' },
  stageDotDone:   { background: 'var(--text-muted)', border: '1px solid var(--text-muted)' },
  stageText:      { fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', transition: 'color 0.3s' },
  stageTextActive:{ color: 'var(--accent)' },
  stageTextDone:  { color: 'var(--text-secondary)', textDecoration: 'line-through', textDecorationColor: 'var(--text-muted)' },
}