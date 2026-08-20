"""가족 아카이브 내보내기 (기획안 02장 EXPANSION · LEGACY)

    "플랫폼에 종속되지 않도록 원본·그래프·이야기를 가족 아카이브 파일로 내보낸다"

지어낸 용량이나 가짜 진행률을 쓰지 않는다. 파일 크기는 디스크에서 재고, zip은
실제로 만든다. 안에 들어가는 것도 이 서비스 없이 열 수 있는 형식만 쓴다.

    originals/      원본 사진·영상·음성 (보정 없이 그대로)
    graph.json      인물·사건·장소·기억과 그 연결 (표준 JSON)
    memories.md     기억 문장을 사람이 읽을 수 있게
    chronicle.html  가족 연대기 — 브라우저만 있으면 열린다
    README.txt      무엇이 들어 있고 어떻게 열면 되는지

공개 범위를 지킨다. 내보내는 사람이 볼 수 없는 기록은 아카이브에도 들어가지
않는다 (기획안 08장). PDF는 만들지 않는다 — 의존성을 늘리는 대신 HTML로 낸다.
"""

from __future__ import annotations

import html
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.config import EXPORT_DIR, GRAPH_FILE, MEDIA_DIR
from backend.models.graph_models import MediaType, NodeType
from backend.services import visibility
from backend.services.graph_manager import graph_manager

# 아카이브에 담을 수 있는 항목
ITEM_ORIGINALS = "originals"
ITEM_GRAPH = "graph"
ITEM_VOICES = "voices"
ITEM_CHRONICLE = "chronicle"

# 원본과 그래프는 아카이브의 뼈대다. 빼면 남는 게 이야기 조각뿐이다.
REQUIRED_ITEMS = {ITEM_ORIGINALS, ITEM_GRAPH}


def _local_path(file_path: str) -> Optional[Path]:
    """/media-files/... 경로를 디스크 경로로"""
    if not file_path:
        return None
    candidate = MEDIA_DIR / Path(file_path).name
    return candidate if candidate.exists() else None


def _size_of(paths: list[Path]) -> int:
    return sum(path.stat().st_size for path in paths)


def _visible_media(viewer_id: Optional[str]) -> list[dict]:
    return visibility.filter_media(graph_manager.get_media_nodes(), viewer_id)


def manifest(viewer_id: Optional[str] = None) -> dict:
    """무엇을 얼마나 내보낼 수 있는지 (크기는 디스크에서 잰다)"""
    media = _visible_media(viewer_id)
    photos_videos = [m for m in media if m.get("media_type") != MediaType.AUDIO]
    audios = [m for m in media if m.get("media_type") == MediaType.AUDIO]

    original_paths = [p for m in photos_videos if (p := _local_path(m.get("file_path", "")))]
    audio_paths = [p for m in audios if (p := _local_path(m.get("file_path", "")))]

    memories = graph_manager.get_memories()
    events = graph_manager.get_events()
    transcribed = sum(1 for m in audios if m.get("transcript"))

    hidden = len(graph_manager.get_media_nodes()) - len(media)

    items = [
        {
            "id": ITEM_ORIGINALS,
            "label": "원본 사진 · 영상",
            "detail": f"사진·영상 {len(original_paths)}개 · 보정 없는 원본",
            "size_bytes": _size_of(original_paths),
            "count": len(original_paths),
            "required": True,
        },
        {
            "id": ITEM_GRAPH,
            "label": "Memory Graph",
            "detail": (
                f"노드 {len(graph_manager.get_all_nodes())}개 · "
                f"엣지 {len(graph_manager.get_all_edges())}개 · JSON"
            ),
            "size_bytes": GRAPH_FILE.stat().st_size if GRAPH_FILE.exists() else 0,
            "count": 1,
            "required": True,
        },
        {
            "id": ITEM_VOICES,
            "label": "목소리와 전사문",
            "detail": (
                f"음성 {len(audio_paths)}개 · 글로 옮긴 것 {transcribed}개"
                if audio_paths
                else "아직 남은 목소리가 없습니다"
            ),
            "size_bytes": _size_of(audio_paths),
            "count": len(audio_paths),
            "required": False,
        },
        {
            "id": ITEM_CHRONICLE,
            "label": "가족 연대기 (HTML)",
            "detail": f"사건 {len(events)}개 · 기억 {len(memories)}개 · 브라우저로 열립니다",
            # 만들면서 정해진다. 지어낸 숫자를 적지 않는다.
            "size_bytes": None,
            "count": 1,
            "required": False,
        },
    ]

    return {
        "viewer_id": viewer_id,
        "items": items,
        "hidden_media": hidden,
        "note": (
            "열람 범위 밖의 기록은 아카이브에 들어가지 않습니다."
            if hidden
            else "지금 보이는 모든 기록이 아카이브에 들어갑니다."
        ),
    }


