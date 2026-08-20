/**
 * Memory Film (기획안 02장 CORE · STORY)
 *
 * 하나의 사건에 연결된 사진·영상·음성을 30~60초 이야기로 묶는다.
 * 기획안의 진정성 원칙에 따라 장면마다 원본 출처와 적용된 AI 효과를 드러낸다.
 *
 * AI 효과 표시에 경고색을 쓰지 않는다. AI가 손을 댄 것은 잘못이 아니라 사실이고,
 * 사실은 조용히 적으면 된다 — 보라색 알약은 "여기까지가 원본, 여기부터가 생성"의
 * 경계를 알려주는 표지판이지 경보가 아니다. 효과가 없는 장면은 teal로 "원본
 * 그대로"라고 밝혀, 둘 중 어느 쪽인지 화면에서 늘 읽히게 한다.
 *
 * 장면 구성은 POST /api/film 이 그래프에서 조립한다. 길이와 대상 세대를 넘기면
 * 서버가 장면을 자르고 내레이션을 확인된 기록 안에서만 쓴다.
 *
 * 사진에 클립(motion_url)이 있으면 그것을 재생하고, 없으면 원본 사진에 CSS
 * 카메라 움직임을 건다. 어느 쪽인지는 서버가 정하고 AI 라벨에 그대로 적힌다.
 *
 * 클립을 만드는 중(motion_pending)이면 이야기를 내주지 않고 "만들고 있어요"를
 * 보여준다. 바로 재생하면 처음 본 사람은 줌만 되는 화면을 이 기능의 결과로 읽고,
 * 조금 뒤에 사진이 저절로 영상으로 바뀌는 것이 고장처럼 보인다. 한 장에 40초씩
 * 걸리는 일이라 빠져나갈 길("기다리지 않고 먼저 보기")은 함께 둔다.
 *
 * 배경 음악도 무엇을 깔지는 서버가 정하고(무드), 소리는 화면이 만든다
 * (lib/filmMusic.ts). 음원 파일이 아니라 무드만 내려오므로 화면이 합성한다 —
 * narrator가 브라우저 목소리를 쓰는 것과 같은 분업이다. 앱이 만든 소리라는 사실과
 * 그 무드를 고른 근거를 함께 적고, 가족의 목소리가 나는 동안에는 음량을 낮춘다.
 *
 * 남은 교체 지점: 미리보기 진행바 -> 장면 전체를 이어 붙인 영상 플레이어
 */

import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Anniversary,
  FilmStoryboard,
  composeFilm,
  getAnniversaries,
  getMotionStatus,
  mediaUrl,
} from '../lib/api'
import { AUDIENCE_DESC, AUDIENCE_LABEL, Audience, FilmLength } from '../lib/filmOptions'
import { useEvents, useVoiceClips } from '../lib/useGraphData'
import { usePrefersReducedMotion } from '../lib/reducedMotion'
import { useNarrator } from '../lib/narrator'
import { useFilmMusic } from '../lib/filmMusic'
import { Page, PageHeader } from '../components/Page'
import AudioClip from '../components/AudioClip'
import RichText from '../components/RichText'

const LENGTHS: FilmLength[] = [30, 45, 60]
const AUDIENCES: Audience[] = ['child', 'adult', 'elder']

/** 초를 "1분 20초"처럼 읽는 말로. 0이면 "곧" */
function formatWait(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds))
  if (whole === 0) return '곧'
  if (whole < 60) return `${whole}초`
  const minutes = Math.floor(whole / 60)
  const rest = whole % 60
  return rest ? `${minutes}분 ${rest}초` : `${minutes}분`
}

/**
 * 서버가 고른 움직임을 CSS 클래스로 옮긴다.
 *
 * 무엇을 걸지 화면이 정하지 않는다. 예전에는 여기서 장면 순서로 골랐는데
 * 서버가 라벨을 붙이는 순서와 달라서, 화면에 적힌 효과와 실제로 걸린 효과가
 * 네 경우 모두 어긋나 있었다 (backend/services/film_composer.py CAMERA_MOTIONS).
 */
const MOTION_CLASS: Record<string, string> = {
  'zoom-in': 'motion-zoom-in',
  'pan-left': 'motion-pan-left',
  'zoom-out': 'motion-zoom-out',
  'pan-right': 'motion-pan-right',
}

