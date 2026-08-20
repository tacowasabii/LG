/**
 * 내 기억 더하기 — 글 · 목소리 · 사진 · 영상
 *
 * 다른 가족이 만든 추억 아래에 붙는 입력이다. 원본을 고치는 폼이 아니라는 것이
 * 이 컴포넌트의 전제다. 그래서 제목·날짜·장소를 건드릴 칸이 없다. 있는 것은
 * "무엇이 기억나는가" 하나뿐이다.
 *
 * 목소리는 녹음과 전사를 동시에 돌린다 (lib/recorder.ts · lib/transcriber.ts).
 * 인식이 실패해도 녹음은 남는다 — 목소리 원본이 자산이고 글은 색인이다.
 * 기계가 옮긴 글은 source_type=ai_stt로 보내고, 서버가 읽기 좋게 다듬으면서
 * 원문을 그대로 보존한다 (기획안 07).
 *
 * "조금 다르게 기억해요"는 눌러도 되고 안 눌러도 된다. 눌러도 원본은 바뀌지
 * 않고, 상세 화면에 "가족들이 조금 다르게 기억하고 있어요" 한 줄이 뜬다.
 * 누가 맞는지는 아무도 판정하지 않는다.
 */

import { useEffect, useRef, useState } from 'react'
import { Camera, Mic, Square } from 'lucide-react'
import { addMemoryContribution, mediaUrl, uploadMedia, uploadVoice } from '../lib/api'
import { useCurrentUser } from '../lib/currentUser'
import { Recording, VoiceRecorder, isRecordingSupported } from '../lib/recorder'
import { LiveTranscriber, TranscriberError, isTranscriptionSupported } from '../lib/transcriber'
import { invalidateEvents, invalidateVoiceClips } from '../lib/useGraphData'

interface Attachment {
  id: string
  /** 미리보기용 그림. 영상도 첫 장면이 있으면 그림이다 (lib/videoMeta.ts) */
  thumb: string | null
  /** 원본 경로. 그림이 없는 영상만 여기로 떨어진다 */
  file_path: string
  media_type: string
  filename: string
}

interface Props {
  eventId: string
  /** 저장이 끝난 뒤. 목록·상세가 다시 읽는다 */
  onSaved: () => void
  onCancel?: () => void
  /** 자리 표시 문구 (추억 제목을 넣어 준다) */
  placeholder?: string
}

