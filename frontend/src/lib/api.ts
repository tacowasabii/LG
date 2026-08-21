/**
 * API 클라이언트 - Backend 통신
 */

import { probeVideo } from './videoMeta';

const BASE_URL = import.meta.env.VITE_API_URL || '/api';
const STATIC_MODE = import.meta.env.VITE_STATIC_MODE === 'true';
const MEDIA_BASE = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace('/api', '')
  : '';

/**
 * 지금 보는 사람. 공개 범위(기획안 08장)를 서버가 적용할 수 있게 모든 조회에
 * 함께 보낸다. CurrentUserProvider가 사용자를 바꿀 때 여기에 심는다.
 *
 * 로그인이 붙으면 이 값은 토큰에서 나오고 setViewer는 사라진다.
 */
let viewerId: string | null = null;

export function setViewer(id: string | null): void {
  viewerId = id;
}

export function getViewer(): string | null {
  return viewerId;
}

/** 조회 URL에 열람자를 붙인다 */
function withViewer(url: string): string {
  if (!viewerId) return url;
  return url + (url.includes('?') ? '&' : '?') + 'viewer_id=' + encodeURIComponent(viewerId);
}

/** 미디어 파일 경로를 절대 URL로 변환 */
export function mediaUrl(path: string | null | undefined): string {
  if (!path) return '';
  if (path.startsWith('http')) return path;
  if (STATIC_MODE) return path.replace('/media-files/', '/mock/photos/');
  return `${MEDIA_BASE}${path}`;
}

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  // 정적 모드: public/mock/ JSON에서 읽기
  if (STATIC_MODE && !options?.method) {
    const mockMap: Record<string, string> = {
      '/api/media': '/mock/media.json',
      '/api/graph/events': '/mock/events.json',
      '/api/graph/persons': '/mock/persons.json',
      '/api/graph': '/mock/graph.json',
    };
    // 이벤트 상세 패턴 매칭
    const eventMatch = url.match(/\/api\/graph\/event\/(.+)/);
    if (eventMatch) {
      const response = await fetch(`/mock/events/${eventMatch[1]}.json`);
      return response.json();
    }
    const mockUrl = mockMap[url];
    if (mockUrl) {
      const response = await fetch(mockUrl);
      return response.json();
    }
  }

  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      // 지금 쓰는 사람. 서버가 역할로 쓰기를 막고, 공개 범위를 적용한다.
      // 인증이 아니라 실수 방지 가드다 (backend/services/permissions.py).
      ...(viewerId ? { 'X-Viewer-Id': viewerId } : {}),
      ...options?.headers,
    },
    ...options,
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(`API Error ${response.status}: ${error}`);
  }
  return response.json();
}

/**
 * 서버가 밝힌 이유를 꺼낸다.
 *
 * 권한 거절(403)의 detail은 화면이 지어낼 수 없는 문장이다 —
 * "김하늘님은 열람자입니다. 기록을 지울 수 없습니다."처럼 누가 왜 막혔는지를
 * 담고 있어서, 그대로 보여주는 편이 "실패했습니다"보다 낫다.
 *
 * 같은 네 줄이 화면마다 복사되던 것을 여기로 올렸다 (공개·동의, 가족 공간,
 * 초대 참여에는 아직 각자의 사본이 있다).
 */
export function readDetail(error: unknown, fallback: string): string {
  const message = error instanceof Error ? error.message : String(error);
  const match = message.match(/"detail"\s*:\s*"([^"]+)"/);
  return match ? match[1] : fallback;
}

// --- Media ---

export interface MediaItem {
  id: string;
  media_type: string;
  file_path: string;
  thumbnail_path?: string | null;
  original_filename: string;
  created_at: string;
  exif_date?: string | null;
  // 음성일 때만 채워진다
  duration_sec?: number | null;
  waveform?: number[];
  transcript?: string | null;
  /** 그 글을 누가 썼는지: ai_stt(기계가 옮김) | user_input(사람이 적거나 고침) */
  transcript_source?: string | null;
  speaker_id?: string | null;
  speaker_name?: string | null;
  event_id?: string | null;
  event_title?: string | null;
  /** 인터뷰로 남긴 목소리가 답한 질문 */
  question?: string | null;
}

/**
 * 재생 가능한 가족 음성.
 * AudioClip 컴포넌트가 쓰는 최소 모양이다. file_path가 있으면 실제 파일을
 * 재생하고, 없으면(목데이터) 흉내만 낸다.
 */
export interface VoiceClip {
  id: string;
  file_path?: string | null;
  event_id?: string | null;
  event_title?: string | null;
  speaker_id?: string | null;
  speaker_name?: string | null;
  duration_sec: number;
  transcript?: string | null;
  /** 전사문을 기계가 옮겼는지. 화면이 그렇다고 밝혀야 한다 */
  transcript_source?: string | null;
  recorded_at?: string | null;
  waveform: number[];
  /**
   * 이 목소리가 답한 질문 (AI 인터뷰 녹음).
   * 답만 보여주면 "모르겠어요" 한 마디가 무슨 이야기인지 읽을 수 없다.
   */
  question?: string | null;
}

/** 음성 미디어를 재생용 클립 모양으로 */
export function toVoiceClip(item: MediaItem): VoiceClip {
  return {
    id: item.id,
    file_path: item.file_path,
    event_id: item.event_id,
    event_title: item.event_title,
    speaker_id: item.speaker_id,
    speaker_name: item.speaker_name,
    duration_sec: item.duration_sec || 0,
    transcript: item.transcript,
    transcript_source: item.transcript_source,
    recorded_at: (item.created_at || '').slice(0, 10),
    waveform: item.waveform || [],
    question: item.question,
  };
}

export interface MediaUploadResult {
  id: string;
  media_type: string;
  file_path: string;
  thumbnail_path?: string | null;
  original_filename: string;
  exif_date?: string | null;
  exif_lat?: number | null;
  exif_lng?: number | null;
  /** 좌표에서 짐작한 대략적인 지명 ("부산 해운대구"). 화면은 좌표 숫자 대신 이걸 쓴다 */
  place_guess?: string | null;
  detected_faces: string[];
  /** detected_faces를 누가 정했는지: ai_vision(얼굴 인식) | user_input(사람이 지목) */
  faces_source?: string | null;
  scene_description?: string | null;
  /** 영상·음성일 때. 브라우저가 재서 보낸 값이다 */
  duration_sec?: number | null;
  linked_event_id?: string | null;
  needs_info: boolean;
  message: string;
}

export async function uploadMedia(
  file: File,
  /** 이 기록에 있는 사람. 얼굴 인식이 없으므로 사람이 지목한 것만 붙는다 */
  personIds?: string[],
): Promise<MediaUploadResult> {
  const formData = new FormData();
  formData.append('file', file);
  if (personIds && personIds.length > 0) formData.append('person_ids', personIds.join(','));
  // 올린 사람이 소유자다 (기획안 08장 Asset 권한)
  if (viewerId) formData.append('owner_id', viewerId);

  // 영상은 길이와 첫 장면을 브라우저가 재서 함께 보낸다. 서버에 ffmpeg를 두지
  // 않기 위한 분업이고, 못 뽑으면 그냥 없이 올라간다 (lib/videoMeta.ts).
  if (file.type.startsWith('video/')) {
    const meta = await probeVideo(file);
    if (meta.durationSec != null) formData.append('duration_sec', String(meta.durationSec));
    if (meta.poster) formData.append('poster', meta.poster, 'poster.jpg');
  }
  const response = await fetch(`${BASE_URL}/media/upload`, {
    method: 'POST',
    headers: viewerId ? { 'X-Viewer-Id': viewerId } : undefined,
    body: formData,
  });
  if (!response.ok) throw new Error('Upload failed');
  return response.json();
}

