/**
 * API 클라이언트 - Backend 통신
 */

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
      '/api/gaps': '/mock/gaps.json',
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
  speaker_id?: string | null;
  speaker_name?: string | null;
  event_id?: string | null;
  event_title?: string | null;
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
  recorded_at?: string | null;
  waveform: number[];
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
    recorded_at: (item.created_at || '').slice(0, 10),
    waveform: item.waveform || [],
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
  detected_faces: string[];
  scene_description?: string | null;
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
export async function setMediaPersons(
  mediaId: string,
  personIds: string[],
): Promise<{ media_id: string; detected_faces: string[] }> {
  return fetchJSON(`${BASE_URL}/media/${mediaId}/persons`, {
    method: 'PUT',
    body: JSON.stringify({ person_ids: personIds }),
  });
}

export async function supplementMedia(data: {
  media_id: string;
  date?: string;
  event_id?: string;
  description?: string;
}): Promise<{ message: string; linked_event_id?: string }> {
  return fetchJSON(`${BASE_URL}/media/supplement`, {
    method: 'POST',
    body: JSON.stringify(data),
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
  state: VerificationState;
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

export async function startInterview(targetType?: string, targetId?: string): Promise<InterviewStartResult> {
  return fetchJSON(`${BASE_URL}/interview/start`, {
    method: 'POST',
    body: JSON.stringify({ target_type: targetType || 'auto', target_id: targetId }),
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

// --- Gaps ---

export interface GapItem {
  id: string;
  event_id?: string | null;
  event_title?: string | null;
  gap_type: string;
  description: string;
  suggested_question: string;
  target_person?: string | null;
  priority: number;
}

export interface GapsResponse {
  gaps: GapItem[];
  total: number;
}

export async function getGaps(): Promise<GapsResponse> {
  return fetchJSON(`${BASE_URL}/gaps`);
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
}

export interface TVJourney {
  id: string;
  title: string;
  slides: TVSlide[];
  narration: string;
  total_duration_sec: number;
}

export async function createTVJourney(query: string, style?: string): Promise<TVJourney> {
  return fetchJSON(`${BASE_URL}/tv/journey`, {
    method: 'POST',
    body: JSON.stringify({ query, style: style || 'timeline' }),
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
  verified_count: number;
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
  voice_id?: string | null;
}

export interface FilmStoryboard {
  event_id: string;
  title: string;
  subtitle: string;
  narration: string;
  scenes: FilmScene[];
  total_sec: number;
  audience: string;
  requested_sec: number;
  /** 길이에 맞추려고 뺀 장면 수 */
  omitted_scenes: number;
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

// --- Verification (가족 확인) ---

export type VerificationState = 'confirmed' | 'supported' | 'inferred' | 'conflicted';

export interface VerifierRef {
  id: string;
  name: string;
}

export interface InboxMemory {
  id: string;
  content: string;
  contributor_id?: string | null;
  contributor_name?: string | null;
}

export interface PlaceOption {
  id: string;
  name: string;
}

/** 무엇이 무엇으로 바뀌었는가 */
export interface FieldChange {
  field: string;
  before?: string | null;
  after?: string | null;
}

export interface CorrectionRecord {
  person_id: string;
  person_name: string;
  at?: string | null;
  changes: FieldChange[];
}

export interface InboxItem {
  event_id: string;
  event_title: string;
  date_start?: string | null;
  /** 수정 폼을 채울 지금 값 */
  description?: string;
  place?: PlaceOption | null;
  state: VerificationState;
  confirmed_by: VerifierRef[];
  corrected_by: VerifierRef[];
  disputed_by: VerifierRef[];
  unknown_by: VerifierRef[];
  participants: Array<{ id: string; name: string; relation: string }>;
  memories: InboxMemory[];
  /** 누가 언제 무엇을 고쳤는가 (출처 보존) */
  corrections: CorrectionRecord[];
}

export interface VerifyResult {
  event_id: string;
  verification: {
    state: VerificationState;
    confirmed_by: VerifierRef[];
    corrected_by: VerifierRef[];
    disputed_by: VerifierRef[];
    unknown_by: VerifierRef[];
  };
  created_memory_id?: string | null;
  changes: FieldChange[];
  message: string;
}

export async function getVerificationInbox(): Promise<{
  items: InboxItem[];
  total: number;
  /** 장소는 새로 적지 않고 그래프에 있는 것을 고른다 */
  places: PlaceOption[];
}> {
  return fetchJSON(`${BASE_URL}/graph/verify`);
}

/** 확인 화면에서 고칠 수 있는 값 (서버가 이 넷만 받는다) */
export interface EventCorrections {
  title?: string;
  date_start?: string | null;
  description?: string;
  location_id?: string | null;
}

export async function verifyEvent(
  eventId: string,
  personId: string,
  action: 'confirm' | 'correct' | 'unknown' | 'dispute',
  note?: string,
  corrections?: EventCorrections,
): Promise<VerifyResult> {
  return fetchJSON(`${BASE_URL}/graph/event/${eventId}/verify`, {
    method: 'POST',
    body: JSON.stringify({ person_id: personId, action, note, corrections }),
  });
}