export default function MemoryComposer({ eventId, onSaved, onCancel, placeholder }: Props) {
  const { current } = useCurrentUser()

  const [text, setText] = useState('')
  const [differs, setDiffers] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 사진·영상
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [uploading, setUploading] = useState(false)

  // 목소리
  const recorder = useRef<VoiceRecorder | null>(null)
  const transcriber = useRef<LiveTranscriber | null>(null)
  const [recording, setRecording] = useState(false)
  const [recordSec, setRecordSec] = useState(0)
  const [pending, setPending] = useState<Recording | null>(null)
  const [interim, setInterim] = useState('')
  /** 지금 입력란의 글을 기계가 옮겼는가 (사람이 고치면 꺼진다) */
  const [fromMachine, setFromMachine] = useState(false)
  const [sttError, setSttError] = useState<string | null>(null)

  const canRecord = isRecordingSupported()
  const canTranscribe = isTranscriptionSupported()

  useEffect(() => {
    if (!recording) return
    const timer = setInterval(() => setRecordSec((s) => s + 1), 1000)
    return () => clearInterval(timer)
  }, [recording])

  useEffect(
    () => () => {
      // 화면을 떠날 때 마이크를 놓아준다
      transcriber.current?.stop()
      if (pending) URL.revokeObjectURL(pending.previewUrl)
    },
    [pending],
  )

  const toggleRecording = async () => {
    if (recording) {
      transcriber.current?.stop()
      transcriber.current = null
      setInterim('')
      try {
        const recorded = await recorder.current!.stop()
        setPending(recorded)
      } catch (e) {
        console.error(e)
        setError('녹음을 저장하지 못했습니다.')
      } finally {
        recorder.current = null
        setRecording(false)
      }
      return
    }

    try {
      recorder.current = new VoiceRecorder()
      await recorder.current.start()
      setPending(null)
      setRecordSec(0)
      setRecording(true)
      setSttError(null)
      setFromMachine(false)

      // 인식은 곁다리다. 실패해도 녹음은 계속된다.
      if (canTranscribe) {
        transcriber.current = new LiveTranscriber()
        transcriber.current.start({
          onUpdate: ({ final, interim: partial }) => {
            setText(final)
            setInterim(partial)
            setFromMachine(true)
          },
          onError: (e: TranscriberError) => setSttError(e.message),
        })
      }
    } catch (e) {
      console.error(e)
      recorder.current = null
      setError('마이크를 쓸 수 없습니다. 브라우저 권한을 확인해 주세요.')
    }
  }

  const discardRecording = () => {
    if (pending) URL.revokeObjectURL(pending.previewUrl)
    setPending(null)
    setRecordSec(0)
    // 버린 녹음의 전사만 남으면 근거 없는 문장이 된다
    if (fromMachine) {
      setText('')
      setFromMachine(false)
    }
    setInterim('')
  }

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setUploading(true)
    setError(null)
    for (const file of Array.from(files)) {
      try {
        const uploaded = await uploadMedia(file)
        setAttachments((prev) => [
          ...prev,
          {
            id: uploaded.id,
            thumb: uploaded.thumbnail_path || null,
            file_path: uploaded.file_path,
            media_type: uploaded.media_type,
            filename: uploaded.original_filename,
          },
        ])
      } catch (e) {
        console.error(e)
        setError(`${file.name} 을 올리지 못했습니다.`)
      }
    }
    setUploading(false)
  }

  const save = async () => {
    const content = text.trim()
    if (!content || saving) return
    setSaving(true)
    setError(null)

    try {
      // 녹음이 있으면 먼저 올려서 이 기억의 근거로 매단다
      let audioMediaId: string | undefined
      if (pending) {
        try {
          const uploaded = await uploadVoice(pending.blob, {
            durationSec: pending.durationSec,
            waveform: pending.waveform,
            transcript: content,
            transcriptSource: fromMachine ? 'ai_stt' : undefined,
            speakerId: current?.id,
            eventId,
          })
          audioMediaId = uploaded.id
          invalidateVoiceClips()
        } catch (e) {
          console.error(e)
          setError('목소리를 저장하지 못했습니다. 글로 남긴 기억은 저장됩니다.')
        }
        URL.revokeObjectURL(pending.previewUrl)
        setPending(null)
      }

      await addMemoryContribution(eventId, {
        content,
        media_ids: attachments.map((a) => a.id),
        audio_media_id: audioMediaId,
        differs,
        // 고치지 않은 전사문은 기계가 쓴 문장이다. 그렇게 밝혀야 서버가
        // 원문을 보존하면서 다듬은 문장을 따로 남긴다.
        source_type: fromMachine ? 'ai_stt' : 'user_input',
      })

      invalidateEvents()
      setText('')
      setAttachments([])
      setDiffers(false)
      setFromMachine(false)
      setRecordSec(0)
      onSaved()
    } catch (e) {
      console.error(e)
      setError('기억을 더하지 못했습니다. 다시 시도해 주세요.')
    } finally {
      setSaving(false)
    }
  }

  const inputId = `composer-files-${eventId}`

  return (
    <div className="rounded-lg bg-ink-50 p-5">
      <p className="t-caption m-0">
        {current?.name ?? '지금 쓰는 사람'}님의 기억으로 남습니다 · 원래 기록은 그대로 있습니다
      </p>

      <textarea
        value={recording && interim ? text + interim : text}
        onChange={(e) => {
          setText(e.target.value)
          // 사람이 손대면 더 이상 기계가 쓴 문장이 아니다
          setFromMachine(false)
        }}
        rows={3}
        placeholder={placeholder || '기억나는 것을 말하듯이 적어도 됩니다.'}
        className="field mt-3 w-full resize-y text-sm"
      />

      {/* 목소리 · 사진 — 녹음을 못 쓰는 브라우저에서도 사진은 붙일 수 있어야 한다 */}
      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        {canRecord && (
          <button
            onClick={toggleRecording}
            disabled={saving}
            className="flex cursor-pointer items-center gap-1.5 rounded bg-transparent px-3 py-1.5
                       text-xs disabled:opacity-40"
            style={
              recording
                ? { border: '1px solid var(--critical)', color: 'var(--critical-ink)' }
                : { border: '1px solid var(--border-strong)', color: 'var(--ink-500)' }
            }
          >
            {recording ? <Square size={13} /> : <Mic size={13} />}
            {recording ? `녹음 중 ${recordSec}초 · 멈추기` : '말로 남기기'}
          </button>
        )}

        {pending && !recording && (
          <>
            <audio src={pending.previewUrl} controls className="h-8" />
            <button onClick={discardRecording} className="btn-link text-[11px]">
              녹음 버리기
            </button>
          </>
        )}

        <label
            className="flex cursor-pointer items-center gap-1.5 rounded bg-transparent px-3 py-1.5
                       text-xs text-ink-500"
            style={{ border: '1px solid var(--border-strong)' }}
          >
            <Camera size={13} />
            {uploading ? '올리는 중…' : '사진 · 영상'}
            <input
              id={inputId}
              type="file"
              multiple
              accept="image/*,video/*"
              className="hidden"
              onChange={(e) => handleFiles(e.target.files)}
          />
        </label>
      </div>

      {fromMachine && text && !recording && (
        <p className="t-caption m-0 mt-2">
          AI가 옮긴 글입니다. 고치면 사람이 쓴 문장으로 저장되고, 그대로 두면 원문과 함께
          보존됩니다.
        </p>
      )}
      {sttError && (
        <p className="t-caption m-0 mt-2" style={{ color: 'var(--critical-ink)' }}>
          {sttError} — 녹음은 그대로 저장됩니다.
        </p>
      )}

      {/* 함께 올린 사진·영상 */}
      {attachments.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {attachments.map((item) => (
            <span key={item.id} className="relative">
              {/* 첫 장면이 있으면 그림으로 그린다. 영상 원본을 미리보기로
                  물리면 칩 하나에 수십 MB가 붙는다 (lib/videoMeta.ts). */}
              {item.thumb ? (
                <img
                  src={mediaUrl(item.thumb)}
                  alt=""
                  className="h-14 w-20 rounded bg-ink-100 object-cover"
                />
              ) : item.media_type === 'video' ? (
                <video
                  src={mediaUrl(item.file_path)}
                  preload="metadata"
                  className="h-14 w-20 rounded bg-ink-100 object-cover"
                  muted
                  playsInline
                />
              ) : (
                <img
                  src={mediaUrl(item.file_path)}
                  alt=""
                  className="h-14 w-20 rounded bg-ink-100 object-cover"
                />
              )}
              <button
                onClick={() =>
                  setAttachments((prev) => prev.filter((a) => a.id !== item.id))
                }
                title="이 기억에서 빼기"
                className="absolute -right-1.5 -top-1.5 h-5 w-5 cursor-pointer rounded-full
                           border-0 text-[11px] leading-none"
                style={{ background: 'var(--ink-700)', color: 'var(--paper-pure)' }}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <label className="flex cursor-pointer items-center gap-2 text-[13px] text-ink-500">
          <input
            type="checkbox"
            checked={differs}
            onChange={(e) => setDiffers(e.target.checked)}
          />
          조금 다르게 기억해요
        </label>

        <span className="flex gap-2">
          {onCancel && (
            <button
              onClick={onCancel}
              className="cursor-pointer rounded border-0 bg-transparent px-4 py-2 text-[13px]
                         text-ink-400"
            >
              닫기
            </button>
          )}
          <button
            onClick={save}
            disabled={!text.trim() || saving}
            className="btn-primary px-4 py-2 text-[13px] disabled:opacity-40"
          >
            {saving ? '남기는 중…' : '내 기억 더하기'}
          </button>
        </span>
      </div>

      {differs && (
        <p className="t-caption m-0 mt-2">
          원래 기록은 고치지 않습니다. 두 기억이 나란히 남고, 화면에는 “가족들이 조금 다르게
          기억하고 있어요”라고만 표시됩니다.
        </p>
      )}

      {error && (
        <p className="t-body-sm m-0 mt-3" style={{ color: 'var(--critical-ink)' }}>
          {error}
        </p>
      )}
    </div>
  )
}
