import { useEffect, useRef, useState } from 'react'
import './App.css'
import { Reveal } from './components/landing/reveal'
import { VoiceStage } from './components/landing/voice-stage'

// ── Wordmark ───────────────────────────────────────────────────────────────────

function Wordmark() {
  return (
    <div className="wordmark">
      <span className="seam" />
      <span className="dot" />
      <span className="vt">LUPI</span>
      <span className="seam b" />
    </div>
  )
}

// ── Contact popover ──────────────────────────────────────────────────────────────

function ContactCard() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('click', onDocClick)
    return () => document.removeEventListener('click', onDocClick)
  }, [])

  return (
    <div className={`contact${open ? ' open' : ''}`} ref={ref}>
      <button className="trigger" onClick={() => setOpen((o) => !o)}>
        <span className="pin" />
        Contact
      </button>
      <div className="card">
        <a href="mailto:abhinavsriharshaa@gmail.com">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <rect x="2" y="4" width="20" height="16" rx="2" />
            <path d="m22 6-10 7L2 6" />
          </svg>
          <span>
            Email me
            <small>abhinavsriharshaa@gmail.com</small>
          </span>
        </a>
        <div className="div" />
        <a href="/resume.pdf" download="abhinav_sriharsha_resume.pdf">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <path d="M14 2v6h6M12 18v-6M9 15l3 3 3-3" />
          </svg>
          <span>
            Download résumé
            <small>PDF</small>
          </span>
        </a>
      </div>
    </div>
  )
}

// ── Tech strip ───────────────────────────────────────────────────────────────────

function TechStrip() {
  return (
    <Reveal as="div" className="techstrip">
      <div className="lab">The real-time pipeline</div>
      <div className="techrow">
        <span className="tech">
          <img src="/logos/LiveKit-Logo-New.png" alt="LiveKit" />
        </span>
        <span className="tech">
          <img src="/logos/deepgram.png" alt="Deepgram" />
        </span>
        <span className="tech">
          <img src="/logos/groq.png" alt="Groq" style={{ height: '17px' }} />
        </span>
        <span className="tech">
          <img src="/logos/llama.png" alt="Llama" style={{ height: '68px' }} />
        </span>
        <span className="tech">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 21s-6.9-4.5-9.2-8.9C1.1 9 2.4 5.4 5.9 5.4c2 0 3.3 1.2 4.1 2.4.8-1.2 2.1-2.4 4.1-2.4 3.5 0 4.8 3.6 3.1 6.7C14.9 16.5 12 21 12 21Z" />
          </svg>
          <span>Kokoro</span>
        </span>
        <span className="tech">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M13 2.2 4.1 13.6c-.5.6 0 1.4.7 1.4H11l-.9 6.9c-.1.8.9 1.2 1.4.6L20 10.4c.5-.6 0-1.4-.7-1.4H13l.9-6.2c.1-.8-.9-1.2-1.4-.6Z" transform="translate(.4 0)" />
          </svg>
          <span>Supabase</span>
        </span>
      </div>
    </Reveal>
  )
}

// ── Hero ───────────────────────────────────────────────────────────────────────

const STATS = [
  { value: '455', unit: 'ms', label: 'Avg time to first audio' },
  { value: '246', unit: 'ms', label: 'Intent classification' },
  { value: '114', unit: 'ms', label: 'Best time to first token' },
  { value: '8B', unit: '+', suffix: '70B', label: 'Parallel LLM execution' },
]

function HeroSection() {
  return (
    <section className="hero" id="hero">
      <div className="hero-grid">
        <Reveal>
          <div className="eyebrow">Real-time voice AI</div>
          <h1>
            Voice that thinks in <em>milliseconds.</em>
          </h1>
          <p className="lede">
            Deepgram Nova-2 STT, Groq LLaMA 70B reasoning, and Kokoro local TTS
            chained through a deterministic FSM. Sub-500ms turn latency, end to end.
          </p>
          <div className="stats">
            {STATS.map((s) => (
              <div className="stat" key={s.label}>
                <div className="n">
                  {s.value}
                  <small>{s.unit}</small>
                  {'suffix' in s && (s as { suffix: string }).suffix}
                </div>
                <div className="l">{s.label}</div>
              </div>
            ))}
          </div>
        </Reveal>

        <Reveal as="div" className="orbside">
          <VoiceStage
            agentName="lupi-chat"
            variant="violet"
            idleLabel="Tap to talk"
            ctaLabel="Talk to Lupi"
            agentLabel="Lupi"
          />
        </Reveal>
      </div>
    </section>
  )
}

