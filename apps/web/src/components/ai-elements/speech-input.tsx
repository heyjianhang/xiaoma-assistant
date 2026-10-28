// AI Elements source, adapted for XiaoMa Assistant. See THIRD_PARTY_NOTICES.md (Apache-2.0).
"use client"

import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { cn } from "@/lib/utils"
import { MicIcon, SquareIcon } from "lucide-react"
import type { ComponentProps } from "react"
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react"

interface SpeechRecognition extends EventTarget {
  continuous: boolean
  interimResults: boolean
  lang: string
  start(): void
  stop(): void
  onstart: ((this: SpeechRecognition, ev: Event) => void) | null
  onend: ((this: SpeechRecognition, ev: Event) => void) | null
  onresult:
    ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => void) | null
  onerror:
    ((this: SpeechRecognition, ev: SpeechRecognitionErrorEvent) => void) | null
}

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList
  resultIndex: number
}

interface SpeechRecognitionResultList {
  readonly length: number
  item(index: number): SpeechRecognitionResult
  [index: number]: SpeechRecognitionResult
}

interface SpeechRecognitionResult {
  readonly length: number
  item(index: number): SpeechRecognitionAlternative
  [index: number]: SpeechRecognitionAlternative
  isFinal: boolean
}

interface SpeechRecognitionAlternative {
  transcript: string
  confidence: number
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string
}

declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognition
    webkitSpeechRecognition: new () => SpeechRecognition
  }
}

type SpeechInputMode = "speech-recognition" | "media-recorder" | "none"

export type SpeechInputProps = ComponentProps<typeof Button> & {
  onTranscriptionChange?: (text: string) => void
  onSpeechError?: (code: string) => void
  /**
   * Callback for when audio is recorded using MediaRecorder fallback.
   * This is called in browsers that don't support the Web Speech API (Firefox, Safari).
   * The callback receives an audio Blob that should be sent to a transcription service.
   * Return the transcribed text, which will be passed to onTranscriptionChange.
   */
  onAudioRecorded?: (audioBlob: Blob) => Promise<string>
  lang?: string
}

const detectSpeechInputMode = (): SpeechInputMode => {
  if (typeof window === "undefined") {
    return "none"
  }

  if ("SpeechRecognition" in window || "webkitSpeechRecognition" in window) {
    return "speech-recognition"
  }

  if ("MediaRecorder" in window && "mediaDevices" in navigator) {
    return "media-recorder"
  }

  return "none"
}

const subscribeToSpeechInputMode = () => () => undefined