export async function getMediaList(): Promise<MediaItem[]> {
  return fetchJSON(withViewer(`${BASE_URL}/media`));
}

// --- 사진첩 ---

/**
 * 사진첩 한 칸.
 *
 * MediaItem과 나눠 둔 이유: 사진첩은 사건·인물·장소·공개 범위를 한 목록에서
 * 그려야 하는데, 반대로 음성 전용 필드(파형·전사문)는 쓰지 않는다.
 */
export interface AlbumMediaItem {
  id: string;
  media_type: 'photo' | 'video';
  file_path: string;
  thumbnail_path?: string | null;
  original_filename: string;
  /**
   * 촬영일. has_exif가 false면 카메라가 적은 날짜가 아니라 올린 시각이다 —
   * 화면은 그때 "날짜를 알 수 없는 사진"으로 묶는다.
   */
  captured_at?: string | null;
  uploaded_at: string;
  duration_sec?: number | null;
  event?: { id: string; title: string } | null;
  /** 사람이 직접 지목한 사람들만 (얼굴 인식이 없다) */
  people: Array<{
    id: string;
    name: string;
    relation?: string | null;
    thumbnail_url?: string | null;
  }>;
  place?: { id: string; name: string } | null;
  visibility: Visibility;
  owner_id?: string | null;
  has_exif: boolean;
}

export interface AlbumResponse {
  items: AlbumMediaItem[];
  /** 다음 페이지를 부를 때 그대로 되돌려 보낸다. 없으면 마지막 페이지다 */
  next_cursor?: string | null;
  /** 지금 조건에 맞는 전체 개수 (이 페이지 개수가 아니다) */
  total: number;
  /** 고를 수 있는 촬영 연도 (최신순) */
  available_years: number[];
}

/**
 * 기록 하나의 상세. 목록에 싣지 않는 것(카메라·좌표·장면 설명)이 여기 있다.
 *
 * 사진첩은 상세를 열 때 이걸 부른다 — 목록 60건에 카메라 정보까지 실으면
 * 훑어보기만 하는 사람도 쓰지 않을 값을 매번 받는다.
 */
/**
 * 사진에서 찾은 얼굴 하나. 상세 화면이 사진 위에 이 자리를 표시한다.
 *
 * 좌표는 0~1 비율이라 화면에 표시하는 크기가 원본과 달라도 그대로 쓴다.
 *
 * person_id가 없는 얼굴도 온다 — "누군지 모르는 얼굴이 여기 있다"도 보여줘야
 * 하는 정보다. 조용히 빼면 사용자는 AI가 그 얼굴을 못 봤다고 생각하고, 왜 이름이
 * 안 붙었는지 알 수 없다. reason에 이유가 담겨 온다.
 */
export interface FaceBox {
  left: number;
  top: number;
  width: number;
  height: number;
  person_id?: string | null;
  name?: string | null;
  relation?: string | null;
  /** 닮은 정도 (0~100) */
  similarity: number;
  /** 이름을 붙이지 못한 이유 */
  reason: string;
}

export interface MediaDetail {
  id: string;
  media_type: string;
  file_path: string;
  thumbnail_path?: string | null;
  original_filename: string;
  created_at: string;
  exif_date?: string | null;
  exif_lat?: number | null;
  exif_lng?: number | null;
  exif_camera?: string | null;
  detected_faces: string[];
  scene_description?: string | null;
  /** 그 설명을 누가 썼는지: ai_vision(모델이 사진을 보고 씀) | user_input */
  scene_source?: string | null;
  /** detected_faces를 누가 정했는지: ai_vision | user_input */
  faces_source?: string | null;
  /** 사진에서 찾은 얼굴의 위치와 이름. 비어 있으면 아직 찾지 않은 것이다 */
  face_boxes: FaceBox[];
  confidence: string;
  linked_events: Array<{ id: string; title: string }>;
  linked_persons: Array<{ id: string; name: string }>;
}

/** 볼 수 없는 기록은 404가 온다 (있다는 사실 자체를 알리지 않는다) */
export async function getMediaDetail(mediaId: string): Promise<MediaDetail> {
  return fetchJSON(withViewer(`${BASE_URL}/media/${mediaId}`));
}

export type AlbumSort = 'captured_desc' | 'captured_asc' | 'uploaded_desc';
export type AlbumEventStatus = 'all' | 'linked' | 'unlinked';

export interface AlbumQuery {
  cursor?: string | null;
  limit?: number;
  /** 'photo' | 'video' — 비우면 둘 다 */
  types?: string | null;
  year?: number | null;
  personId?: string | null;
  eventStatus?: AlbumEventStatus;
  sort?: AlbumSort;
  q?: string | null;
}

export interface BulkDeleteResult {
  deleted: string[];
  /** 지우지 못한 것과 그 이유 (남의 기록이 섞여 있을 때) */
  failed: Array<{ id: string; reason: string }>;
  message: string;
}

/**
 * 고른 원본들을 한 번에 지운다.
 *
 * 한 장씩 DELETE를 여러 번 부르지 않는다. 서버가 저장을 한 번으로 모으고,
 * 하나가 막혀도 나머지는 지운 뒤 무엇이 왜 막혔는지 함께 돌려준다 —
 * 요청을 흩어 보내면 그 결과를 화면이 다시 모아야 한다.
 */
export async function bulkDeleteMedia(mediaIds: string[]): Promise<BulkDeleteResult> {
  return fetchJSON(`${BASE_URL}/media/bulk-delete`, {
    method: 'POST',
    body: JSON.stringify({ media_ids: mediaIds }),
  });
}

/**
 * 사진첩 한 페이지. 원본은 부르지 않는다 — 썸네일 경로만 받아 두고 원본은
 * 상세(Lightbox)를 열 때 처음 불러온다.
 */
export async function getAlbum(query: AlbumQuery = {}): Promise<AlbumResponse> {
  const params = new URLSearchParams();
  if (query.cursor) params.set('cursor', query.cursor);
  params.set('limit', String(query.limit ?? 60));
  if (query.types) params.set('types', query.types);
  if (query.year != null) params.set('year', String(query.year));
  if (query.personId) params.set('person_id', query.personId);
  if (query.eventStatus && query.eventStatus !== 'all') params.set('event_status', query.eventStatus);
  if (query.sort) params.set('sort', query.sort);
  if (query.q) params.set('q', query.q);

  return fetchJSON(withViewer(`${BASE_URL}/media/album?${params.toString()}`));
}

/**
 * 녹음한 음성 업로드.
 * 길이와 파형은 브라우저가 계산해서 함께 보낸다 — 서버에 오디오 디코더를 두지
 * 않기 위한 분업이다. eventId를 주면 그 사건의 기록으로 바로 이어진다.
 */