def build(viewer_id: Optional[str] = None, items: Optional[list[str]] = None) -> dict:
    """실제로 zip을 만든다"""
    chosen = set(items or [ITEM_ORIGINALS, ITEM_GRAPH, ITEM_VOICES, ITEM_CHRONICLE])
    chosen |= REQUIRED_ITEMS

    media = _visible_media(viewer_id)
    audios = [m for m in media if m.get("media_type") == MediaType.AUDIO]
    others = [m for m in media if m.get("media_type") != MediaType.AUDIO]

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    file_name = f"homestory-archive-{stamp}.zip"
    out_path = EXPORT_DIR / file_name

    included: list[str] = []

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if ITEM_ORIGINALS in chosen:
            for node in others:
                path = _local_path(node.get("file_path", ""))
                if path:
                    archive.write(path, "originals/" + path.name)
            included.append(ITEM_ORIGINALS)

        if ITEM_VOICES in chosen and audios:
            for node in audios:
                path = _local_path(node.get("file_path", ""))
                if path:
                    archive.write(path, "voices/" + path.name)
            archive.writestr("voices/transcripts.md", _transcripts_markdown(audios))
            included.append(ITEM_VOICES)

        if ITEM_GRAPH in chosen and GRAPH_FILE.exists():
            archive.write(GRAPH_FILE, "graph.json")
            included.append(ITEM_GRAPH)

        # 기억 문장은 언제나 넣는다. 이 서비스가 남기는 것 중 가장 오래 남을 것이다.
        archive.writestr("memories.md", _memories_markdown())

        if ITEM_CHRONICLE in chosen:
            archive.writestr("chronicle.html", _chronicle_html(viewer_id))
            included.append(ITEM_CHRONICLE)

        archive.writestr("README.txt", _readme(included, viewer_id))

    return {
        "file_name": file_name,
        "size_bytes": out_path.stat().st_size,
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "included": included,
        "download_url": "/api/export/download/" + file_name,
    }


def resolve_download(file_name: str) -> Optional[Path]:
    """다운로드 경로 확인. 이름을 그대로 붙이면 상위 경로로 빠져나갈 수 있다."""
    if "/" in file_name or "\\" in file_name or ".." in file_name:
        return None
    path = EXPORT_DIR / file_name
    if not path.exists() or path.suffix != ".zip":
        return None
    return path


# --- 사람이 읽는 파일들 -------------------------------------------------------


def _event_order() -> list[dict]:
    return sorted(graph_manager.get_events(), key=lambda e: e.get("date_start") or "")


def _speaker_name(memory: dict) -> str:
    person = graph_manager.get_node(memory.get("contributor_id") or "")
    return person.get("name", "가족") if person else "가족"


def _memories_markdown() -> str:
    lines = ["# 가족의 기억", "", "가족이 직접 남긴 문장을 그대로 옮겼습니다. 요약하지 않았습니다.", ""]

    for event in _event_order():
        connected = graph_manager.get_connected_nodes(event["id"])
        memories = [n for n in connected if n.get("node_type") == NodeType.MEMORY]
        if not memories:
            continue

        lines.append(f"## {event.get('title', '')}")
        lines.append(f"- 날짜: {event.get('date_start') or '미상'}")
        place = graph_manager.get_node(event.get("location_id") or "")
        if place:
            lines.append(f"- 장소: {place.get('name', '')}")
        lines.append("")

        for memory in memories:
            lines.append(f"**{_speaker_name(memory)}**")
            lines.append("")
            lines.append("> " + (memory.get("content") or "").replace("\n", "\n> "))
            lines.append("")

    return "\n".join(lines)


def _transcripts_markdown(audios: list[dict]) -> str:
    lines = ["# 목소리 전사문", "", "음성 파일과 같은 이름으로 짝지어 두었습니다.", ""]

    for node in audios:
        speaker = graph_manager.get_node(node.get("speaker_id") or "")
        name = speaker.get("name") if speaker else "가족"
        file_name = Path(node.get("file_path", "")).name
        lines.append(f"## {file_name}")
        lines.append(f"- 말한 사람: {name}")
        if node.get("duration_sec"):
            lines.append(f"- 길이: {round(node['duration_sec'])}초")
        lines.append("")
        lines.append(node.get("transcript") or "_아직 글로 옮기지 않았습니다._")
        lines.append("")

    return "\n".join(lines)