export default function FilmPage() {
  const { events } = useEvents()
  const { clips } = useVoiceClips()
  const [searchParams] = useSearchParams()
  /*
    ?event=E01로 들어오면 그 사건으로 시작한다. 타임라인·지도에서 사건을 크게
    보다가 "한 편의 이야기로 보기"를 누르는 길이다 — 여기서 사건을 다시 고르게
    하면 방금 보던 사건을 이름으로 찾아야 한다.

    들어온 뒤 칩으로 다른 사건을 고르면 주소는 그대로 둔다. 이 값은 시작점일
    뿐이고, 주소를 따라 고쳐 쓰면 뒤로 가기가 사건 선택을 되짚는 기록이 된다.
  */
  const [eventId, setEventId] = useState<string | null>(searchParams.get('event'))
  const [length, setLength] = useState<FilmLength>(45)
  const [audience, setAudience] = useState<Audience>('adult')
  const [board, setBoard] = useState<FilmStoryboard | null>(null)
  const [composing, setComposing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [anniversaries, setAnniversaries] = useState<Anniversary[]>([])
  const [playing, setPlaying] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  /*
    미세 움직임을 만드는 동안은 이야기를 내주지 않는다.

    예전에는 바로 재생되다가 도중에 사진이 하나씩 영상으로 바뀌었다. 그러면
    처음 본 사람은 "줌만 되는 화면"을 이 기능의 결과로 읽고, 조금 뒤에 화면이
    저절로 달라지는 것이 고장처럼 보인다. 만드는 중이라고 밝히고 다 되면
    시작하는 편이 정직하다.

    total은 이 사건에서 만들기 시작한 장수다 (진행률의 분모).
    skipWait은 기다리지 않고 먼저 보겠다고 누른 경우 — 40초씩 걸리는 일이라
    빠져나갈 길은 있어야 한다.
  */
  const [motionTotal, setMotionTotal] = useState(0)
  const [waitedSec, setWaitedSec] = useState(0)
  const [skipWait, setSkipWait] = useState(false)
  const [musicOn, setMusicOn] = useState(true)
  // 지금 이 장면의 가족 음성이 나고 있는가. AudioClip만 아는 값이라 받아 둔다.
  const [voicePlaying, setVoicePlaying] = useState(false)
  const reducedMotion = usePrefersReducedMotion()
  const narrator = useNarrator()
  const music = useFilmMusic()

  // 사진이 가장 많은 사건에서 시작한다 (이야기가 될 자료가 있는 쪽)
  useEffect(() => {
    if (eventId || events.length === 0) return
    const richest = [...events].sort((a, b) => b.media_count - a.media_count)[0]
    setEventId(richest.id)
  }, [events, eventId])

  useEffect(() => {
    getAnniversaries().then(setAnniversaries).catch(console.error)
  }, [])

  // 사건·길이·대상이 바뀌면 서버가 다시 구성한다
  useEffect(() => {
    if (!eventId) return

    let cancelled = false
    setComposing(true)
    setError(null)
    setPlaying(false)
    setElapsed(0)
    // 기다림은 사건마다 새로 센다. 다른 사건으로 옮기면 앞서 기다린 시간과
    // "먼저 보기"를 눌렀던 것도 그 사건의 이야기다.
    setMotionTotal(0)
    setWaitedSec(0)
    setSkipWait(false)

    composeFilm(eventId, length, audience)
      .then((result) => {
        if (!cancelled) setBoard(result)
      })
      .catch((e) => {
        console.error(e)
        if (!cancelled) {
          setBoard(null)
          setError('이 사건으로는 아직 이야기를 만들 수 없습니다. 사진이나 영상을 먼저 연결해주세요.')
        }
      })
      .finally(() => {
        if (!cancelled) setComposing(false)
      })

    return () => {
      cancelled = true
    }
  }, [eventId, length, audience])

  const scenes = board?.scenes ?? []
  const totalSec = board?.total_sec ?? 0
  const motionPending = board?.motion_pending ?? []
  const filmMusic = board?.music ?? null

  /** 아직 만들고 있어서 이야기를 내주지 않는 상태 */
  const waitingForMotion = motionPending.length > 0 && !skipWait
  /** 이 사건에서 만들기 시작한 장수 중 끝난 것 */
  const motionDone = Math.max(0, motionTotal - motionPending.length)

  // 분모는 줄지 않는다 — 하나 끝날 때마다 전체도 같이 줄면 진행률이 늘 100%다
  useEffect(() => {
    setMotionTotal((prev) => Math.max(prev, motionPending.length))
  }, [motionPending.length])

  // 기다리는 동안 초를 센다. 숫자가 늘지 않으면 멈춘 화면으로 읽힌다.
  useEffect(() => {
    if (!waitingForMotion) return
    const timer = window.setInterval(() => setWaitedSec((s) => s + 1), 1000)
    return () => window.clearInterval(timer)
  }, [waitingForMotion])

  /*
    아직 만들고 있는 클립을 기다린다.

    서버는 클립이 없는 사진을 그 자리에서 만들기 시작하고 바로 응답한다
    (한 장에 40초쯤 걸린다). 여기서 잠시 뒤 되물어, 준비된 것만 그 장면에
    바꿔 끼운다 — 화면을 처음부터 다시 그리지 않는다.

    composeFilm을 다시 부르지 않는 이유는 그쪽이 내레이션을 위해 모델을
    호출하기 때문이다. 되묻는 값이 응답 시간과 돈으로 돌아온다.

    실패한 것은 서버가 failed로 알려주고 다시 맡지 않는다. 그것까지 빠지면
    기다릴 것이 없어져 되묻기가 멈춘다.
  */
  useEffect(() => {
    if (motionPending.length === 0) return

    let cancelled = false
    const timer = window.setInterval(async () => {
      try {
        const status = await getMotionStatus(motionPending)
        if (cancelled) return

        const arrived = Object.keys(status.ready)
        const settled = new Set([...arrived, ...Object.keys(status.failed)])
        if (settled.size === 0) return

        setBoard((prev) => {
          if (!prev) return prev
          return {
            ...prev,
            scenes: prev.scenes.map((scene) => {
              const clip = status.ready[scene.media_id]
              if (!clip) return scene
              return {
                ...scene,
                motion_url: clip.file,
                thumb: clip.poster || scene.thumb,
                // 라벨과 카메라 움직임도 서버가 준 대로 바꾼다. 클립이 도는
                // 장면에 CSS 움직임을 겹쳐 두면 어지럽고, 라벨이 "느린 줌 인"
                // 으로 남으면 화면이 하지 않는 일을 했다고 적는 셈이다.
                motion: null,
                ai_effects: [clip.label],
              }
            }),
            motion_pending: prev.motion_pending?.filter((id) => !settled.has(id)) ?? [],
          }
        })
      } catch (e) {
        console.error(e)
      }
    }, 8000)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
    // motionPending의 내용이 바뀔 때만 다시 건다 (배열 정체성이 아니라 값 기준)
  }, [motionPending.join(',')])

  /*
    채울 수 있는 길이만 고르게 한다.

    서버는 사진 한 장을 세워 두는 시간에 상한을 둔다 (film_composer.PHOTO_MAX_SEC).
    그래서 사진 세 장뿐인 사건은 60초를 채울 방법이 없고, 예전에는 그 60초가
    눌리기는 하는데 눌러도 영상이 그대로였다. 자료로 닿을 수 없는 길이는 잠근다.

    가장 짧은 길이는 잠그지 않는다. 사진 한 장뿐인 사건이면 30초에도 닿지 못하는데
    거기서 전부 잠그면 아무것도 고를 수 없는 자리가 된다 — 그때는 짧게 나오고
    아래 문구가 몇 초까지였는지 밝힌다.
  */
  const maxSec = board?.max_sec ?? 0
  const reachable = (l: FilmLength) => l <= maxSec || l === LENGTHS[0]

  useEffect(() => {
    if (!board) return
    // 대상 세대를 바꾸면 닿을 수 있는 길이도 바뀐다 (아이용은 장면이 짧아 총 길이가
    // 준다). 고른 길이가 잠기면 닿는 것 중 가장 긴 쪽으로 내려온다 — 잠긴 버튼이
    // 켜진 채로 남아 있으면 무엇이 만들어졌는지 화면이 거짓말을 한다.
    if (length <= board.max_sec) return
    const fits = LENGTHS.filter((l) => l <= board.max_sec)
    // 닿는 것이 하나도 없으면(사진 한 장뿐인 사건 — 16초) 가장 짧은 쪽으로 내려온다.
    // 그 자리는 잠기지 않아서(reachable) 고를 수 있고, 아래 문구가 몇 초까지인지
    // 밝힌다. 예전에는 여기서 아무것도 하지 않아 45초가 잠긴 채로 켜져 있었다.
    setLength(fits.length > 0 ? fits[fits.length - 1] : LENGTHS[0])
  }, [board, length])

  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => {
      setElapsed((prev) => {
        const next = prev + 0.25
        if (next >= totalSec) {
          setPlaying(false)
          return totalSec
        }
        return next
      })
    }, 250)
    return () => window.clearInterval(timer)
  }, [playing, totalSec])

  /*
    이야기가 멈추면 음악도 멈춘다.

    멈추는 길이 여럿이다 — 일시정지 · 끝까지 재생 · 사건·길이·대상 변경. 한 자리에서
    받아야 어느 길로 멈춰도 소리가 남지 않는다.

    시작은 여기서 하지 못한다. 소리는 사용자 동작 없이 시작할 수 없어서(자동재생
    정책) 재생 버튼 클릭 안에서 부른다.
  */
  useEffect(() => {
    if (!playing) music.stop()
  }, [playing, music.stop])

  /*
    가족의 목소리·낭독이 나는 동안 배경 음악을 낮춘다.

    끄지 않고 낮춘다. 목소리 한 마디마다 음악이 꺼졌다 켜지면 그 편집이 목소리보다
    더 들린다. 배경 음악이 할머니 목소리를 덮는 것은 이 제품에서 가장 중요한 자산을
    우리가 가리는 일이라, 어느 쪽이든 목소리가 이긴다.
  */
  useEffect(() => {
    music.duck(narrator.speaking || voicePlaying)
  }, [narrator.speaking, voicePlaying, music.duck])

  // 현재 재생 위치가 몇 번째 장면인지
  let acc = 0
  let currentIndex = 0
  for (let i = 0; i < scenes.length; i++) {
    acc += scenes[i].duration_sec
    if (elapsed < acc) {
      currentIndex = i
      break
    }
    currentIndex = i
  }
  const currentScene = scenes[currentIndex]
  const voice = currentScene?.voice_id
    ? clips.find((c) => c.id === currentScene.voice_id)
    : undefined

  return (
    <Page width={1000}>
      <PageHeader
        eyebrow="Memory Film"
        title="한 사건, 한 편의 이야기"
        lead="사진·영상·음성을 짧은 이야기로 묶습니다. 장면마다 원본 출처와 적용된 AI 효과를 함께 남깁니다."
      />

      <div
        className="mt-9 py-5"
        style={{
          borderTop: '1px solid var(--border)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <p className="t-eyebrow m-0 mb-2.5 text-ink-300">어떤 사건으로 만들까요</p>
        <div className="flex flex-wrap gap-1.5">
          {events.map((event) => {
            const ready = event.media_count > 0
            /*
              자료가 없는 사건은 눌러도 아무 일이 없는 칩으로 두지 않는다.
              사진첩에서 사진을 다 지우면 사건은 남고(원본을 지울 때 끊기는 것은
              연결뿐이다) 여기에 옅은 칩으로 계속 뜨는데, 예전에는 그것을 치울
              길이 이 화면에 없었다. 상세로 보낸다 — 거기서 사진을 더하거나
              추억을 지운다.
            */
            if (!ready) {
              return (
                <Link
                  key={event.id}
                  to={`/memory/${event.id}`}
                  className="chip text-ink-200"
                  title="자료가 없어 장면을 만들 수 없습니다. 상세에서 사진을 더하거나 추억을 지울 수 있습니다."
                >
                  {event.title.replace(/^\d{4}\s*/, '')}
                </Link>
              )
            }
            return (
              <button
                key={event.id}
                onClick={() => setEventId(event.id)}
                className={`chip ${eventId === event.id ? 'chip-on' : ''}`}
              >
                {event.title.replace(/^\d{4}\s*/, '')}
              </button>
            )
          })}
        </div>
        {events.some((event) => event.media_count === 0) && (
          <p className="t-caption m-0 mt-2">
            옅은 사건은 연결된 사진·영상이 없어 이야기를 만들 수 없습니다. 누르면 그
            추억으로 가서 사진을 더하거나 추억을 지울 수 있습니다.
          </p>
        )}
      </div>

      <div className="mt-6 grid grid-cols-2 gap-8">
        <div>
          <p className="t-eyebrow m-0 mb-2.5 text-ink-300">길이</p>
          <div className="flex gap-1.5">
            {LENGTHS.map((l) => (
              <button
                key={l}
                disabled={!reachable(l)}
                onClick={() => setLength(l)}
                className={`tab ${length === l ? 'tab-on' : ''}`}
                title={reachable(l) ? undefined : `연결된 자료로는 ${maxSec}초까지 만들 수 있습니다`}
              >
                {l}초
              </button>
            ))}
          </div>
          <p className="t-caption mt-2.5">
            장면 {scenes.length}개 · {totalSec}초
          </p>
          {board && maxSec < LENGTHS[LENGTHS.length - 1] && (
            <p className="t-caption m-0 mt-1">
              연결된 자료로는 {maxSec}초까지입니다. 사진 한 장을 오래 세워 두면 이야기가
              아니라 정지 화면이 되기 때문입니다 — 사진이나 영상을 더 연결하면 긴 길이가
              열립니다.
            </p>
          )}
        </div>

        <div>
          <p className="t-eyebrow m-0 mb-2.5 text-ink-300">누구에게 보여줄까요</p>
          <div className="flex gap-1.5">
            {AUDIENCES.map((a) => (
              <button
                key={a}
                onClick={() => setAudience(a)}
                className={`tab ${audience === a ? 'tab-on' : ''}`}
              >
                {AUDIENCE_LABEL[a]}
              </button>
            ))}
          </div>
          <p className="t-caption mt-2.5">{AUDIENCE_DESC[audience]}</p>
        </div>
      </div>

      {composing && (
        <p className="t-body-sm mt-8 text-ink-300">이야기를 구성하고 있어요…</p>
      )}

      {error && !composing && (
        <p className="t-body-sm mt-8" style={{ color: 'var(--critical-ink)' }}>
          {error}
        </p>
      )}

      {board && waitingForMotion && (
        /*
          만드는 중에는 이야기를 내주지 않는다.

          바로 재생하면 처음 본 사람은 "줌만 되는 화면"을 이 기능의 결과로 읽고,
          조금 뒤에 사진이 저절로 영상으로 바뀌는 것이 고장처럼 보인다.

          기다리게 하는 대신 세 가지를 보여준다 — 몇 장 중 몇 장이 됐는지, 몇 초
          기다렸는지, 얼마나 더 걸릴지. 그리고 빠져나갈 길을 둔다. 한 장에 40초씩
          걸리는 일이라 갇히면 안 된다.
        */
        <div className="surface mt-8 px-7 py-8">
          <p className="t-eyebrow m-0 text-ink-300">Memory Film</p>
          <p className="m-0 mt-2.5 text-[19px] font-semibold text-ink-900">
            이 이야기를 만들고 있어요
          </p>
          <p className="t-body mt-3 max-w-[58ch]">
            사진이 움직이는 장면으로 바뀌는 중입니다. 한 장에 40초쯤 걸리고, 다 되면
            이야기가 시작됩니다.
          </p>

          <div className="mt-7">
            <div className="h-0.5" style={{ background: 'var(--ink-100)' }}>
              <div
                className="h-0.5"
                style={{
                  background: 'var(--accent)',
                  width: (motionTotal ? (motionDone / motionTotal) * 100 : 0) + '%',
                  transition: 'width 400ms var(--ease-out)',
                }}
              />
            </div>
            <div className="mt-2 flex justify-between">
              <span className="t-mono text-[11px] text-ink-400">
                {motionDone} / {motionTotal}장 완료
              </span>
              <span className="t-mono text-[11px] text-ink-400">
                {formatWait(waitedSec)} 기다림 · 약 {formatWait(motionPending.length * 40)} 남음
              </span>
            </div>
          </div>

          <p className="t-caption mt-5 max-w-[58ch]">
            만드는 것은 파도·불꽃·머리카락처럼 저절로 움직이는 것뿐입니다. 인물의
            행동이나 표정은 만들지 않습니다.
          </p>

          <button onClick={() => setSkipWait(true)} className="btn-quiet mt-5">
            기다리지 않고 먼저 보기
          </button>
        </div>
      )}

      {board && currentScene && !waitingForMotion && (
        <>
          <div className="surface mt-8 overflow-hidden">
            <div
              className="relative aspect-video overflow-hidden"
              style={{ background: 'var(--ink-900)' }}
            >
              {currentScene.motion_url && !reducedMotion ? (
                /* 미리 만들어 둔 미세 모션 클립. 실패해도 poster(원본 썸네일)가
                   남아 화면이 비지 않는다. */
                <video
                  key={currentScene.media_id}
                  src={mediaUrl(currentScene.motion_url)}
                  poster={mediaUrl(currentScene.thumb)}
                  className="h-full w-full object-cover"
                  autoPlay
                  loop
                  muted
                  playsInline
                />
              ) : (
                <img
                  key={currentScene.media_id}
                  src={mediaUrl(currentScene.thumb)}
                  alt=""
                  className={`h-full w-full object-cover ${
                    (currentScene.motion && MOTION_CLASS[currentScene.motion]) || ''
                  }`}
                  /* index.css의 9초 고정을 장면 길이로 덮는다. 세대별 배속과
                     목소리 길이 때문에 장면은 6~11초로 갈리는데, 애니메이션이
                     9초로 굳어 있으면 짧은 장면은 잘리고 긴 장면은 끝에서
                     멈춰 선다 — 움직임이 있다고 적어 둔 동안 정지 화면이다.

                     focus가 오면 그 지점을 확대의 중심으로 삼는다. 가족이 더한
                     기억이 가리키는 인물이 사진에서 있는 자리이고, 어디인지는
                     서버가 정한다 (backend/services/memory_context.focus_of).
                     자르지 않는다 — 같은 원본을 다른 중심으로 확대할 뿐이다. */
                  style={{
                    animationDuration: currentScene.duration_sec + 's',
                    transformOrigin: currentScene.focus
                      ? `${currentScene.focus.x * 100}% ${currentScene.focus.y * 100}%`
                      : undefined,
                  }}
                />
              )}
              <div
                className="absolute inset-0"
                style={{
                  background:
                    'linear-gradient(to top, rgba(14,13,11,0.82) 0%, rgba(14,13,11,0.08) 55%, rgba(14,13,11,0.32) 100%)',
                }}
              />

              {/* AI 라벨 — 생성 요소를 숨기지 않는다.
                  움직임을 끈 사용자에게는 걸리지 않은 효과를 적지 않는다.
                  화면은 멈춰 있는데 "AI 생성 미세 움직임"이라고 쓰면, 적용된 것을
                  드러낸다는 원칙이 반대로 뒤집힌다. */}
              <span
                className="absolute right-4 top-4 rounded-full px-3 py-[5px] text-[11px]"
                style={{ background: 'rgba(14,13,11,0.62)', color: 'var(--paper)' }}
              >
                {reducedMotion
                  ? currentScene.ai_effects.length > 0
                    ? '원본 그대로 · 움직임 끔'
                    : '원본 그대로'
                  : currentScene.ai_effects.length > 0
                    ? 'AI 효과 · ' + currentScene.ai_effects.join(' · ')
                    : '원본 그대로'}
              </span>

              <div className="absolute inset-x-0 bottom-0 p-7">
                <p
                  className="m-0 text-[22px] font-semibold tracking-[-0.01em]"
                  style={{ color: 'var(--paper)' }}
                >
                  {currentScene.subtitle}
                </p>
                <p
                  className="m-0 mt-1.5 text-xs"
                  style={{ color: 'rgba(250,250,247,0.62)' }}
                >
                  {currentScene.source_label}
                </p>
              </div>
            </div>

            <div className="px-6 py-5">
              <div className="flex items-center gap-4">
                <button
                  onClick={() => {
                    if (elapsed >= totalSec) setElapsed(0)
                    // 장면마다 실제 가족 음성이 재생되므로 기계 낭독을 겹치지
                    // 않는다. 둘이 함께 나면 어느 쪽이 가족 목소리인지 알 수 없다.
                    narrator.stop()
                    const next = !playing
                    setPlaying(next)
                    // 배경 음악은 이 클릭 안에서 시작해야 한다. 자동재생 정책은
                    // 사용자 동작 안에서만 소리를 열어 준다 — 효과에서 부르면
                    // 브라우저가 막는다. 멈추는 것은 위 효과가 맡는다.
                    if (next && musicOn && filmMusic) {
                      music.start(filmMusic.mood, filmMusic.pace)
                    }
                  }}
                  aria-label={playing ? '일시정지' : '재생'}
                  className="h-[38px] w-[38px] shrink-0 cursor-pointer rounded-full border-0 text-[11px]"
                  style={{ background: 'var(--accent)', color: 'var(--accent-fg)' }}
                >
                  {playing ? '■' : '▶'}
                </button>

                <div className="flex-1">
                  <div className="h-0.5" style={{ background: 'var(--ink-100)' }}>
                    <div
                      className="h-0.5"
                      style={{
                        background: 'var(--accent)',
                        width: (totalSec ? (elapsed / totalSec) * 100 : 0) + '%',
                      }}
                    />
                  </div>
                  <div className="mt-2 flex justify-between">
                    <span className="t-mono text-[11px] text-ink-400">
                      장면 {currentIndex + 1} / {scenes.length}
                    </span>
                    <span className="t-mono text-[11px] text-ink-400">
                      {Math.floor(elapsed)}초 / {totalSec}초
                    </span>
                  </div>
                </div>
              </div>

              {/*
                배경 음악을 밝히는 자리. 무드와 그것을 고른 근거를 함께 적는다 —
                앱이 만든 소리를 가족의 기록처럼 들리게 두지 않는다는 것이 AudioClip이
                정한 경계이고, 여기서도 같다. 끄는 버튼을 문구 옆에 둔다.
              */}
              {filmMusic && (
                <div
                  className="mt-4 flex items-start gap-3 pt-4"
                  style={{ borderTop: '1px solid var(--border)' }}
                >
                  <div className="min-w-0 flex-1">
                    <p className="t-caption m-0">
                      배경 음악 · <strong>{filmMusic.label}</strong> · {filmMusic.reason}
                    </p>
                    <p className="t-caption m-0 mt-0.5">
                      {music.supported
                        ? '앱이 그 자리에서 만드는 소리입니다 — 가족이 남긴 기록이 아닙니다. 가족의 목소리나 낭독이 나는 동안에는 음량을 낮춥니다.'
                        : '이 브라우저에서는 배경 음악을 만들지 못합니다.'}
                    </p>
                  </div>
                  {music.supported && (
                    <button
                      onClick={() => {
                        const next = !musicOn
                        setMusicOn(next)
                        // 재생 중에 켜면 그 자리에서 들린다. 이 클릭이 자동재생
                        // 정책이 요구하는 사용자 동작이다.
                        if (next && playing) music.start(filmMusic.mood, filmMusic.pace)
                        if (!next) music.stop()
                      }}
                      className="btn-quiet shrink-0 whitespace-nowrap"
                    >
                      {musicOn ? '♪ 음악 끄기' : '♪ 음악 켜기'}
                    </button>
                  )}
                </div>
              )}

              {voice && (
                <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--border)' }}>
                  <p className="t-caption m-0 mb-2">이 장면에 함께 재생되는 실제 음성</p>
                  {/* 이 목소리가 나는 동안 배경 음악을 낮춘다 */}
                  <AudioClip clip={voice} compact onPlayingChange={setVoicePlaying} />
                </div>
              )}
            </div>
          </div>

          <div className="mt-8">
            <p className="m-0 text-[19px] font-semibold text-ink-900">
              {board.title}
              <span className="t-caption ml-2.5 text-ink-300">{board.subtitle}</span>
            </p>
            <div className="mt-3 flex items-start gap-3">
              <p className="t-body m-0 max-w-[45em]">
                <RichText text={board.narration} />
              </p>
              {narrator.supported && board.narration && (
                <button
                  onClick={() =>
                    narrator.speaking
                      ? narrator.stop()
                      : narrator.speak(board.narration, { audience })
                  }
                  className="btn-quiet shrink-0 whitespace-nowrap"
                >
                  {narrator.speaking ? '■ 멈추기' : '▶ 소리로 듣기'}
                </button>
              )}
            </div>
            {motionPending.length > 0 && (
              /* 기다리지 않고 먼저 보기를 누른 뒤에만 여기까지 온다. 아직 만드는
                 중이라는 사실은 그때도 밝혀야 한다 — 도중에 사진이 저절로 영상으로
                 바뀌는데 그 이유가 화면에 없으면 고장으로 읽힌다. */
              <p className="t-caption m-0 mt-2">
                사진 {motionPending.length}장은 아직 만들고 있습니다. 지금은 카메라 움직임으로
                재생되고, 준비되면 그 장면이 움직이는 영상으로 바뀝니다.
              </p>
            )}
            {board.omitted_scenes > 0 && (
              <p className="t-caption m-0 mt-2">
                {board.requested_sec}초에 맞추려고 장면 {board.omitted_scenes}개를 뺐습니다.{' '}
                {/* 가장 긴 길이에서도 넘칠 수 있다 (자료가 많은 사건 · 어르신용).
                    그 자리에서 "더 긴 길이를 고르면 된다"고 적으면 없는 길을 가리킨다. */}
                {LENGTHS.some((l) => l > length && reachable(l))
                  ? '더 긴 길이를 고르면 모두 들어갑니다.'
                  : '고를 수 있는 가장 긴 길이라, 나머지는 이 편에 담지 못합니다.'}
              </p>
            )}
            <p className="t-caption mt-3">
              내레이션은 확인된 기록 안에서만 생성됩니다. 원본에 없는 발화·행동은 만들지
              않습니다.
              {narrator.supported ? (
                <>
                  {' '}
                  소리로 들으면 <strong>기계가 읽어 주는 음성</strong>입니다 — 가족의
                  목소리가 아닙니다. 실제 목소리는 장면마다 따로 재생됩니다.
                </>
              ) : (
                ' 이 브라우저에서는 소리로 읽어 주지 못합니다.'
              )}
            </p>
          </div>

          <div className="mt-9">
            <p className="t-eyebrow m-0 mb-1">장면 구성</p>
            <div className="rule-strong mt-3">
              {scenes.map((scene, i) => (
                <div
                  key={scene.media_id}
                  className="flex gap-5 px-1 py-5"
                  style={{
                    borderBottom: '1px solid var(--border)',
                    borderLeft: `2px solid ${i === currentIndex ? 'var(--accent)' : 'transparent'}`,
                  }}
                >
                  <img
                    src={mediaUrl(scene.thumb)}
                    alt=""
                    className="h-20 w-28 shrink-0 rounded bg-ink-50 object-cover"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="t-mono text-[11px] text-ink-300">
                        {i + 1}번째 · {scene.duration_sec}초
                      </span>
                      {scene.voice_id && (
                        <span
                          className="pill font-normal"
                          style={{
                            background: 'var(--accent-soft)',
                            color: 'var(--accent-ink)',
                          }}
                        >
                          실제 음성
                        </span>
                      )}
                    </div>
                    <p className="m-0 mt-1.5 text-[15px] font-semibold text-ink-900">
                      {scene.subtitle}
                    </p>
                    <p className="t-body-sm m-0 mt-1 text-ink-400">{scene.note}</p>
                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                      <span className="pill bg-ink-50 px-[9px] font-normal text-ink-500">
                        {scene.source_label}
                      </span>
                      {!reducedMotion &&
                        scene.ai_effects.map((fx) => (
                          <span
                            key={fx}
                            className="pill px-[9px] font-normal"
                            style={{
                              background: 'var(--warning-soft)',
                              color: 'var(--warning-ink)',
                            }}
                          >
                            AI · {fx}
                          </span>
                        ))}
                      {reducedMotion && scene.ai_effects.length > 0 && (
                        <span
                          className="pill px-[9px] font-normal"
                          style={{
                            background: 'var(--positive-soft)',
                            color: 'var(--positive-ink)',
                          }}
                        >
                          원본 그대로 · 움직임 끔
                        </span>
                      )}
                      {scene.ai_effects.length === 0 && (
                        <span
                          className="pill px-[9px] font-normal"
                          style={{
                            background: 'var(--positive-soft)',
                            color: 'var(--positive-ink)',
                          }}
                        >
                          원본 그대로
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      <div className="mt-9">
        <p className="t-eyebrow m-0 mb-1">다가오는 기념일</p>
        <p className="t-caption m-0 mb-3">
          기념일이 되면 TV 대기화면에서 그날의 Film이 먼저 뜹니다.
        </p>
        <div style={{ borderTop: '1px solid var(--border)' }}>
          {anniversaries.map((a) => (
            <div
              key={a.date}
              className="flex items-center gap-5 px-1 py-4"
              style={{ borderBottom: '1px solid var(--border)' }}
            >
              <span className="t-mono w-[88px] shrink-0 text-xs text-accent-ink">{a.date}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-[15px] font-semibold text-ink-900">{a.label}</span>
                <span className="t-caption mt-0.5 block">{a.reason}</span>
              </span>
              <span className="t-mono whitespace-nowrap text-[11px] text-ink-300">
                {a.days_left}일 남음
              </span>
              {events.find((e) => e.id === a.event_id && e.media_count > 0) ? (
                <button onClick={() => setEventId(a.event_id)} className="btn-quiet">
                  미리 보기
                </button>
              ) : (
                <Link to="/interview" className="btn-outline no-underline hover:no-underline">
                  자료 채우기
                </Link>
              )}
            </div>
          ))}
        </div>
      </div>
    </Page>
  )
}
