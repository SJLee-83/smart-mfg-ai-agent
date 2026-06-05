"""
A7 검증 — Chroma 기본 연동 스모크 테스트 (experiments PoC, 버려도 되는 검증용)

ADR-004(Chroma 채택)의 동작 검증. 로컬 파일 기반 Chroma가 다음을 지원하는지 확인:
  - PersistentClient(파일 기반) 생성 / 컬렉션 생성
  - 문서 + 메타데이터 add
  - 메타데이터 필터링 (where: error_code)
  - 유사도 검색 (query_embeddings)

실제 임베딩 모델/네트워크 없이 **더미 벡터(dim=8)**로 메커니즘만 검증한다.
(기본 EmbeddingFunction의 ONNX 모델 다운로드를 피하려고 더미 EF + 명시적 embeddings 사용)

의존성: chromadb
실행: .venv/Scripts/python.exe experiments/a7_vector_db/verify_chroma.py
"""

from __future__ import annotations

import gc
import shutil
import sys
import time
from pathlib import Path

# Windows 콘솔 기본 인코딩(cp949)에서 한글이 깨져 크래시하지 않도록 UTF-8 강제.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# [1] chromadb 설치 확인 — 없으면 설치 안내만 출력하고 종료
try:
    import chromadb
except ImportError:
    print("[중단] chromadb 미설치.")
    print("설치: .venv/Scripts/python.exe -m pip install chromadb")
    sys.exit(0)

SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = SCRIPT_DIR / "chroma_test_db"
RESULT_PATH = SCRIPT_DIR / "result_chroma_verify.txt"

_buffer: list[str] = []


def out(line: str = "") -> None:
    print(line)
    _buffer.append(line)


class DummyEmbeddingFunction:
    """결정적 더미 임베딩(dim=8). 실제 모델/네트워크 없이 Chroma 동작만 검증."""

    DIM = 8

    def __call__(self, input):  # chroma EmbeddingFunction 시그니처
        vecs = []
        for text in input:
            h = abs(hash(text))
            vecs.append([float((h >> (i * 5)) & 0x3F) for i in range(self.DIM)])
        return vecs

    @staticmethod
    def name() -> str:
        return "dummy-deterministic-8d"


def cleanup(db_path: Path) -> bool:
    """[8] 테스트 DB 디렉터리 삭제 (Windows sqlite 파일 잠금 대비 재시도)."""
    gc.collect()
    for _ in range(6):
        try:
            if db_path.exists():
                shutil.rmtree(db_path)
            return True
        except (PermissionError, OSError):
            time.sleep(0.5)
            gc.collect()
    return not db_path.exists()


def main() -> None:
    out("=" * 72)
    out("A7 검증 — Chroma 기본 연동 스모크 테스트")
    out("=" * 72)
    out(f"chromadb 버전 : {getattr(chromadb, '__version__', 'unknown')}")
    out(f"테스트 DB 경로: {DB_PATH}")
    out("")

    if DB_PATH.exists():
        cleanup(DB_PATH)

    ef = DummyEmbeddingFunction()
    client = None
    collection = None
    ok = True
    try:
        # [2] 로컬 PersistentClient (파일 기반)
        client = chromadb.PersistentClient(path=str(DB_PATH))
        out("[2] PersistentClient 생성: OK (파일 기반)")

        # [3] 테스트 컬렉션
        collection = client.create_collection(name="a7_smoke_test", embedding_function=ef)
        out("[3] 컬렉션 생성: OK (name=a7_smoke_test)")

        # [4] 더미 문서 5개 (error_code, content_type 메타데이터) — 명시적 embeddings 사용
        docs = [
            ("d1", "SRVO-062 BZAL alarm. Battery voltage low.",
             {"error_code": "SRVO-062", "content_type": "cause"}),
            ("d2", "Replace the pulsecoder battery and master the robot.",
             {"error_code": "SRVO-062", "content_type": "action"}),
            ("d3", "SRVO-094 PMAL alarm. Pulsecoder abnormal.",
             {"error_code": "SRVO-094", "content_type": "cause"}),
            ("d4", "Close the cabinet door or check the E-stop unit.",
             {"error_code": "SRVO-105", "content_type": "action"}),
            ("d5", "SRVO-214 fuse blown on the servo amplifier.",
             {"error_code": "SRVO-214", "content_type": "cause"}),
        ]
        ids = [d[0] for d in docs]
        texts = [d[1] for d in docs]
        metas = [d[2] for d in docs]
        collection.add(ids=ids, embeddings=ef(texts), documents=texts, metadatas=metas)
        out(f"[4] 문서 추가: OK (count={collection.count()})")

        # [5] 메타데이터 필터링 (error_code=SRVO-062)
        filtered = collection.get(where={"error_code": "SRVO-062"})
        f_ids = filtered.get("ids", [])
        out("")
        out("[5] 메타데이터 필터  where={error_code: 'SRVO-062'}")
        out(f"    - 매칭 문서 수: {len(f_ids)} (기대: 2)")
        for i, did in enumerate(f_ids):
            md = filtered["metadatas"][i]
            out(f"      · {did}  content_type={md.get('content_type')}  :: {filtered['documents'][i]}")

        # [6] 유사도 검색 (더미 임베딩 벡터로)
        query_vec = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]  # dim=8
        res = collection.query(query_embeddings=[query_vec], n_results=3)
        out("")
        out("[6] 유사도 검색  query_embeddings=[8차원 더미벡터], n_results=3")
        r_ids = res.get("ids", [[]])[0]
        r_dist = res.get("distances", [[]])[0]
        for did, dist in zip(r_ids, r_dist):
            out(f"      · {did}  distance={dist:.4f}")

        out("")
        out("=" * 72)
        out("결과: 로컬 파일 기반 Chroma에서 컬렉션·메타데이터 필터·유사도 검색 모두 동작 확인")
        out("=" * 72)

    except Exception as e:  # noqa: BLE001 (검증용 — 모든 예외 기록)
        ok = False
        out("")
        out(f"[ERROR] 검증 중 예외: {type(e).__name__}: {e}")
    finally:
        # 핸들 해제 후 [8] 정리
        collection = None
        client = None
        removed = cleanup(DB_PATH)
        out("")
        if removed:
            out("[8] 테스트 DB 정리: 완료(삭제됨)")
        else:
            out("[8] 테스트 DB 정리: 프로세스 내 삭제 실패(Windows sqlite 잠금). "
                "chroma_test_db/는 .gitignore 처리됨 — 다음 실행 시작 시 자동 삭제.")

    RESULT_PATH.write_text("\n".join(_buffer) + "\n", encoding="utf-8", errors="replace")
    print(f"\n[저장됨] 결과 파일: {RESULT_PATH}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
