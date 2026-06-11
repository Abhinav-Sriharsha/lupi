import { useEffect, useMemo, useRef, useState } from "react"
import {
  AssistantRuntimeProvider,
  useAuiState,
  useLocalRuntime,
  useVoiceControls,
  useVoiceState,
  type ChatModelAdapter,
} from "@assistant-ui/react"
import { MicIcon, MicOffIcon, PhoneIcon, PhoneOffIcon } from "lucide-react"
import {
  VoiceOrb,
  deriveOrbWrapState,
  type VoiceOrbVariant,
} from "@/components/assistant-ui/voice-orb"
import { createLiveKitVoiceAdapter } from "@/lib/livekit-voice-adapter"

const chatModelStub: ChatModelAdapter = {
  run: async () => ({ content: [] }),
}

type TurnMetric = {
  turn: number
  ttft_ms: number
  tts_first_chunk_ms: number
  tts_total_ms: number
  ttfa_ms: number
  total_ms: number
}

export type VoiceStageProps = {
  agentName: string
  variant: VoiceOrbVariant
  idleLabel: string
  ctaLabel: string
  agentLabel: string
  onData?: (data: unknown) => void
}

function TranscriptList({ agentLabel }: { agentLabel: string }) {
  const messages = useAuiState((s) => s.thread.messages)
  const last3 = messages.slice(-3)

  return (
    <div className="transcript">
      {last3.map((m) => {
        const text = m.content
          .map((part) => (part.type === "text" ? part.text : ""))
          .join("")
        const isUser = m.role === "user"
        return (
          <div key={m.id} className={`line ${isUser ? "user" : "lupi"}`}>
            <span className="who">{isUser ? "You" : agentLabel}</span>
            {text}
          </div>
        )
      })}
    </div>
  )
}

