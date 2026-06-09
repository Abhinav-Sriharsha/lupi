import { useState, useCallback, useRef, useEffect, Fragment } from 'react'
import {
  LiveKitRoom,
  useVoiceAssistant,
  BarVisualizer,
  RoomAudioRenderer,
  useLocalParticipant,
} from '@livekit/components-react'
import type { TranscriptionSegment, TrackPublication } from 'livekit-client'
import '@livekit/components-styles'
import './App.css'

type CallState = 'idle' | 'connecting' | 'connected' | 'disconnected'

interface TranscriptLine {
  id: string
  speaker: 'user' | 'agent'
  text: string
  final: boolean
}

interface ActivityEvent {
  id: string
  timestamp: string
  label: string
  type: 'stage' | 'tool' | 'success' | 'error'
}

type PushActivityFn = (event: Omit<ActivityEvent, 'id' | 'timestamp'>) => void

const DOT_COLORS: Record<ActivityEvent['type'], string> = {
  stage:   '#3b82f6',
  tool:    '#f97316',
  success: '#22c55e',
  error:   '#ef4444',
}

const STATE_LABELS: Record<string, string> = {
  disconnected: 'IDLE',
  connecting:   'CONNECTING',
  initializing: 'INITIALIZING',
  listening:    'LISTENING',
  thinking:     'PROCESSING',
  speaking:     'SPEAKING',
}

const STATE_ACTIVITY: Record<string, { label: string; type: ActivityEvent['type'] }> = {
  initializing: { label: 'Connecting',  type: 'stage' },
  listening:    { label: 'Listening',   type: 'stage' },
  thinking:     { label: 'Processing',  type: 'stage' },
  speaking:     { label: 'Speaking',    type: 'stage' },
}

const FSM_STAGES = [
  'INTRO',
  'PHONE COLLECTION',
  'ISSUE COLLECTION',
  'INVESTIGATION',
  'RESOLUTION',
  'CLOSING',
] as const

const FSM_STATUS: Record<number, string> = {
  0: 'exchanging greeting',
  1: 'collecting phone number',
  2: 'identifying issue',
  3: 'fetching order data',
  4: 'processing resolution',
  5: 'wrapping up',
}