export async function uploadVoice(
  blob: Blob,
  meta: {
    durationSec: number;
    waveform: number[];
    transcript?: string;
    /** 전사문이 기계가 옮긴 것이면 'ai_stt'. 사람이 적거나 고쳤으면 비워 둔다 */
    transcriptSource?: string;
    speakerId?: string;
    eventId?: string;
    filename?: string;
  },
): Promise<MediaUploadResult> {
  const formData = new FormData();
  formData.append('file', blob, meta.filename || 'voice-' + Date.now() + '.webm');
  formData.append('duration_sec', String(meta.durationSec));
  formData.append('waveform', JSON.stringify(meta.waveform));
  if (meta.transcript) formData.append('transcript', meta.transcript);
  if (meta.transcriptSource) formData.append('transcript_source', meta.transcriptSource);
  if (meta.speakerId) formData.append('speaker_id', meta.speakerId);
  if (meta.eventId) formData.append('event_id', meta.eventId);
  // 올린 사람이 소유자다 — 공개 범위를 정할 수 있는 사람
  if (meta.speakerId) formData.append('owner_id', meta.speakerId);

  const response = await fetch(`${BASE_URL}/media/upload`, {
    method: 'POST',
    headers: viewerId ? { 'X-Viewer-Id': viewerId } : undefined,
    body: formData,
  });
  if (!response.ok) throw new Error('Voice upload failed');
  return response.json();
}

/** 가족이 남긴 음성 목록. personId를 주면 그 사람이 말한 것만. */
export async function getVoiceClips(personId?: string): Promise<VoiceClip[]> {
  const query = personId
    ? '?media_type=audio&person_id=' + encodeURIComponent(personId)
    : '?media_type=audio';
  const items: MediaItem[] = await fetchJSON(withViewer(`${BASE_URL}/media${query}`));
  return items.map(toVoiceClip);
}

export async function deleteMedia(id: string): Promise<void> {
  const response = await fetch(withViewer(`${BASE_URL}/media/${id}`), {
    method: 'DELETE',
    headers: viewerId ? { 'X-Viewer-Id': viewerId } : undefined,
  });
  // 남의 기록을 지우려 했을 때 403이 온다. 화면이 그대로 넘기지 않게 던진다.
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || '삭제하지 못했습니다.');
  }
}

/**
 * 이 기록에 누가 있는지 지목한다. 보낸 목록이 최종 상태가 된다.
 *
 * 얼굴 인식이 없으므로 이 호출이 detected_faces의 유일한 출처다. 켜고 끈 결과를
 * 그대로 보내면 서버가 DEPICTS 엣지를 맞춘다 — 더하기만 있으면 잘못 지목한
 * 사람을 뗄 수 없다.
 */
/**
 * 이 사진에서 얼굴을 다시 찾는다 (사람이 눌렀을 때만).
 *
 * 화면을 여는 것만으로는 돌지 않는다 — Rekognition 호출이 사진당 여러 번이라
 * 열기만 하는 사람도 비용을 만든다. 얼굴 등록이 늘어난 뒤에 다시 눌러 본다.
 */
/**
 * 얼굴 하나가 누구인지 정한다 (상세 화면에서 상자를 눌렀을 때).
 *
 * 사진 전체 목록(setMediaPersons)과 나눠 둔 이유: 목록만으로는 어느 얼굴이
 * 누구인지가 남지 않아서, 이름을 얼굴 위에 얹을 수 없고 인식이 틀렸을 때 어느
 * 상자를 고쳐야 하는지도 알 수 없다. personId를 null로 보내면 이름을 뗀다.
 */
export async function assignMediaFace(
  mediaId: string,
  faceIndex: number,
  personId: string | null,
): Promise<{ media_id: string; face_boxes: FaceBox[]; detected_faces: string[] }> {
  return fetchJSON(`${BASE_URL}/media/${mediaId}/faces`, {
    method: 'PUT',
    body: JSON.stringify({ face_index: faceIndex, person_id: personId }),
  });
}

export async function detectMediaFaces(
  mediaId: string,
): Promise<{ media_id: string; face_boxes: FaceBox[] }> {
  return fetchJSON(`${BASE_URL}/media/${mediaId}/faces/detect`, { method: 'POST' });
}

export async function setMediaPersons(
  mediaId: string,
  personIds: string[],
): Promise<{ media_id: string; detected_faces: string[] }> {
  return fetchJSON(`${BASE_URL}/media/${mediaId}/persons`, {
    method: 'PUT',
    body: JSON.stringify({ person_ids: personIds }),
  });
}

// --- Graph ---