function SessionReport({ metrics }: { metrics: TurnMetric[] }) {
  const avg = (key: keyof Omit<TurnMetric, "turn">) =>
    metrics.length > 0
      ? Math.round(metrics.reduce((sum, m) => sum + m[key], 0) / metrics.length)
      : 0

  return (
    <div className="report show">
      <h3>Session report</h3>
      <div className="sub">Latency captured per turn from the LiveKit data channel.</div>
      <table>
        <thead>
          <tr>
            <th>Turn</th>
            <th>TTFT</th>
            <th>TTFA</th>
            <th>TTS</th>
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((m) => (
            <tr key={m.turn}>
              <td>{m.turn}</td>
              <td><b>{m.ttft_ms}ms</b></td>
              <td>{m.ttfa_ms}ms</td>
              <td>{m.tts_total_ms}ms</td>
              <td>{m.total_ms}ms</td>
            </tr>
          ))}
          <tr className="avg">
            <td>Avg</td>
            <td>{avg("ttft_ms")}ms</td>
            <td>{avg("ttfa_ms")}ms</td>
            <td>{avg("tts_total_ms")}ms</td>
            <td>{avg("total_ms")}ms</td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

function StageInner({
  variant,
  idleLabel,
  ctaLabel,
  agentLabel,
  metrics,
  resetMetrics,
}: Pick<VoiceStageProps, "variant" | "idleLabel" | "ctaLabel" | "agentLabel"> & {
  metrics: TurnMetric[]
  resetMetrics: () => void
}) {
  const voiceState = useVoiceState()
  const { connect, disconnect, mute, unmute } = useVoiceControls()
  const wrapState = deriveOrbWrapState(voiceState)
  const isActive = voiceState != null && voiceState.status.type !== "ended"
  const isMuted = voiceState?.isMuted ?? false
  const hasError = voiceState?.status.type === "ended" && voiceState.status.reason === "error"

  const [showReport, setShowReport] = useState(false)
  const [everConnected, setEverConnected] = useState(false)
  const wasActive = useRef(false)

  useEffect(() => {
    if (isActive && !wasActive.current) {
      setShowReport(false)
      resetMetrics()
      setEverConnected(true)
    } else if (!isActive && wasActive.current && metrics.length > 0) {
      setShowReport(true)
    }
    wasActive.current = isActive
  }, [isActive, metrics, resetMetrics])

  const latest = metrics[metrics.length - 1]

  return (
    <>
      <div className={`orb-wrap ${wrapState}`}>
        <span className="ring" />
        <span className="ring" />
        <span className="ring" />
        <VoiceOrb variant={variant} className="orb-canvas" />
      </div>
      <div className="status">
        {wrapState === "asleep" ? (
          idleLabel
        ) : wrapState === "idle" ? (
          <b>Connected</b>
        ) : (
          wrapState.charAt(0).toUpperCase() + wrapState.slice(1)
        )}
      </div>
      <div className={`telemetry${isActive || showReport ? " show" : ""}`}>
        <span>TTFT <b>{latest ? `${latest.ttft_ms}ms` : "-"}</b></span>
        <span>TTS <b>{latest ? `${latest.tts_total_ms}ms` : "-"}</b></span>
        <span>turn <b>{metrics.length}</b></span>
      </div>
      <div className="controls">
        {!isActive ? (
          <button className="btn btn-connect" onClick={() => connect()}>
            <PhoneIcon /> {everConnected ? "Talk again" : ctaLabel}
          </button>
        ) : (
          <>
            <button className="btn btn-end" onClick={() => disconnect()}>
              <PhoneOffIcon /> End call
            </button>
            <button
              type="button"
              className="btn-icon"
              data-active={isMuted}
              aria-label={isMuted ? "Unmute" : "Mute"}
              onClick={() => (isMuted ? unmute() : mute())}
            >
              {isMuted ? <MicOffIcon /> : <MicIcon />}
            </button>
          </>
        )}
      </div>
      {hasError && <p className="error-msg">Connection error</p>}
      <div className="convo">
        {isActive && <TranscriptList agentLabel={agentLabel} />}
        {showReport && metrics.length > 0 && <SessionReport metrics={metrics} />}
      </div>
    </>
  )
}

export function VoiceStage({
  agentName,
  variant,
  idleLabel,
  ctaLabel,
  agentLabel,
  onData,
}: VoiceStageProps) {
  const [metrics, setMetrics] = useState<TurnMetric[]>([])
  const metricsRef = useRef<TurnMetric[]>([])
  const onDataRef = useRef(onData)
  onDataRef.current = onData

  const runtime = useLocalRuntime(
    chatModelStub,
    useMemo(
      () => ({
        adapters: {
          voice: createLiveKitVoiceAdapter({
            agentName,
            onData: (data) => {
              onDataRef.current?.(data)
              const d = data as Partial<TurnMetric> & { type?: string }
              if (d?.type !== "metrics" || typeof d.turn !== "number") return
              const turn: TurnMetric = {
                turn: d.turn,
                ttft_ms: d.ttft_ms ?? 0,
                tts_first_chunk_ms: d.tts_first_chunk_ms ?? 0,
                tts_total_ms: d.tts_total_ms ?? 0,
                ttfa_ms: d.ttfa_ms ?? 0,
                total_ms: d.total_ms ?? 0,
              }
              metricsRef.current = [
                ...metricsRef.current.filter((m) => m.turn !== turn.turn),
                turn,
              ].sort((a, b) => a.turn - b.turn)
              setMetrics(metricsRef.current)
            },
          }),
        },
      }),
      [agentName],
    ),
  )

  const resetMetrics = () => {
    metricsRef.current = []
    setMetrics([])
  }

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <StageInner
        variant={variant}
        idleLabel={idleLabel}
        ctaLabel={ctaLabel}
        agentLabel={agentLabel}
        metrics={metrics}
        resetMetrics={resetMetrics}
      />
    </AssistantRuntimeProvider>
  )
}
