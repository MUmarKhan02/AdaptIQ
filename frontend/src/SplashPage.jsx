import { useEffect, useRef, useState } from 'react'

export default function SplashPage({ onEnter }) {
  const canvasRef = useRef(null)
  const animRef   = useRef(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 80)
    return () => clearTimeout(t)
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')

    const resize = () => {
      canvas.width  = window.innerWidth
      canvas.height = window.innerHeight
    }
    resize()
    window.addEventListener('resize', resize)

    const orbs = Array.from({ length: 7 }, (_, i) => ({
      x:       Math.random() * window.innerWidth,
      y:       Math.random() * window.innerHeight,
      r:       260 + Math.random() * 200,
      vx:      (Math.random() - 0.5) * 0.35,
      vy:      (Math.random() - 0.5) * 0.35,
      alpha:   0,
      targetA: 0.10 + Math.random() * 0.13,
      phase:   Math.random() * Math.PI * 2,
      speed:   0.004 + Math.random() * 0.006,
      hue:     i % 2 === 0 ? '108,99,255' : '139,92,246',
    }))

    let frame = 0
    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      frame++
      orbs.forEach(o => {
        o.x += o.vx
        o.y += o.vy
        if (o.x < -o.r) o.x = canvas.width + o.r
        if (o.x > canvas.width + o.r)  o.x = -o.r
        if (o.y < -o.r) o.y = canvas.height + o.r
        if (o.y > canvas.height + o.r) o.y = -o.r

        const pulse  = Math.sin(frame * o.speed + o.phase)
        const alpha  = o.targetA * (0.55 + 0.45 * pulse)
        const radius = o.r * (0.92 + 0.08 * pulse)

        const grad = ctx.createRadialGradient(o.x, o.y, 0, o.x, o.y, radius)
        grad.addColorStop(0,   `rgba(${o.hue}, ${alpha})`)
        grad.addColorStop(0.5, `rgba(${o.hue}, ${alpha * 0.45})`)
        grad.addColorStop(1,   `rgba(${o.hue}, 0)`)
        ctx.fillStyle = grad
        ctx.beginPath()
        ctx.arc(o.x, o.y, radius, 0, Math.PI * 2)
        ctx.fill()
      })
      animRef.current = requestAnimationFrame(draw)
    }
    draw()

    return () => {
      cancelAnimationFrame(animRef.current)
      window.removeEventListener('resize', resize)
    }
  }, [])

  const handleEnter = () => {
    setVisible(false)
    setTimeout(onEnter, 420)
  }

  return (
    <div style={styles.root}>
      <canvas ref={canvasRef} style={styles.canvas} />

      <div style={{
        ...styles.content,
        opacity:   visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(18px)',
        transition: 'opacity 0.7s ease, transform 0.7s ease',
      }}>
        <img
          src="/AdaptIQ.png"
          alt="AdaptIQ"
          style={styles.logo}
        />

        <button
          onClick={handleEnter}
          style={styles.btn}
          onMouseEnter={e => {
            e.currentTarget.style.boxShadow = '0 0 48px rgba(108,99,255,0.55), 0 8px 24px rgba(108,99,255,0.35)'
            e.currentTarget.style.filter = 'brightness(1.1)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.boxShadow = '0 0 32px rgba(108,99,255,0.38), 0 4px 16px rgba(108,99,255,0.22)'
            e.currentTarget.style.filter = 'brightness(1)'
          }}
        >
          Get Started
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="5" y1="12" x2="19" y2="12"/>
            <polyline points="12 5 19 12 12 19"/>
          </svg>
        </button>
      </div>
    </div>
  )
}

const styles = {
  root: {
    position: 'fixed',
    inset: 0,
    background: 'radial-gradient(ellipse at 60% 40%, #1a0f3c 0%, #0e0b1f 45%, #080612 100%)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 9999,
  },
  canvas: {
    position: 'absolute',
    inset: 0,
    width: '100%',
    height: '100%',
    pointerEvents: 'none',
  },
  content: {
    position: 'relative',
    zIndex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 48,
  },
  logo: {
    width: 'min(600px, 88vw)',
    height: 'auto',
    opacity: 0.95,
    maskImage: 'radial-gradient(ellipse 70% 60% at 50% 50%, black 50%, transparent 75%)',
    WebkitMaskImage: 'radial-gradient(ellipse 65% 60% at 50% 50%, black 30%, transparent 75%)',
    filter: 'drop-shadow(0 0 40px rgba(108,99,255,0.4))',
    userSelect: 'none',
  },
  btn: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '14px 36px',
    background: 'linear-gradient(135deg, #3d6ef6 0%, #8b5cf6 100%)',
    border: 'none',
    borderRadius: 12,
    color: '#ffffff',
    fontFamily: "'DM Sans', sans-serif",
    fontSize: 16,
    fontWeight: 600,
    letterSpacing: '0.01em',
    cursor: 'pointer',
    boxShadow: '0 0 32px rgba(108,99,255,0.38), 0 4px 16px rgba(108,99,255,0.22)',
    transition: 'filter 0.2s, box-shadow 0.2s',
  },
}