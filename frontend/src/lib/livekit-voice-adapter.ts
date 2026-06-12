import { createVoiceSession, type RealtimeVoiceAdapter } from "@assistant-ui/react"
import { Room, RoomEvent, Track } from "livekit-client"

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"
const TOKEN_ENDPOINT = `${API_URL}/token`

export type LiveKitVoiceAdapterOptions = {
  phone?: string
  customerName?: string
  agentName?: string
  onData?: (data: unknown) => void
}

export function createLiveKitVoiceAdapter(
  options: LiveKitVoiceAdapterOptions = {},
): RealtimeVoiceAdapter {
  return {
    connect: ({ abortSignal }) =>
      createVoiceSession({ abortSignal }, async (helpers) => {
        const res = await fetch(TOKEN_ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            phone: options.phone ?? "unknown",
            customer_name: options.customerName ?? "Customer",
            agent_name: options.agentName ?? "lupi-agent",
          }),
          signal: abortSignal,
        })
        if (!res.ok) throw new Error(`Backend error ${res.status}`)
        const data = (await res.json()) as { token: string; livekit_url: string }

        const room = new Room()
        const audioContainer = document.createElement("div")
        audioContainer.style.display = "none"
        document.body.appendChild(audioContainer)

        room.on(RoomEvent.TrackSubscribed, (track) => {
          if (track.kind === Track.Kind.Audio) {
            audioContainer.appendChild(track.attach())
          }
        })

        room.on(RoomEvent.TrackUnsubscribed, (track) => {
          track.detach().forEach((el) => el.remove())
        })

        room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
          for (const seg of segments) {
            helpers.emitTranscript({
              role: participant?.isLocal ? "user" : "assistant",
              text: seg.text,
              isFinal: seg.final,
            })
          }
        })

        room.on(RoomEvent.ParticipantAttributesChanged, (changed, participant) => {
          if (!participant.isAgent) return
          const agentState = changed["lk.agent.state"]
          if (agentState) {
            helpers.emitMode(agentState === "speaking" ? "speaking" : "listening")
          }
        })

        room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
          const maxLevel = speakers.reduce((max, p) => Math.max(max, p.audioLevel), 0)
          helpers.emitVolume(maxLevel)
        })

        room.on(RoomEvent.DataReceived, (payload) => {
          if (!options.onData) return
          try {
            options.onData(JSON.parse(new TextDecoder().decode(payload)))
          } catch {
            // ignore non-JSON payloads
          }
        })

        room.on(RoomEvent.Disconnected, () => {
          audioContainer.remove()
          helpers.end("finished")
        })

        await room.connect(data.livekit_url, data.token)
        await room.localParticipant.setMicrophoneEnabled(true)

        helpers.setStatus({ type: "running" })

        return {
          disconnect: () => {
            audioContainer.remove()
            room.disconnect()
          },
          mute: () => {
            void room.localParticipant.setMicrophoneEnabled(false)
          },
          unmute: () => {
            void room.localParticipant.setMicrophoneEnabled(true)
          },
        }
      }),
  }
}