def _chronicle_html(viewer_id: Optional[str]) -> str:
    """브라우저만 있으면 열리는 연대기

    사진은 아카이브 안의 originals/ 를 상대 경로로 가리킨다. zip을 풀면 그대로 보인다.
    """
    visible_ids = {node["id"] for node in _visible_media(viewer_id)}
    parts: list[str] = []

    for event in _event_order():
        connected = graph_manager.get_connected_nodes(event["id"])
        media = [
            n
            for n in connected
            if n.get("node_type") == NodeType.MEDIA
            and n["id"] in visible_ids
            and n.get("media_type") == MediaType.PHOTO
        ]
        memories = [n for n in connected if n.get("node_type") == NodeType.MEMORY]
        persons = [n for n in connected if n.get("node_type") == NodeType.PERSON]
        place = graph_manager.get_node(event.get("location_id") or "")

        meta = " · ".join(
            filter(
                None,
                [
                    event.get("date_start") or "날짜 미상",
                    place.get("name") if place else None,
                    ", ".join(p.get("name", "") for p in persons) or None,
                ],
            )
        )

        images = "".join(
            f'<img src="originals/{html.escape(Path(m.get("file_path", "")).name)}" alt="">'
            for m in media
        )
        quotes = "".join(
            f"<blockquote><b>{html.escape(_speaker_name(m))}</b>"
            f"<p>{html.escape(m.get('content') or '')}</p></blockquote>"
            for m in memories
        )

        parts.append(
            f"<section><h2>{html.escape(event.get('title', ''))}</h2>"
            f"<p class=meta>{html.escape(meta)}</p>"
            f"<div class=photos>{images}</div>{quotes}</section>"
        )

    style = """
      body { max-width: 760px; margin: 0 auto; padding: 64px 24px;
             font-family: 'Pretendard', system-ui, sans-serif;
             background: #FAFAF7; color: #1F1D1A; line-height: 1.7; }
      h1 { font-size: 32px; letter-spacing: -0.02em; margin-bottom: 8px; }
      h2 { font-size: 21px; margin: 0 0 6px; }
      section { padding: 40px 0; border-bottom: 1px solid #E5E3DC; }
      .meta { color: #6E6A60; font-size: 14px; margin: 0 0 20px; }
      .photos { display: flex; flex-wrap: wrap; gap: 8px; }
      .photos img { width: 172px; height: 128px; object-fit: cover; border-radius: 6px; }
      blockquote { margin: 20px 0 0; padding: 16px 20px; background: #F4E3E8; border-radius: 8px; }
      blockquote b { color: #A61E4D; font-size: 13px; }
      blockquote p { margin: 6px 0 0; }
      footer { color: #9C988C; font-size: 13px; padding-top: 32px; }
    """

    return (
        "<!doctype html><html lang=ko><head><meta charset=utf-8>"
        "<title>가족 연대기 · LG HomeStory</title>"
        f"<style>{style}</style></head><body>"
        "<h1>가족 연대기</h1>"
        "<p class=meta>가족이 남긴 기록을 시간 순으로 모았습니다. "
        "사진은 같은 폴더의 originals/ 에 들어 있습니다.</p>"
        + "".join(parts)
        + "<footer>LG HomeStory · Family Memory Graph</footer></body></html>"
    )


def _readme(included: list[str], viewer_id: Optional[str]) -> str:
    who = viewer_id or "지정되지 않음"
    lines = [
        "LG HomeStory — 가족 아카이브",
        "",
        f"내보낸 시각: {datetime.now().isoformat(timespec='seconds')}",
        f"내보낸 사람: {who}",
        "",
        "들어 있는 것",
        "  originals/       원본 사진·영상 (보정 없이 그대로)",
        "  graph.json       인물·사건·장소·기억과 그 연결 (표준 JSON)",
        "  memories.md      가족이 남긴 문장",
    ]
    if ITEM_VOICES in included:
        lines.append("  voices/          음성 원본과 전사문")
    if ITEM_CHRONICLE in included:
        lines.append("  chronicle.html   브라우저로 여는 연대기")

    lines += [
        "",
        "이 아카이브는 LG HomeStory 없이도 열립니다.",
        "사진은 파일 탐색기로, graph.json은 아무 텍스트 편집기로,",
        "chronicle.html은 브라우저로 열면 됩니다.",
        "",
        "열람 범위 밖의 기록은 들어 있지 않습니다.",
        "다른 가족이 비공개로 둔 기록은 그 사람이 직접 내보내야 합니다.",
    ]
    return "\n".join(lines)