export const SpeechInput = ({
  className,
  onTranscriptionChange,
  onSpeechError,
  onAudioRecorded,
  lang = "zh-CN",
  disabled = false,
  ...props
}: SpeechInputProps) => {
  const [isListening, setIsListening] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const mode = useSyncExternalStore(
    subscribeToSpeechInputMode,
    detectSpeechInputMode,
    () => "none"
  )
  const recognitionRef = useRef<SpeechRecognition | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const onTranscriptionChangeRef = useRef<
    SpeechInputProps["onTranscriptionChange"]
  >(onTranscriptionChange)
  const onAudioRecordedRef =
    useRef<SpeechInputProps["onAudioRecorded"]>(onAudioRecorded)
  const onSpeechErrorRef = useRef(onSpeechError)

  useEffect(() => {
    onTranscriptionChangeRef.current = onTranscriptionChange
    onAudioRecordedRef.current = onAudioRecorded
    onSpeechErrorRef.current = onSpeechError
  }, [onAudioRecorded, onTranscriptionChange, onSpeechError])

  // Initialize Speech Recognition when mode is speech-recognition
  useEffect(() => {
    if (mode !== "speech-recognition") {
      return
    }

    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition
    const speechRecognition = new SpeechRecognition()

    speechRecognition.continuous = true
    speechRecognition.interimResults = true
    speechRecognition.lang = lang

    const handleStart = () => {
      setIsListening(true)
    }

    const handleEnd = () => {
      setIsListening(false)
    }

    const handleResult = (event: Event) => {
      const speechEvent = event as SpeechRecognitionEvent
      let finalTranscript = ""

      for (
        let i = speechEvent.resultIndex;
        i < speechEvent.results.length;
        i += 1
      ) {
        const result = speechEvent.results[i]
        if (result.isFinal) {
          finalTranscript += result[0]?.transcript ?? ""
        }
      }

      if (finalTranscript) {
        onTranscriptionChangeRef.current?.(finalTranscript)
      }
    }

    const handleError = (event: Event) => {
      setIsListening(false)
      const code = (event as SpeechRecognitionErrorEvent).error
      if (code !== "aborted") onSpeechErrorRef.current?.(code)
    }

    speechRecognition.addEventListener("start", handleStart)
    speechRecognition.addEventListener("end", handleEnd)
    speechRecognition.addEventListener("result", handleResult)
    speechRecognition.addEventListener("error", handleError)

    recognitionRef.current = speechRecognition

    return () => {
      speechRecognition.removeEventListener("start", handleStart)
      speechRecognition.removeEventListener("end", handleEnd)
      speechRecognition.removeEventListener("result", handleResult)
      speechRecognition.removeEventListener("error", handleError)
      speechRecognition.stop()
      recognitionRef.current = null
    }
  }, [mode, lang])

  useEffect(() => {
    if (disabled) recognitionRef.current?.stop()
  }, [disabled])

  // Cleanup MediaRecorder and stream on unmount
  useEffect(
    () => () => {
      if (mediaRecorderRef.current?.state === "recording") {
        mediaRecorderRef.current.stop()
      }
      if (streamRef.current) {
        for (const track of streamRef.current.getTracks()) {
          track.stop()
        }
      }
    },
    []
  )

  // Start MediaRecorder recording
  const startMediaRecorder = useCallback(async () => {
    if (!onAudioRecordedRef.current) {
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const mediaRecorder = new MediaRecorder(stream)
      audioChunksRef.current = []

      const handleDataAvailable = (event: BlobEvent) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      const handleStop = async () => {
        for (const track of stream.getTracks()) {
          track.stop()
        }
        streamRef.current = null

        const audioBlob = new Blob(audioChunksRef.current, {
          type: "audio/webm",
        })

        if (audioBlob.size > 0 && onAudioRecordedRef.current) {
          setIsProcessing(true)
          try {
            const transcript = await onAudioRecordedRef.current(audioBlob)
            if (transcript) {
              onTranscriptionChangeRef.current?.(transcript)
            }
          } catch {
            // Error handling delegated to the onAudioRecorded caller
          } finally {
            setIsProcessing(false)
          }
        }
      }

      const handleError = () => {
        setIsListening(false)
        for (const track of stream.getTracks()) {
          track.stop()
        }
        streamRef.current = null
      }

      mediaRecorder.addEventListener("dataavailable", handleDataAvailable)
      mediaRecorder.addEventListener("stop", handleStop)
      mediaRecorder.addEventListener("error", handleError)

      mediaRecorderRef.current = mediaRecorder
      mediaRecorder.start()
      setIsListening(true)
    } catch {
      setIsListening(false)
    }
  }, [])

  // Stop MediaRecorder recording
  const stopMediaRecorder = useCallback(() => {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop()
    }
    setIsListening(false)
  }, [])

  const toggleListening = useCallback(() => {
    if (mode === "speech-recognition" && recognitionRef.current) {
      if (isListening) {
        recognitionRef.current.stop()
      } else {
        try { recognitionRef.current.start() }
        catch { onSpeechErrorRef.current?.("unavailable") }
      }
    } else if (mode === "media-recorder") {
      if (isListening) {
        stopMediaRecorder()
      } else {
        startMediaRecorder()
      }
    }
  }, [mode, isListening, startMediaRecorder, stopMediaRecorder])

  // Determine if button should be disabled
  const isDisabled =
    disabled ||
    mode === "none" ||
    (mode === "media-recorder" && !onAudioRecorded) ||
    isProcessing

  return (
    <div className="relative inline-flex items-center justify-center">
      {/* Animated pulse rings */}
      {isListening &&
        [0, 1, 2].map((index) => (
          <div
            className="absolute inset-0 animate-ping rounded-full border-2 border-destructive/30"
            key={index}
            style={{
              animationDelay: `${index * 0.3}s`,
              animationDuration: "2s",
            }}
          />
        ))}

      {/* Main record button */}
      <Button
        type="button"
        className={cn(
          "relative z-10 rounded-full transition-all duration-300",
          isListening
            ? "bg-destructive text-destructive-foreground hover:bg-destructive/80 hover:text-destructive-foreground"
            : "bg-primary text-primary-foreground hover:bg-primary/80 hover:text-primary-foreground",
          className
        )}
        disabled={isDisabled}
        onClick={toggleListening}
        {...props}
        aria-label={isListening ? "停止语音输入" : props["aria-label"] ?? "语音输入"}
        aria-pressed={isListening}
        title={mode === "none" || (mode === "media-recorder" && !onAudioRecorded) ? "当前浏览器不支持语音识别，请使用支持语音识别的浏览器。" : undefined}
      >
        {isProcessing && <Spinner />}
        {!isProcessing && isListening && <SquareIcon className="size-4" />}
        {!(isProcessing || isListening) && <MicIcon className="size-4" />}
      </Button>
    </div>
  )
}
