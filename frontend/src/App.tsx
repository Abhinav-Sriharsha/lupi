import { useState, useCallback, useRef, useEffect } from 'react'
import {
  LiveKitRoom,
  useVoiceAssistant,
  BarVisualizer,
  DisconnectButton,
  RoomAudioRenderer,
  useLocalParticipant,
} from '@livekit/components-react'
import type { TranscriptionSegment, TrackPublication } from 'livekit-client'
import '@livekit/components-styles'
import './App.css'

type CallState = 'idle' | 'connecting' | 'connected' | 'disconnected'

interface TranscriptLine {
  id: string
  speaker: 'you' | 'lupi'
  text: string
  final: boolean
}

function VoiceAgent({ onDisconnect }: { onDisconnect: () => void }) {
  const { state, audioTrack, agent } = useVoiceAssistant()
  const { localParticipant } = useLocalParticipant()
  const [transcript, setTranscript] = useState<TranscriptLine[]>([])
  const transcriptEndRef = useRef<HTMLDivElement>(null)

  const stateColor: Record<string, string> = {
    listening: '#22c55e',
    thinking:  '#f59e0b',
    speaking:  '#f97316',
  }

  const stateLabel: Record<string, string> = {
    disconnected:  'Disconnected',
    connecting:    'Connecting...',
    initializing:  'Starting up...',
    listening:     'Listening',
    thinking:      'Processing...',
    speaking:      'Speaking',
  }

  // Scroll to bottom on new transcript lines
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [transcript])

  // Subscribe to agent transcription
  useEffect(() => {
    if (!agent) return

    const handleAgentTranscription = (
      segments: TranscriptionSegment[],
      _publication?: TrackPublication
    ) => {
      segments.forEach(seg => {
        setTranscript(prev => {
          const existing = prev.findIndex(t => t.id === `lupi-${seg.id}`)
          const line: TranscriptLine = {
            id: `lupi-${seg.id}`,
            speaker: 'lupi',
            text: seg.text,
            final: seg.final,
          }
          if (existing >= 0) {
            const updated = [...prev]
            updated[existing] = line
            return updated
          }
          return [...prev, line]
        })
      })
    }

    agent.on('transcriptionReceived', handleAgentTranscription)
    return () => { agent.off('transcriptionReceived', handleAgentTranscription) }
  }, [agent])

  // Subscribe to local (user) transcription
  useEffect(() => {
    if (!localParticipant) return

    const handleUserTranscription = (
      segments: TranscriptionSegment[],
      _publication?: TrackPublication
    ) => {
      segments.forEach(seg => {
        setTranscript(prev => {
          const existing = prev.findIndex(t => t.id === `you-${seg.id}`)
          const line: TranscriptLine = {
            id: `you-${seg.id}`,
            speaker: 'you',
            text: seg.text,
            final: seg.final,
          }
          if (existing >= 0) {
            const updated = [...prev]
            updated[existing] = line
            return updated
          }
          return [...prev, line]
        })
      })
    }

    localParticipant.on('transcriptionReceived', handleUserTranscription)
    return () => { localParticipant.off('transcriptionReceived', handleUserTranscription) }
  }, [localParticipant])

  return (
    <div className="voice-agent">
      <div className="agent-avatar">🐺</div>
      <p className="agent-name">Lupi</p>

      <div className="state-row">
        <div className="state-dot" style={{ backgroundColor: stateColor[state] || '#6b7280' }} />
        <p className="state-label">{stateLabel[state] || state}</p>
      </div>

      <div className="visualizer-wrap">
        <BarVisualizer
          state={state}
          trackRef={audioTrack}
          barCount={28}
          style={{ height: '56px', width: '100%' }}
        />
      </div>

      <div className="transcript-box">
        {transcript.length === 0 && (
          <p className="transcript-empty">Transcript will appear here...</p>
        )}
        {transcript.map(line => (
          <div key={line.id} className={`transcript-line ${line.speaker} ${line.final ? 'final' : 'interim'}`}>
            <span className="transcript-speaker">{line.speaker === 'lupi' ? 'Lupi' : 'You'}</span>
            <span className="transcript-text">{line.text}</span>
          </div>
        ))}
        <div ref={transcriptEndRef} />
      </div>

      <DisconnectButton onClick={onDisconnect} className="end-btn">
        End Call
      </DisconnectButton>
    </div>
  )
}

export default function App() {
  const [callState, setCallState]   = useState<CallState>('idle')
  const [token, setToken]           = useState('')
  const [livekitUrl, setLivekitUrl] = useState('')
  const [error, setError]           = useState('')
  const abortRef                    = useRef<AbortController | null>(null)
  const isConnecting = callState === 'connecting'

  const startCall = useCallback(async () => {
    setError('')
    setCallState('connecting')
    abortRef.current = new AbortController()
    try {
      const res = await fetch('http://localhost:8000/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: 'unknown', customer_name: 'Customer' }),
        signal: abortRef.current.signal,
      })
      if (!res.ok) throw new Error(`Backend error ${res.status}`)
      const data = await res.json()
      setToken(data.token)
      setLivekitUrl(data.livekit_url)
      setCallState('connected')
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setError(err.message || 'Failed to connect')
        setCallState('idle')
      }
    }
  }, [])

  const endCall = useCallback(() => {
    abortRef.current?.abort()
    setToken('')
    setLivekitUrl('')
    setCallState('disconnected')
    setTimeout(() => setCallState('idle'), 1200)
  }, [])

  return (
    <div className="app">
      <header>
        <div className="logo">🐺 Lupi</div>
        <p className="tagline">Food Delivery Support</p>
      </header>

      {callState === 'idle' || callState === 'disconnected' ? (
        <main className="setup">
          <div className="call-card">
            <div className="call-card-icon">🐺</div>
            <h2>Lupi Support</h2>
            <p className="call-card-sub">AI-powered food delivery support agent</p>
            {error && <p className="error">{error}</p>}
            {callState === 'disconnected' && (
              <p className="disconnected-msg">Call ended.</p>
            )}
            <button
              className="call-btn"
              onClick={startCall}
              disabled={isConnecting}
            >
              {isConnecting ? 'Connecting...' : 'Call Lupi Support'}
            </button>
            <p className="call-hint">Lupi will ask for your phone number to look up your account</p>
          </div>
        </main>
      ) : (
        <main className="in-call">
          <LiveKitRoom
            token={token}
            serverUrl={livekitUrl}
            connect={true}
            audio={true}
            video={false}
            onDisconnected={endCall}
          >
            <RoomAudioRenderer />
            <VoiceAgent onDisconnect={endCall} />
          </LiveKitRoom>
        </main>
      )}
    </div>
  )
}