function formatTime(d: Date): string {
  return d.toLocaleTimeString('en-US', {
    hour12: false,
    hour:   '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatDuration(total: number): string {
  const m = Math.floor(total / 60).toString().padStart(2, '0')
  const s = (total % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

function VoiceAgent({
  onDisconnect,
  onActivity,
  onFsmAdvance,
  callDuration,
}: {
  onDisconnect: () => void
  onActivity: PushActivityFn
  onFsmAdvance: (stage: number) => void
  callDuration: number
}) {
  const { state, audioTrack, agent } = useVoiceAssistant()
  const { localParticipant } = useLocalParticipant()
  const [transcript, setTranscript] = useState<TranscriptLine[]>([])
  const prevStateRef    = useRef<string>('')
  const userTurnCount   = useRef(0)
  const countedUserSegs  = useRef(new Set<string>())
  const countedAgentSegs = useRef(new Set<string>())

  // Agent state → activity feed
  useEffect(() => {
    if (state !== prevStateRef.current && STATE_ACTIVITY[state]) {
      onActivity(STATE_ACTIVITY[state])
      prevStateRef.current = state
    }
  }, [state, onActivity])

  // Advance FSM stage by watching finalized transcript entries
  useEffect(() => {
    transcript.forEach(line => {
      if (!line.final) return
      if (line.speaker === 'user' && !countedUserSegs.current.has(line.id)) {
        countedUserSegs.current.add(line.id)
        userTurnCount.current += 1
        const n = userTurnCount.current
        if (n === 1) onFsmAdvance(1)
        else if (n === 2) onFsmAdvance(2)
        else if (n === 3) onFsmAdvance(3)
      } else if (line.speaker === 'agent' && !countedAgentSegs.current.has(line.id)) {
        countedAgentSegs.current.add(line.id)
        const u = userTurnCount.current
        if (u === 3) onFsmAdvance(4)
        else if (u >= 4) onFsmAdvance(5)
      }
    })
  }, [transcript, onFsmAdvance])

  // Agent transcription
  useEffect(() => {
    if (!agent) return
    const handle = (segments: TranscriptionSegment[], _pub?: TrackPublication) => {
      segments.forEach(seg => {
        if (seg.final) onActivity({ label: 'Response generated', type: 'success' })
        setTranscript(prev => {
          const key = `agent-${seg.id}`
          const idx = prev.findIndex(t => t.id === key)
          const line: TranscriptLine = { id: key, speaker: 'agent', text: seg.text, final: seg.final }
          if (idx >= 0) {
            const next = [...prev]
            next[idx] = line
            return next
          }
          return [...prev, line].slice(-12)
        })
      })
    }
    agent.on('transcriptionReceived', handle)
    return () => { agent.off('transcriptionReceived', handle) }
  }, [agent, onActivity])

  // User transcription
  useEffect(() => {
    if (!localParticipant) return
    const handle = (segments: TranscriptionSegment[], _pub?: TrackPublication) => {
      segments.forEach(seg => {
        if (seg.final) onActivity({ label: 'User input received', type: 'tool' })
        setTranscript(prev => {
          const key = `user-${seg.id}`
          const idx = prev.findIndex(t => t.id === key)
          const line: TranscriptLine = { id: key, speaker: 'user', text: seg.text, final: seg.final }
          if (idx >= 0) {
            const next = [...prev]
            next[idx] = line
            return next
          }
          return [...prev, line].slice(-12)
        })
      })
    }
    localParticipant.on('transcriptionReceived', handle)
    return () => { localParticipant.off('transcriptionReceived', handle) }
  }, [localParticipant, onActivity])

  const last3 = transcript.slice(-3)
  const orbClass =
    state === 'listening' ? 'orb-listening'
    : state === 'thinking' ? 'orb-thinking'
    : state === 'speaking' ? 'orb-speaking'
    : 'orb-idle'

  return (
    <>
      <div className="center-section">
        <div className={`orb-wrap ${orbClass}`}>
          <div className="orb">
            {state === 'thinking' && <div className="orb-ring" />}
            <div className="orb-viz">
              <BarVisualizer
                state={state}
                track={audioTrack}
                barCount={20}
                style={{ height: '60px', width: '100%' }}
              />
            </div>
          </div>
          <div className="orb-label">{STATE_LABELS[state] ?? 'IDLE'}</div>
          <div className="orb-timer">{formatDuration(callDuration)}</div>
        </div>
      </div>

      <div className="bottom-section">
        <div className="transcript-lines">
          {last3.map(line => (
            <div
              key={line.id}
              className={`t-entry t-${line.speaker}${line.final ? '' : ' t-interim'}`}
            >
              {line.speaker === 'agent' && <span className="t-dash">&#8212;</span>}
              <span className="t-text">{line.text}</span>
            </div>
          ))}
        </div>
        <div className="action-row action-right">
          <button className="btn-terminate" onClick={onDisconnect}>TERMINATE</button>
        </div>
      </div>
    </>
  )
}

export default function App() {
  const [callState, setCallState]       = useState<CallState>('idle')
  const [token, setToken]               = useState('')
  const [livekitUrl, setLivekitUrl]     = useState('')
  const [error, setError]               = useState('')
  const [activity, setActivity]         = useState<ActivityEvent[]>([])
  const [callDuration, setCallDuration] = useState(0)
  const [fsmStage, setFsmStage]         = useState(0)
  const abortRef = useRef<AbortController | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const pushActivity = useCallback<PushActivityFn>(event => {
    setActivity(prev => {
      const entry: ActivityEvent = {
        ...event,
        id:        `${Date.now()}-${Math.random()}`,
        timestamp: formatTime(new Date()),
      }
      return [entry, ...prev].slice(0, 12)
    })
  }, [])

  const handleFsmAdvance = useCallback((stage: number) => {
    setFsmStage(stage)
  }, [])

  useEffect(() => {
    if (callState === 'connected') {
      setCallDuration(0)
      timerRef.current = setInterval(() => setCallDuration(d => d + 1), 1000)
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [callState])

  const startCall = useCallback(async () => {
    setError('')
    setFsmStage(0)
    setCallState('connecting')
    pushActivity({ label: 'Connecting', type: 'stage' })
    abortRef.current = new AbortController()
    try {
      const res = await fetch('http://localhost:8000/token', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ phone: 'unknown', customer_name: 'Customer' }),
        signal:  abortRef.current.signal,
      })
      if (!res.ok) throw new Error(`Backend error ${res.status}`)
      const data = (await res.json()) as { token: string; livekit_url: string }
      setToken(data.token)
      setLivekitUrl(data.livekit_url)
      setCallState('connected')
      pushActivity({ label: 'Session established', type: 'success' })
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== 'AbortError') {
        setError(err.message)
        setCallState('idle')
        pushActivity({ label: 'Connection failed', type: 'error' })
      }
    }
  }, [pushActivity])

  const endCall = useCallback(() => {
    abortRef.current?.abort()
    setToken('')
    setLivekitUrl('')
    pushActivity({ label: 'Session terminated', type: 'error' })
    setCallState('disconnected')
    setTimeout(() => setCallState('idle'), 1200)
  }, [pushActivity])

  const isLive    = callState === 'connected'
  const lastEvent = activity[0] ?? null

  return (
    <div className="app-root">
      <aside className="activity-panel">
        <div className="activity-header">AGENT STATE</div>

        <div className="fsm-body">
          <div className="fsm-diagram">
            {FSM_STAGES.map((label, i) => {
              const nodeState =
                i < fsmStage  ? 'completed'
                : i === fsmStage ? 'active'
                : 'inactive'
              const connDone = i < fsmStage
              return (
                <Fragment key={label}>
                  <div className={`fsm-node fsm-node-${nodeState}`}>
                    <span className="fsm-node-label">{label}</span>
                  </div>
                  {i === fsmStage && (
                    <div className="fsm-status">{FSM_STATUS[i]}</div>
                  )}
                  {i < FSM_STAGES.length - 1 && (
                    <div className={`fsm-conn${connDone ? ' fsm-conn-done' : ''}`}>
                      <div className="fsm-conn-line" />
                      <div className="fsm-conn-arrow" />
                    </div>
                  )}
                </Fragment>
              )
            })}
          </div>
        </div>

        <div className="fsm-footer">
          <div className="fsm-divider" />
          <div className="fsm-last-label">LAST EVENT</div>
          {lastEvent && (
            <div className="activity-event">
              <span className="activity-ts">{lastEvent.timestamp}</span>
              <span className="activity-dot" style={{ background: DOT_COLORS[lastEvent.type] }} />
              <span className="activity-label">{lastEvent.label}</span>
            </div>
          )}
        </div>
      </aside>

      <main className="main-panel">
        <div className="top-bar">
          <span className="top-title">Lupi</span>
          <div className="top-status">
            <span className={`status-dot ${isLive ? 'status-live' : 'status-off'}`} />
            <span className="status-label">{isLive ? 'LIVE' : 'OFFLINE'}</span>
          </div>
        </div>

        {callState === 'connected' ? (
          <LiveKitRoom
            className="lk-fill"
            token={token}
            serverUrl={livekitUrl}
            connect={true}
            audio={true}
            video={false}
            onDisconnected={endCall}
          >
            <RoomAudioRenderer />
            <VoiceAgent
              onDisconnect={endCall}
              onActivity={pushActivity}
              onFsmAdvance={handleFsmAdvance}
              callDuration={callDuration}
            />
          </LiveKitRoom>
        ) : (
          <>
            <div className="center-section">
              <div className="orb-wrap orb-idle">
                <div className="orb" />
                <div className="orb-label">IDLE</div>
              </div>
            </div>

            <div className="bottom-section">
              <div className="transcript-lines" />
              {error && <p className="error-msg">{error}</p>}
              <div className="action-row action-center">
                <button
                  className="btn-init"
                  onClick={startCall}
                  disabled={callState === 'connecting'}
                >
                  {callState === 'connecting' ? 'CONNECTING' : 'INITIALIZE CALL'}
                </button>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  )
}