export interface GraphNode {
  id: string;
  node_type: string;
  name?: string;
  title?: string;
  relation?: string;
  description?: string;
  content?: string;
  date_start?: string;
  media_type?: string;
  file_path?: string;
  thumbnail_path?: string;
  original_filename?: string;
  exif_date?: string;
  /** 인물의 프로필 사진 (그래프가 점 대신 얼굴을 그리는 데 쓴다) */
  thumbnail_url?: string;
  /** confirmed · ai_inferred · user_unverified (backend/models/graph_models.py) */
  confidence?: string;
  /** 기억을 남긴 사람 */
  contributor_id?: string;
  [key: string]: unknown;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  properties?: Record<string, unknown>;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface PlaceRef {
  id: string;
  name: string;
  lat?: number | null;
  lng?: number | null;
}

export interface PersonRef {
  id: string;
  name: string;
  relation?: string | null;
  thumbnail_url?: string | null;
}

/**
 * 타임라인 · 지도 · TV가 함께 쓰는 사건 요약.
 * 좌표·참여자·썸네일·확인 상태까지 한 번에 온다 (화면이 사건마다 상세를 다시
 * 부르지 않게 하려는 것이다).
 */
export interface EventListItem {
  id: string;
  title: string;
  date_start?: string | null;
  date_end?: string | null;
  location_name?: string | null;
  participant_count: number;
  media_count: number;
  place?: PlaceRef | null;
  participants: PersonRef[];
  media_thumbs: string[];
  memory_count: number;
  voice_count: number;
  /** 기억이 쌓인 정도 (확인 상태가 아니다) */
  state: MemoryState;
  /** 나도 기억나요를 누른 사람 수 */
  echo_count: number;
}

export interface PersonData {
  id: string;
  name: string;
  relation: string;
  birth_year?: number | null;
  thumbnail_url?: string | null;
  events?: Array<{ id: string; title: string; date_start?: string }>;
  media?: Array<{ id: string; file_path: string; thumbnail_path?: string }>;
}

export async function getGraph(): Promise<GraphData> {
  return fetchJSON(`${BASE_URL}/graph`);
}

export async function getEvents(): Promise<EventListItem[]> {
  return fetchJSON(withViewer(`${BASE_URL}/graph/events`));
}

export interface EventDetail {
  id: string;
  title: string;
  description?: string;
  date_start?: string | null;
  date_end?: string | null;
  location?: { id: string; name: string } | null;
  confidence: string;
  participants: Array<{ id: string; name: string; relation: string }>;
  media: Array<{
    id: string;
    file_path: string;
    thumbnail_path?: string | null;
    media_type: string;
  }>;
  memories: Array<{ id: string; content: string; contributor_id?: string | null }>;
}

/**
 * 사건 하나의 상세. 화면이 자기 손으로 fetch하지 않고 이 함수를 쓴다 —
 * 예전에는 홈이 raw fetch로 '/api/...'를 직접 불러서, 백엔드가 다른 도메인에
 * 있는 배포(VITE_API_URL)에서는 사진 펼치기가 조용히 실패했다. 열람자도 함께
 * 나가지 않아 서버가 공개 범위를 적용할 수 없었다.
 */
export async function getEventDetail(eventId: string): Promise<EventDetail> {
  if (STATIC_MODE) {
    const response = await fetch(`/mock/events/${eventId}.json`);
    return response.json();
  }
  return fetchJSON(withViewer(`${BASE_URL}/graph/event/${eventId}`));
}

export async function getPersons(): Promise<PersonData[]> {
  return fetchJSON(`${BASE_URL}/graph/persons`);
}

export async function createPerson(data: { name: string; relation: string; birth_year?: number }): Promise<PersonData> {
  return fetchJSON(`${BASE_URL}/graph/person`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// --- Chat ---

export interface ChatSource {
  type: string;
  id: string;
  title?: string | null;
  thumbnail?: string | null;
  confidence?: number | null;
}

export interface ChatResponse {
  answer: string;
  sources: ChatSource[];
  confidence: string;
  conversation_id?: string | null;
  /** 실제 모델이 이 답변을 썼는가. false면 키가 없거나 호출이 실패한 것이다 */
  llm_used: boolean;
  /** 어떤 모델이었는지 (폴백이면 null) */
  model?: string | null;
  /** 어디로 갔는지: exaone(사내망) · friendli · bedrock */
  provider?: string | null;
}

export async function sendChat(query: string, conversationId?: string): Promise<ChatResponse> {
  return fetchJSON(`${BASE_URL}/chat`, {
    method: 'POST',
    body: JSON.stringify({
      query,
      conversation_id: conversationId,
      viewer_id: viewerId,
    }),
  });
}

/** 스트리밍 중에 화면이 쓰는 조각들 */
export interface ChatStreamHandlers {
  /** 근거·신뢰도는 모델을 부르기 전에 정해지므로 먼저 온다 */
  onMeta?: (meta: { conversation_id?: string | null; sources: ChatSource[]; confidence: string }) => void;
  /** 답변 조각. 받는 대로 이어 붙인다 */
  onDelta?: (text: string) => void;
}

/**
 * 답변을 토큰 단위로 받는다 (SSE).
 *
 * EventSource는 GET만 되고 헤더도 못 붙여서 fetch 스트림을 직접 읽는다.
 * 실패하면 예외를 던지므로 호출부가 sendChat으로 되돌릴 수 있다.
 */
export async function streamChat(
  query: string,
  conversationId: string | undefined,
  handlers: ChatStreamHandlers,
): Promise<ChatResponse> {
  const response = await fetch(`${BASE_URL}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(viewerId ? { 'X-Viewer-Id': viewerId } : {}),
    },
    body: JSON.stringify({ query, conversation_id: conversationId, viewer_id: viewerId }),
  });

  if (!response.ok || !response.body) {
    throw new Error(`스트리밍 실패: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let done: ChatResponse | null = null;

  // SSE는 빈 줄로 프레임을 구분한다. 청크가 프레임 중간에서 끊기므로
  // 완성된 프레임만 꺼내 쓰고 나머지는 버퍼에 남긴다.
  const handleFrame = (frame: string) => {
    let event = 'message';
    const dataLines: string[] = [];
    for (const line of frame.split('\n')) {
      if (line.startsWith('event: ')) event = line.slice(7).trim();
      else if (line.startsWith('data: ')) dataLines.push(line.slice(6));
    }
    if (dataLines.length === 0) return;
    const payload = JSON.parse(dataLines.join('\n'));

    if (event === 'meta') handlers.onMeta?.(payload);
    else if (event === 'delta') handlers.onDelta?.(payload.text);
    else if (event === 'done') done = payload as ChatResponse;
  };

  for (;;) {
    const { value, done: finished } = await reader.read();
    if (finished) break;
    buffer += decoder.decode(value, { stream: true });
    let split = buffer.indexOf('\n\n');
    while (split !== -1) {
      handleFrame(buffer.slice(0, split));
      buffer = buffer.slice(split + 2);
      split = buffer.indexOf('\n\n');
    }
  }
  if (buffer.trim()) handleFrame(buffer);

  if (!done) throw new Error('스트림이 done 없이 끝났습니다');
  return done;
}

// --- Interview ---

export interface InterviewStartResult {
  session_id: string;
  question: string;
  context?: { target_type?: string; target_id?: string; target_title?: string } | null;
}

/** 답변에서 뽑아 그래프에 이은 것 (기획안 02장 "답변에서 사건·인물·시점 추출") */
export interface ExtractedFromAnswer {
  /** 그래프에 있는 인물로 맞춰진 것 */
  persons: Array<{ id: string; name: string; term: string }>;
  place?: { id: string; name: string; term: string } | null;
  date?: string | null;
  /** 비어 있어서 이 답변으로 채운 사건 필드 */
  filled: string[];
  /** 답변에 나왔지만 그래프에 없어서 잇지 않은 표현 */
  unmatched: string[];
}

export interface InterviewAnswerResult {
  session_id: string;
  next_question?: string | null;
  is_complete: boolean;
  updated_nodes: string[];
  extracted?: ExtractedFromAnswer | null;
  message: string;
}

/**
 * 인터뷰 시작.
 * speakerId는 "지금 답하는 사람" — 질문이 이 사람을 향한다. 넘기지 않으면
 * 서버가 아무 참여자를 인터뷰 대상으로 골라 다른 사람의 이름으로 묻는다.
 */
export async function startInterview(
  targetType?: string,
  targetId?: string,
  speakerId?: string,
): Promise<InterviewStartResult> {
  return fetchJSON(`${BASE_URL}/interview/start`, {
    method: 'POST',
    body: JSON.stringify({
      target_type: targetType || 'auto',
      target_id: targetId,
      speaker_id: speakerId,
    }),
  });
}

/**
 * 답변 제출.
 * speakerId는 화면에서 고른 "지금 답하는 사람" — 기억의 주인이 된다.
 * audioMediaId를 넘기면 그 음성이 기억의 근거로 연결된다.
 */
export async function submitInterviewAnswer(
  sessionId: string,
  answer: string,
  speakerId?: string,
  audioMediaId?: string,
): Promise<InterviewAnswerResult> {
  return fetchJSON(`${BASE_URL}/interview/answer`, {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      answer,
      speaker_id: speakerId,
      audio_media_id: audioMediaId,
    }),
  });
}

// --- TV Journey ---

export interface TVSlide {
  type: string;
  media_id?: string | null;
  file_path?: string | null;
  caption: string;
  event_id?: string | null;
  event_title?: string | null;
  date?: string | null;
  /** 미리 만들어 둔 미세 모션 클립. 있으면 사진 대신 재생한다 (Film과 같은 자산) */
  motion_url?: string | null;
  /** 클립이 못 뜰 때 보여줄 정지 그림 */
  motion_poster?: string | null;
  /** 인물 영역을 원본으로 되돌린 클립인가 */
  subject_preserved?: boolean;
  /**
   * 이 슬라이드에 적을 AI 라벨. 서버가 정한다
   * (backend/services/film_composer.generated_label).
   * 화면이 문구를 조립하면 서버가 붙이는 것과 조용히 갈라진다.
   */
  motion_label?: string | null;
  /**
   * 가족이 더한 기억에서 온 짧은 자막 (backend/services/memory_context.py).
   * 거실 화면에 긴 문장을 띄우지 않는다 — 원문은 앱에서 읽는다.
   */
  context_caption?: string;
  context_contributor?: string | null;
  /** 그 자막의 출처. "이 사진의 장면은 아닙니다"까지 서버가 적는다 */
  context_source?: string;
  /** 맥락이 가리키는 원본. 비어 있으면 이 사진이 아니라 같은 사건의 기억이다 */
  context_media_ids?: string[];
}

export interface TVJourney {
  id: string;
  title: string;
  slides: TVSlide[];
  narration: string;
  /**
   * 이 여정에 깔리는 배경 음악. 여정 전체에 하나뿐이다 — 슬라이드마다 바꾸면
   * 9초마다 곡이 갈린다 (backend/services/film_music.pick_journey).
   *
   * 서버에 닿지 못해 로컬로 조립한 여정에는 없다. 그때는 음악 없이 재생한다 —
   * 낱말 표를 화면에 복사해 두면 두 곳이 갈라지고, 무엇보다 추모하는 자리에
   * 근거 없이 아무 소리나 얹게 된다.
   */
  music?: FilmMusic | null;
  total_duration_sec: number;
}

/**
 * 여정 만들기.
 *
 * eventIds를 주면 서버가 말을 다시 해석하지 않고 그 사건들의 사진만 쓴다.
 * TV 메뉴처럼 이미 사건을 고른 화면에서는 이쪽이 맞다 — 제목을 키워드로 다시
 * 훑으면 "입학식"을 눌렀는데 같은 사람이 찍힌 다른 해의 사진이 섞인다.
 */
export async function createTVJourney(
  query: string,
  style?: string,
  eventIds?: string[],
): Promise<TVJourney> {
  return fetchJSON(`${BASE_URL}/tv/journey`, {
    method: 'POST',
    body: JSON.stringify({
      query,
      style: style || 'timeline',
      ...(eventIds && eventIds.length > 0 ? { event_ids: eventIds } : {}),
    }),
  });
}



// --- Family Space / 공개 범위 ---

export type FamilyRole = 'owner' | 'contributor' | 'viewer' | 'invited';
export type Visibility = 'family' | 'partial' | 'private';

export interface FamilyMember {
  id: string;
  name: string;
  relation: string;
  birth_year?: number | null;
  thumbnail_url?: string | null;
  role: FamilyRole;
  joined_at?: string | null;
  private_request: boolean;
  asset_count: number;
  memory_count: number;
  /** 다른 가족의 추억에 "나도 기억나요"를 남긴 횟수 */
  echo_count: number;
}

export interface FamilyInvite {
  code: string;
  /** 서버가 앱 주소(APP_BASE_URL)를 알 때만 채워진다 */
  link: string;
  /** 항상 온다. 화면이 자기 origin에 붙여 쓴다 */
  join_path: string;
  person_id?: string | null;
  created_at: string;
  expires_at: string;
  expires_in_hours: number;
}

export interface InviteCheck {
  code: string;
  expires_at: string;
  person_id?: string | null;
  person_name?: string | null;
  space_name: string;
}

export interface FamilySpace {
  space_name: string;
  members: FamilyMember[];
  invites: FamilyInvite[];
  ownership: Array<{ id: string | null; name: string; count: number }>;
  /** 지금 보는 사람에게 몇 개가 가려지는지 */
  visibility: {
    viewer_id?: string | null;
    media_total: number;
    visible: number;
    hidden: number;
  };
}

export interface CascadePreview {
  media_id: string;
  target: string;
  scene_description?: string | null;
  derived: Array<{ label: string; detail: string }>;
}

export async function getFamilySpace(): Promise<FamilySpace> {
  return fetchJSON(withViewer(`${BASE_URL}/family`));
}

export async function updateMember(
  personId: string,
  patch: { role?: FamilyRole; private_request?: boolean },
): Promise<FamilyMember> {
  return fetchJSON(`${BASE_URL}/family/member/${personId}`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

export async function createInvite(personId?: string): Promise<FamilyInvite> {
  return fetchJSON(`${BASE_URL}/family/invite`, {
    method: 'POST',
    body: JSON.stringify({ person_id: personId }),
  });
}

/** 초대에서 실제로 열리는 주소. 서버가 앱 주소를 모르면 지금 보는 origin을 쓴다 */
export function inviteLink(invite: FamilyInvite): string {
  return invite.link || window.location.origin + (invite.join_path || '/join/' + invite.code);
}

/** 코드가 아직 쓸 수 있는지 (참여 화면이 먼저 확인한다) */
export async function checkInvite(code: string): Promise<InviteCheck> {
  return fetchJSON(`${BASE_URL}/family/invite/${encodeURIComponent(code)}`);
}

/**
 * 초대 코드로 참여한다. 코드는 한 번 쓰면 소진된다.
 *
 * 지목된 초대면 person_id 없이 코드만 보내면 되고, 일반 초대면 기존 구성원을
 * 고르거나(person_id) 이름을 적어(name) 새로 들어온다.
 */
export async function joinFamily(
  code: string,
  who: { person_id?: string; name?: string; relation?: string },
): Promise<{ space_name: string; member: FamilyMember }> {
  return fetchJSON(`${BASE_URL}/family/join`, {
    method: 'POST',
    body: JSON.stringify({ code, ...who }),
  });
}

/**
 * 기록 하나의 공개 범위. 비공개·부분공개로 바꿀 때는 소유자를 함께 남긴다 —
 * 소유자가 없으면 아무도 볼 수 없게 되기 때문이다.
 */
export async function setMediaVisibility(
  mediaId: string,
  visibility: Visibility,
  allowedIds?: string[],
  ownerId?: string | null,
): Promise<{ media_id: string; visibility: Visibility; allowed_ids: string[]; owner_id?: string | null }> {
  return fetchJSON(`${BASE_URL}/family/media/${mediaId}/visibility`, {
    method: 'PUT',
    body: JSON.stringify({
      visibility,
      allowed_ids: allowedIds,
      owner_id: ownerId ?? viewerId,
    }),
  });
}

export async function getDeleteCascade(mediaId: string): Promise<CascadePreview> {
  return fetchJSON(`${BASE_URL}/family/media/${mediaId}/cascade`);
}

// --- Memory Film ---

export interface FilmScene {
  media_id: string;
  thumb: string;
  file_path: string;
  subtitle: string;
  note: string;
  duration_sec: number;
  /** 이 장면의 근거가 되는 원본 */
  source_label: string;
  /** 적용된 AI 효과. 빈 배열이면 원본 그대로 — 화면은 이걸 감추지 않는다 */
  ai_effects: string[];
  /**
   * 사진에 걸 카메라 움직임. 서버가 정한다 (film_composer.CAMERA_MOTIONS).
   * 화면이 따로 고르면 ai_effects에 적힌 것과 어긋난다.
   */
  motion?: 'zoom-in' | 'pan-left' | 'zoom-out' | 'pan-right' | null;
  /** 미리 만들어 둔 미세 모션 클립. 있으면 사진 대신 이걸 재생한다 */
  motion_url?: string | null;
  voice_id?: string | null;
  /**
   * 가족이 더한 기억에서 온 자막 (backend/services/memory_context.py).
   * 있으면 subtitle과 같은 값이고, 없으면 빈 문자열이다.
   */
  context_caption?: string;
  /**
   * 그 자막이 누구의 기억에서 왔는지와, 사진에서 확인된 것인지.
   * 화면이 조립하지 않는다 — 확인 여부를 화면이 판단하면 서버와 갈라진다.
   * source_label 안에도 같은 문구가 들어 있다.
   */
  context_source?: string;
  context_contributor?: string | null;
  /**
   * 확대의 중심으로 쓸 지점 (0~1 비율). 맥락의 인물이 사진에서 있는 자리다
   * (MediaNode.face_boxes). 잘라내지 않는다 — transform-origin만 옮긴다.
   */
  focus?: { x: number; y: number } | null;
  /**
   * 지금은 'subject-focus'(인물 중심 확대)뿐이다. 나중에 image-to-video가 붙으면
   * 그때는 ai_effects에 "AI 생성" 라벨이 함께 온다.
   */
  visual_treatment?: string | null;
}

export interface FilmMusic {
  /** warm | nostalgic | bright | calm | solemn. 서버가 고른다 (film_music.py) */
  mood: string;
  /** 사람이 읽을 무드 이름. 화면이 조립하지 않는다 */
  label: string;
  /** 왜 이 무드인지 — 화면은 이걸 그대로 밝힌다 */
  reason: string;
  /** 코드 전환·음 간격에 곱하는 배수 (대상 세대의 장면 배수와 같은 값) */
  pace: number;
}

export interface FilmStoryboard {
  event_id: string;
  title: string;
  subtitle: string;
  narration: string;
  /**
   * 배경 음악의 무드. 음원 파일이 아니라 무드만 온다 — 소리는 화면이 만든다
   * (lib/filmMusic.ts). 화면은 앱이 만든 소리라는 사실을 함께 밝힌다.
   */
  music?: FilmMusic | null;
  scenes: FilmScene[];
  total_sec: number;
  audience: string;
  requested_sec: number;
  /** 이 사건·대상으로 채울 수 있는 최대 길이. 이보다 긴 선택지는 화면에서 잠긴다 */
  max_sec: number;
  /** 길이에 맞추려고 뺀 장면 수 */
  omitted_scenes: number;
  /**
   * 지금 미세 모션 클립을 만들고 있는 사진들.
   * 비어 있지 않으면 화면이 getMotionStatus로 되묻고 준비된 것을 바꿔 끼운다.
   */
  motion_pending?: string[];
}

export interface MotionReady {
  file: string;
  poster?: string | null;
  /** AI 라벨. 서버가 정한다 — 화면이 문구를 조립하면 서버와 갈라진다 */
  label: string;
}

export interface MotionStatus {
  /** media_id → 준비된 클립. 준비된 것만 담긴다 */
  ready: Record<string, MotionReady>;
  pending: string[];
  /** 만들다 실패한 사진과 이유 — 화면은 이걸 보고 되묻기를 멈춘다 */
  failed: Record<string, string>;
  /** 런타임 생성이 켜져 있는가 (키·ffmpeg·상한을 모두 통과했는가) */
  enabled: boolean;
  attempts_left: number;
  /** 앞으로 생긴 사건만 만드는가 (기존 사건은 기준선에 있어 대상이 아니다) */
  new_events_only?: boolean;
}

export interface Anniversary {
  date: string;
  label: string;
  event_id: string;
  days_left: number;
  reason: string;
}

export async function composeFilm(
  eventId: string,
  lengthSec: number,
  audience: string,
): Promise<FilmStoryboard> {
  return fetchJSON(`${BASE_URL}/film`, {
    method: 'POST',
    body: JSON.stringify({ event_id: eventId, length_sec: lengthSec, audience }),
  });
}

export async function getAnniversaries(): Promise<Anniversary[]> {
  return fetchJSON(`${BASE_URL}/film/anniversaries`);
}

/**
 * 맡긴 미세 모션 클립이 준비됐는지 묻는다.
 *
 * composeFilm을 다시 부르지 않는다 — 그쪽은 내레이션을 위해 모델을 호출해서,
 * 되묻는 값이 응답 시간과 돈으로 돌아온다. 이 호출은 파일 목록만 읽는다.
 */
export async function getMotionStatus(mediaIds: string[]): Promise<MotionStatus> {
  const query = mediaIds.length
    ? '?media_ids=' + encodeURIComponent(mediaIds.join(','))
    : '';
  return fetchJSON(`${BASE_URL}/film/motion${query}`);
}



// --- 내보내기 ---

export interface ExportItem {
  id: string;
  label: string;
  detail: string;
  /** 디스크에서 잰 실제 크기. 만들면서 정해지는 항목은 null */
  size_bytes: number | null;
  count: number;
  required: boolean;
}

export interface ExportManifest {
  viewer_id?: string | null;
  items: ExportItem[];
  /** 열람 범위 밖이라 아카이브에 들어가지 않는 기록 수 */
  hidden_media: number;
  note: string;
}

export interface ExportResult {
  file_name: string;
  size_bytes: number;
  built_at: string;
  included: string[];
  download_url: string;
}

export async function getExportManifest(): Promise<ExportManifest> {
  return fetchJSON(withViewer(`${BASE_URL}/export/manifest`));
}

export async function buildArchive(items: string[]): Promise<ExportResult> {
  const query = withViewer(`${BASE_URL}/export?items=` + encodeURIComponent(items.join(',')));
  return fetchJSON(query, { method: 'POST' });
}

/** 다운로드 링크 (서버가 준 상대 경로를 절대 URL로) */
export function exportDownloadUrl(result: ExportResult): string {
  return MEDIA_BASE + result.download_url;
}

// --- Trust Harness ---

export interface TrustMetric {
  key: string;
  label: string;
  /** 0~100. 잴 것이 없으면 null (0점과 구분한다) */
  score: number | null;
  description: string;
  method: string;
}

export interface TrustQuestionRow {
  id: string;
  query: string;
  expected: string;
  actual: string;
  confidence: string;
  verdict: 'pass' | 'partial' | 'fail';
  note: string;
  unsupported_persons: string[];
}

export interface TrustReport {
  ran: boolean;
  message?: string;
  question_count?: number;
  ran_at?: string;
  graph?: { nodes: number; edges: number; file: string };
  llm_enabled?: boolean;
  metrics?: TrustMetric[];
  questions?: TrustQuestionRow[];
  counts?: {
    total: number;
    graded: number;
    no_record: number;
    pass: number;
    partial: number;
    fail: number;
  };
  details?: {
    relations: { expected: number; found: number; missing_count: number };
    media_integrity: { scenes_checked: number; violation_count: number };
    asset_integrity: {
      media_total: number;
      missing_file_count: number;
      orphan_edge_count: number;
    };
  };
}

export async function getTrustReport(): Promise<TrustReport> {
  return fetchJSON(`${BASE_URL}/trust/report`);
}

// --- 추억 · 기억 이어가기 ---

/**
 * 추억 하나에 기억이 얼마나 쌓였는가.
 *
 * 예전의 확인 상태(confirmed/supported/inferred/conflicted)를 대신한다. 추억은
 * 한 사람이 만들면 그 순간 게시되므로 "확인 대기"가 없다. varied는 문제가
 * 아니라 보존해야 할 사실이다 — 가족이 조금 다르게 기억한다는 뜻이다.
 */
export type MemoryState = 'alone' | 'shared' | 'varied';

export interface MemoryMediaRef {
  id: string;
  media_type: string;
  file_path: string;
  thumbnail_path?: string | null;
  duration_sec?: number | null;
  transcript?: string | null;
  waveform?: number[];
  speaker_id?: string | null;
  /** 인터뷰 녹음이면 그 목소리가 답한 질문 (음성만 채워진다) */
  question?: string | null;
}

/**
 * 기억 한 줄에서 뽑아낸 작은 맥락 (backend/services/memory_context.py)
 *
 * 원문을 대신하지 않는다. 화면은 원문을 먼저 보여주고 그 아래에 "이 기억에서
 * 발견된 맥락"으로 붙인다 — 사람이 말한 그대로가 자산이고 이건 파생값이다.
 *
 * 문구(caption · source_note)는 서버가 만든다. 같은 문구가 상세 화면 · Film ·
 * TV 세 곳에 나오는데 각자 조립하면 조용히 갈라진다.
 */
export interface MemoryContextInfo {
  speaker?: PersonRef | null;
  /** 이 기억이 누구에 대한 말인가 (그래프에 있는 사람만) */
  subjects: PersonRef[];
  scene?: string | null;
  action?: string | null;
  highlight?: string | null;
  /** explicit = 원문에 그대로 있었다, inferred = 미루어 짚었다 */
  confidence: string;
  /** 가족 공간에 없어서 잇지 못한 호칭 */
  unmatched: string[];
  /** 이 맥락이 가리키는 원본 (근거가 없으면 비어 있다 — 억지로 잇지 않는다) */
  media_ids: string[];
  /** attached = 함께 올린 기록, scene = 사진 설명에서 확인, person = 인물만 확인 */
  media_basis?: string | null;
  /** 사진에서 확인된 장면인가. 아니면 화면은 기억의 출처만 밝힌다 */
  shows_action: boolean;
  caption: string;
  source_note: string;
  visual_treatment?: string | null;
  used_in_film: boolean;
  used_in_tv: boolean;
}

/** 기억 한 줄 (최초 작성자의 것이든 가족이 더한 것이든 같은 모양) */
export interface MemoryEntry {
  id: string;
  /** 사람이 말하거나 적은 원문 */
  content: string;
  /** AI가 읽기 좋게 다듬은 문장. 원문은 content에 그대로 남아 있다 */
  polished?: string | null;
  /** author = 최초 작성자의 기억, contribution = 가족이 더한 기억 */
  kind: string;
  /** 조금 다르게 기억한다고 밝힌 기억 */
  differs: boolean;
  source_type?: string | null;
  created_at?: string | null;
  contributor?: PersonRef | null;
  media: MemoryMediaRef[];
  /** 이 문장에서 발견된 맥락 (없을 수 있다). 원문 아래에 붙는다 */
  context?: MemoryContextInfo | null;
}

export interface MemoryFeedItem {
  event_id: string;
  title: string;
  date_start?: string | null;
  place?: PlaceOption | null;
  author?: PersonRef | null;
  participants: Array<{ id: string; name: string; relation: string }>;
  thumbs: string[];
  media_count: number;
  author_memory?: MemoryEntry | null;
  contributions: MemoryEntry[];
  state: MemoryState;
  varied: boolean;
  echo_count: number;
  echoed_by: PersonRef[];
  /** 내가 이미 "나도 기억나요"를 눌렀는가 */
  i_echoed: boolean;
  /** 내가 이미 기억을 더했는가 */
  i_added: boolean;
  /** 내가 만든 추억인가 */
  mine: boolean;
  created_at?: string | null;
}

export interface MemoryDetail {
  id: string;
  title: string;
  description?: string;
  date_start?: string | null;
  date_end?: string | null;
  place?: PlaceOption | null;
  created_at?: string | null;
  author?: PersonRef | null;
  participants: Array<{
    id: string;
    name: string;
    relation: string;
    thumbnail_url?: string | null;
  }>;
  media: MemoryMediaRef[];
  author_memory?: MemoryEntry | null;
  contributions: MemoryEntry[];
  state: MemoryState;
  varied: boolean;
  echo_count: number;
  echoed_by: PersonRef[];
  i_echoed: boolean;
  i_added: boolean;
  /** AI가 여러 사람의 기억을 엮어 쓴 이야기 */
  together_story?: string | null;
  together_story_at?: string | null;
  /** 이야기를 쓴 뒤 기억이 더 쌓였는가 */
  together_story_stale: boolean;
}

export interface PlaceOption {
  id: string;
  name: string;
  distance_km?: number;
}

/** AI가 사진·영상에서 읽어낸 추억 초안 (기획안 05) */
export interface MemoryDraft {
  media: Array<{
    id: string;
    media_type: string;
    file_path: string;
    thumbnail_path?: string | null;
    original_filename: string;
    exif_date?: string | null;
    exif_lat?: number | null;
    exif_lng?: number | null;
  }>;
  title: string;
  date_start?: string | null;
  date_end?: string | null;
  place?: PlaceOption | null;
  /**
   * 그래프에 맞는 장소가 없어 좌표에서 짐작한 지명. id가 없다 — 장소 칸에 미리
   * 채워 두고, 저장할 때 이 이름으로 새 장소가 만들어진다. 시·도까지만 짚은
   * 넓은 짐작은 서버가 걸러서 보내지 않는다.
   */
  place_guess?: { name: string; precision: string } | null;
  lat?: number | null;
  lng?: number | null;
  person_ids: string[];
  /** "사진 속 이분이 엄마인가요?" — 확정하지 않고 되묻는 후보 */
  person_candidates: Array<{
    id: string;
    name: string;
    relation: string;
    thumbnail_url?: string | null;
    score: number;
    confidence: 'likely' | 'maybe';
    reason: string;
  }>;
  description: string;
  /** 무엇을 근거로 이 초안을 썼는가 */
  evidence: Array<{ label: string; detail: string }>;
  /** 기존 추억과 관련 있어 보이는 것 (자동으로 붙이지 않는다) */
  related: Array<{
    event_id: string;
    title: string;
    date_start?: string | null;
    place?: string | null;
    score: number;
    reason: string;
  }>;
  /** 초안을 모델이 썼는가. false면 읽어낸 사실로만 만든 것이다 */
  ai_used: boolean;
}

export interface MemoryDraftGroups {
  /** 묶음마다 초안 하나. 여러 사건의 사진을 한꺼번에 올리면 여러 개가 온다 */
  groups: MemoryDraft[];
  total: number;
  /** 갈랐는가 (화면이 "2개 묶음으로 갈랐어요"를 말할 수 있게) */
  grouped: boolean;
}

/**
 * 서버가 준 초안을 화면이 읽을 수 있는 모양으로 맞춘다.
 *
 * 배열이 빠져 있으면 빈 배열로 채운다. 화면은 evidence·related·media를 바로
 * `.length`로 읽는데, 하나라도 없으면 묶음을 그리는 중에 예외가 나면서 모으기
 * 화면 전체가 사라진다 — 사용자에게는 "사진을 올렸는데 아무것도 안 뜬다"로
 * 보인다. 없는 것은 없다고 그리는 것이 화면이 죽는 것보다 낫다.
 *
 * 저장소에서 되살린 초안(lib/collectDraft.ts)도 같은 길을 지난다 — 오래된
 * 배포가 써 둔 모양이 올 수 있어 서버 응답과 사정이 같다.
 */
export function normalizeDraft(raw: Partial<MemoryDraft> | null | undefined): MemoryDraft {
  const list = <T,>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);
  return {
    ...(raw as MemoryDraft),
    title: raw?.title ?? '',
    description: raw?.description ?? '',
    media: list<MemoryDraft['media'][number]>(raw?.media),
    person_ids: list<string>(raw?.person_ids),
    person_candidates: list<MemoryDraft['person_candidates'][number]>(raw?.person_candidates),
    evidence: list<MemoryDraft['evidence'][number]>(raw?.evidence),
    related: list<MemoryDraft['related'][number]>(raw?.related),
    ai_used: !!raw?.ai_used,
  };
}

/**
 * 올린 기록으로 초안을 만든다.
 *
 * 기본은 날짜·장소로 갈라 묶음마다 초안 하나다 — 어떤 사진이 같은 사건인지
 * 고르는 일을 사용자에게 맡기지 않는다. AI가 잘못 갈랐으면 merge로 다시 부른다.
 *
 * 묶음이 없는 예전 응답(초안 하나를 그대로 준다)도 받아 준다. 프론트와 백엔드가
 * 서로 다른 시점에 배포되면 이 응답 모양이 어긋나고, 그때 화면이 죽는 대신
 * 묶음 하나로 그린다.
 */
export async function draftMemory(
  mediaIds: string[],
  merge = false,
): Promise<MemoryDraftGroups> {
  const raw = await fetchJSON<Partial<MemoryDraftGroups> & Partial<MemoryDraft>>(
    `${BASE_URL}/memories/draft`,
    {
      method: 'POST',
      body: JSON.stringify({ media_ids: mediaIds, merge }),
    },
  );

  const groups = Array.isArray(raw?.groups)
    ? raw.groups
    : // 예전 서버는 묶음 없이 초안 하나를 돌려준다 (media가 그 표시다)
      Array.isArray(raw?.media)
      ? [raw as MemoryDraft]
      : [];

  return {
    groups: groups.map(normalizeDraft),
    total: typeof raw?.total === 'number' ? raw.total : groups.length,
    grouped: !!raw?.grouped,
  };
}

export interface MemoryCreateInput {
  title: string;
  description?: string;
  date_start?: string | null;
  place_id?: string | null;
  place_name?: string | null;
  lat?: number | null;
  lng?: number | null;
  person_ids?: string[];
  media_ids?: string[];
}

/** 추억 만들기. 저장하는 즉시 가족 공간에 게시된다 (승인 절차가 없다) */
export async function createMemory(
  input: MemoryCreateInput,
): Promise<{ event_id: string; memory: MemoryDetail; message: string }> {
  return fetchJSON(`${BASE_URL}/memories`, {
    method: 'POST',
    body: JSON.stringify({ ...input, author_id: viewerId }),
  });
}

export async function getMemoryFeed(): Promise<{
  items: MemoryFeedItem[];
  total: number;
  /** 내가 아직 아무 말도 얹지 않은 남의 추억 수 (안내일 뿐 과제가 아니다) */
  open_count: number;
}> {
  return fetchJSON(withViewer(`${BASE_URL}/memories/feed`));
}

export async function getMemoryDetail(eventId: string): Promise<MemoryDetail> {
  return fetchJSON(withViewer(`${BASE_URL}/memories/${eventId}`));
}

/** 나도 기억나요 (다시 부르면 취소된다) */
export async function echoMemory(
  eventId: string,
): Promise<{
  event_id: string;
  echoed: boolean;
  echo_count: number;
  echoed_by: PersonRef[];
  message: string;
}> {
  const url = viewerId
    ? `${BASE_URL}/memories/${eventId}/echo?person_id=${encodeURIComponent(viewerId)}`
    : `${BASE_URL}/memories/${eventId}/echo`;
  return fetchJSON(url, { method: 'POST' });
}

export interface ContributionInput {
  content: string;
  media_ids?: string[];
  audio_media_id?: string;
  /** 조금 다르게 기억한다고 밝히는 경우 */
  differs?: boolean;
  /** 'ai_stt'면 서버가 읽기 좋게 정리하고 원문도 그대로 남긴다 */
  source_type?: string;
}

/** 내 기억 더하기. 원본을 고치지 않고 나란히 쌓인다 */
export async function addMemoryContribution(
  eventId: string,
  input: ContributionInput,
): Promise<{
  event_id: string;
  memory_id: string;
  polished?: string | null;
  polished_by_ai: boolean;
  /** 이 문장에서 발견된 맥락. 없으면 null (모델을 못 불렀거나 뽑을 것이 없었다) */
  context?: MemoryContextInfo | null;
  message: string;
}> {
  return fetchJSON(`${BASE_URL}/memories/${eventId}/memory`, {
    method: 'POST',
    body: JSON.stringify({ ...input, person_id: viewerId }),
  });
}

/**
 * 사건에서 내가 남긴 기억 하나 지우기.
 *
 * 문장과 함께, 그 기억으로 남긴 목소리가 지워진다(deleted_voices). 목소리는 문장과
 * 한 몸이라 따로 남기면 지운 것이 아니다 — 전사문이 녹음에 함께 있다. 사진·영상은
 * 추억에 남고(kept_media), 원본을 지우는 자리는 사진첩이다.
 *
 * AI가 쓴 "함께 기억한 이야기"가 이 기억을 담고 있었다면 서버가 함께 지우고
 * story_cleared로 알려 준다 — 화면이 그 사실을 말하지 않으면 사용자는 이야기가 왜
 * 사라졌는지 모른다.
 *
 * 남의 기억이면 403이 온다. 화면은 단추를 미리 감추지 않고 서버가 밝힌 이유를
 * 그대로 보여준다 (readDetail).
 */
export async function deleteMemoryEntry(
  eventId: string,
  memoryId: string,
): Promise<{
  event_id: string;
  memory_id: string;
  /** 문장과 함께 지워진 녹음 (목소리로 남긴 기억) */
  deleted_voices: string[];
  /** 지운 문장이 근거로 매달고 있던 사진·영상. 지워지지 않고 추억에 남는다 */
  kept_media: string[];
  /** "함께 기억한 이야기"를 함께 지웠는가 */
  story_cleared: boolean;
  message: string;
}> {
  return fetchJSON(`${BASE_URL}/memories/${eventId}/memory/${memoryId}`, {
    method: 'DELETE',
  });
}

/**
 * 추억 하나 지우기.
 *
 * 사진첩에서 사진을 다 지워도 추억은 남는다 — 원본을 지울 때 끊기는 것은 연결
 * 뿐이다. 자료도 기억도 없는 추억을 치우는 길이 이것이다.
 *
 * 함께 지워지는 것은 이 추억에 붙은 기억 문장(deleted_memories)이고, 사진·영상·
 * 목소리는 사진첩에 남는다(kept_media). 화면은 지우기 전에 그것을 밝히고, 지운
 * 뒤에는 서버가 준 message를 그대로 적는다.
 *
 * 남이 만든 추억이면 403이 온다 (readDetail로 그 이유를 읽는다).
 */
export async function deleteMemoryEvent(eventId: string): Promise<{
  event_id: string;
  title: string;
  /** 함께 지운 기억 문장. 사건이 없어지면 걸릴 자리가 없다 */
  deleted_memories: string[];
  /** 지워지지 않고 사진첩에 남는 원본 */
  kept_media: string[];
  echo_count: number;
  message: string;
}> {
  return fetchJSON(`${BASE_URL}/memories/${eventId}`, { method: 'DELETE' });
}

/** 기존 추억에 사진·영상 더하기 (AI가 자동으로 붙이지 않는다) */
export async function addMediaToMemory(
  eventId: string,
  mediaIds: string[],
): Promise<{ event_id: string; attached: string[]; message: string }> {
  return fetchJSON(`${BASE_URL}/memories/${eventId}/media`, {
    method: 'POST',
    body: JSON.stringify({ media_ids: mediaIds }),
  });
}

/** 함께 기억한 이야기 만들기 (AI는 누가 맞는지 판단하지 않는다) */
export async function composeTogetherStory(
  eventId: string,
): Promise<{ event_id: string; story: string; at: string; basis: number; ai_used: boolean }> {
  return fetchJSON(withViewer(`${BASE_URL}/memories/${eventId}/story`), { method: 'POST' });
}
