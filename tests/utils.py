import textwrap
from pathlib import Path


def write(tmpdir: Path, rel: str, content: str) -> Path:
    p = tmpdir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p