// ── Production details (FSM + capabilities) ─────────────────────────────────────

const FSM_STAGES = [
  { key: 'intro', label: 'intro' },
  { key: 'phone_collection', label: 'phone' },
  { key: 'issue_collection', label: 'issue' },
  { key: 'investigation', label: 'investigation' },
  { key: 'resolution', label: 'resolution' },
  { key: 'closing', label: 'closing' },
]

function FsmDiagram({ stage }: { stage: string | null }) {
  const activeIndex = stage ? FSM_STAGES.findIndex((s) => s.key === stage) : -1

  return (
    <div className="fsm">
      {FSM_STAGES.map((s, i) => {
        const status = i === activeIndex ? 'active' : i < activeIndex ? 'done' : ''
        return (
          <div className={`node${status ? ` ${status}` : ''}`} key={s.key}>
            <span className="pill">{s.label}</span>
            {i < FSM_STAGES.length - 1 && <span className="seg" />}
          </div>
        )
      })}
    </div>
  )
}

function ProductionSection({ fsmStage }: { fsmStage: string | null }) {
  return (
    <section className="prod" id="prod">
      <Reveal as="div" className="secthead">
        <div className="kicker">Lupi in production</div>
        <h2>A full support agent that never needs a human.</h2>
        <p>
          LupiDash is a working food-delivery support line. Lupi pulls the live order from a real database,
          runs a pure-Python refund policy engine, and resolves the call on its own, from phone collection to payout.
        </p>
      </Reveal>

      <Reveal as="div">
        <FsmDiagram stage={fsmStage} />
      </Reveal>

      <Reveal as="div" className="caps">
        <div className="cap">
          <div className="ci">8</div>
          <h4>Scenarios end to end</h4>
          <p>Late, missing, wrong, refund, cancel, and more. All resolved without a handoff.</p>
        </div>
        <div className="cap">
          <div className="ci">0</div>
          <h4>Hallucinated refunds</h4>
          <p>A pure-Python policy engine decides payouts from raw timestamps. The LLM never touches the math.</p>
        </div>
        <div className="cap">
          <div className="ci">
            246<span style={{ fontSize: '13px' }}>ms</span>
          </div>
          <h4>Intent routing</h4>
          <p>A parallel Groq 8B classifier picks the path while the 70B model is already responding.</p>
        </div>
        <div className="cap">
          <div className="ci">FSM</div>
          <h4>Deterministic control</h4>
          <p>Every action fires from a state machine, not the model. Same input, same path, every time.</p>
        </div>
      </Reveal>
    </section>
  )
}

// ── LupiDash live agent ──────────────────────────────────────────────────────────

function LupiDashSection({ onData }: { onData: (data: unknown) => void }) {
  return (
    <section className="agent warm" id="lupidash">
      <Reveal as="div" className="secthead">
        <div className="kicker">Try it live</div>
        <h2>Call LupiDash support</h2>
        <p>A late order, a real account, a real refund. Watch the state machine advance with the call.</p>
        <div className="test-numbers">
          <div>Try: Maya (415) 555-0101, late delivery</div>
          <div>Try: Jordan (415) 555-0102, missing items</div>
        </div>
      </Reveal>

      <VoiceStage
        agentName="lupi-agent"
        variant="amber"
        idleLabel="Ready"
        ctaLabel="Call support"
        agentLabel="Lupi"
        onData={onData}
      />
    </section>
  )
}

// ── App ────────────────────────────────────────────────────────────────────────

export default function App() {
  const [fsmStage, setFsmStage] = useState<string | null>(null)

  const handleLupiDashData = (data: unknown) => {
    const d = data as { type?: string; stage?: string }
    if (d?.type === 'fsm_stage' && typeof d.stage === 'string') {
      setFsmStage(d.stage)
    }
  }

  return (
    <>
      <Wordmark />
      <ContactCard />

      <HeroSection />
      <TechStrip />
      <ProductionSection fsmStage={fsmStage} />
      <LupiDashSection onData={handleLupiDashData} />

      <footer>Built by Abhinav Sriharsha</footer>
    </>
  )
}
