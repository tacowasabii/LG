"""컨테이너 시작 준비를 한 프로세스에서 한다

전에는 시작 스크립트가 파이썬을 두 번 따로 띄웠다 (시드, 프로필). 두 스크립트가
모두 backend를 import하고, 거기에 langchain·boto3·psycopg가 딸려 온다. 같은
스택을 두 번 읽는 셈이고, uvicorn이 또 한 번 읽으니 부팅 전에 세 번이었다.
화면과 서비스가 늘면서 그 시간이 헬스체크 창을 넘겨 배포가 실패했다.

여기서 두 작업을 한 인터프리터 안에서 돌린다. 두 번째 스크립트가 import할 때는
이미 sys.modules에 들어 있어 그 비용이 사라진다.

프로필은 이미 만들어져 있으면 건너뛴다. 매 부팅마다 같은 크롭을 다시 만들 이유가
없다. 볼륨이 새로 붙어 크롭만 사라진 경우에는 파일이 없으므로 그때 다시 만든다 —
원래 그 스크립트를 부팅에 둔 이유가 그것이고, 그 성질은 그대로 남는다.

두 스크립트 자체는 손대지 않았다. 여기서 `__main__`으로 실행하므로 손으로 돌릴
때와 같은 경로를 지난다.

    python scripts/boot.py
"""

import runpy
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

SCRIPTS_DIR = ROOT_DIR / "scripts"


def _run(script: str, argv: list[str]) -> None:
    """스크립트를 이 프로세스 안에서 __main__으로 돌린다

    SystemExit은 스크립트가 반환값으로 쓰는 것이라 여기서 받아 넘긴다. 0이 아니면
    다시 올려 시작 스크립트가 멈추게 한다 (예전 set -e와 같은 동작).
    """
    sys.argv = [script] + argv
    try:
        runpy.run_path(str(SCRIPTS_DIR / script), run_name="__main__")
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 0
        if code != 0:
            raise


def _profiles_ready() -> bool:
    """모든 인물의 프로필 크롭이 서빙 위치에 있는지

    graph_manager를 이미 import한 뒤에 부르므로 추가 비용이 없다.
    """
    from backend.config import MEDIA_DIR
    from backend.services.graph_manager import graph_manager

    persons = graph_manager.get_nodes_by_type("person")
    if not persons:
        return False

    missing = [p["id"] for p in persons if not (MEDIA_DIR / f"profile_{p['id']}.jpg").exists()]
    if missing:
        print(f"[boot] 프로필이 없는 인물 {len(missing)}명: {', '.join(missing[:5])}")
        return False
    return True


def main() -> int:
    _run("seed_from_metadata.py", ["--if-empty"])

    if _profiles_ready():
        print("[boot] 프로필이 이미 있습니다. 생성을 건너뜁니다.")
    else:
        _run("generate_profiles.py", [])

    return 0


if __name__ == "__main__":
    sys.exit(main())
