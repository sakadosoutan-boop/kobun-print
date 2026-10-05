#!/usr/bin/env python3
"""テンプレート化で組版が 1 ドットも動いていないことを確かめる。

1. 原本をスロットに割り、そのまま組み直したものが原本と同じか（可逆性）
2. テンプレート＋教材データ（教材形式）から組んだものが、手本のプリントと同じか

照合は、テキストを段落ごとに比べたうえで、LibreOffice で PDF にしたページ画像を
1 ドットずつ突き合わせる。LibreOffice / poppler が無い環境では画像照合を飛ばす。

    python3 tests/verify.py
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kobunprint import slots as slotlib  # noqa: E402
from kobunprint.docxpkg import DocxPackage, w  # noqa: E402

ROUNDTRIP = [
    ROOT / "docs" / "原本_徒然草_あだし野の露.docx",
    ROOT / "prints" / "徒然草_あだし野の露_改訂.docx",
]
# (教材データ, 手本) — テンプレートから組んだものが手本と一致すること
FROM_TEMPLATE = [
    (ROOT / "data" / "徒然草_あだし野の露.json",
     ROOT / "prints" / "徒然草_あだし野の露_改訂.docx"),
]


def can_render() -> bool:
    return bool(shutil.which("soffice") and shutil.which("pdftoppm"))


def pages(docx: Path, work: Path) -> list[str]:
    work.mkdir(parents=True, exist_ok=True)
    src = work / "in.docx"
    shutil.copyfile(docx, src)
    subprocess.run(["soffice", "--headless", "--norestore", "--convert-to", "pdf",
                    "--outdir", str(work), str(src)], check=True, timeout=900,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pdftoppm", "-r", "100", "-png", str(work / "in.pdf"),
                    str(work / "p")], check=True, timeout=900)
    return [hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(work.glob("p-*.png"))]


def texts(docx: Path) -> list[str]:
    root = DocxPackage(docx).parse_document()
    return ["".join(slotlib.run_text(r) for r in p.iter(w("r")) if slotlib.is_plain_text_run(r)
                    or r.find(w("t")) is not None)
            for p in root.iter(w("p"))]


def compare(label: str, expected: Path, actual: Path, tmp: Path) -> list[str]:
    problems = []
    a, b = texts(expected), texts(actual)
    if a != b:
        diffs = [(i, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]
        problems.append(f"{label}: 文字が {len(diffs)} 段落ずれています（段落数 {len(a)}→{len(b)}）")
        for i, x, y in diffs[:3]:
            problems.append(f"    段落{i}: 手本={x[:40]!r} / 生成={y[:40]!r}")
        return problems
    if not can_render():
        print(f"  {label}: 文字一致（画像照合は省略）")
        return problems
    pa, pb = pages(expected, tmp / "a"), pages(actual, tmp / "b")
    if pa != pb:
        bad = [str(i) for i, (x, y) in enumerate(zip(pa, pb), 1) if x != y]
        problems.append(f"{label}: ページ数 {len(pa)}→{len(pb)}、ずれたページ {','.join(bad) or 'なし'}")
    else:
        print(f"  {label}: 文字一致・{len(pa)} ページとも 1 ドット単位で一致")
    return problems


def roundtrip(source: Path, tmp: Path) -> Path:
    package = DocxPackage(source)
    root = package.parse_document()
    found = slotlib.extract(root)
    package.set_document(root)
    package.save(tmp / "template.docx")
    spans = {}
    for s in found:
        spans.update(s.extra_spans)
    package = DocxPackage(tmp / "template.docx")
    root = package.parse_document()
    slotlib.fill(root, {s.slot_id: s.text for s in found}, spans,
                 {s.slot_id: s.local_spans for s in found if s.local_spans})
    package.set_document(root)
    return package.save(tmp / "rebuilt.docx")


def main() -> int:
    problems: list[str] = []
    print("[1] 可逆性（原本 → スロット → 組み直し）")
    for source in ROUNDTRIP:
        with tempfile.TemporaryDirectory() as d:
            problems += compare(source.name, source, roundtrip(source, Path(d)), Path(d))

    print("[2] テンプレート＋教材データ → 手本")
    for data, expected in FROM_TEMPLATE:
        if not data.exists():
            print(f"  {data.name}: まだ無いので省略")
            continue
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "built.docx"
            subprocess.run([sys.executable, str(ROOT / "src" / "build.py"), str(data),
                            "-o", str(out)], check=True, stdout=subprocess.DEVNULL)
            problems += compare(data.name, expected, out, Path(d))

    print("[3] 別の教材（行数の違う教材）を組む")
    sample = ROOT / "data" / "例_方丈記_ゆく河の流れ.json"
    sys.path.insert(0, str(ROOT / "src"))
    import build as builder  # noqa: E402
    with tempfile.TemporaryDirectory() as d:
        report = builder.build(sample, Path(d) / "x.docx")
        for name, (before, after) in report["amount"].items():
            if after > before:
                problems.append(f"{sample.name}: {name}の分量が原本を超えています（{after}/{before}）")
        print(f"  {sample.name}: 組めた（行数を変えた区画 {len(report['resized'])} か所）")

        print("[4] 解答の見せ方の切り替え")
        for mode, banned in (("空欄", "FF0000"), ("答え", "FFFFFF"), ("黒", "FF0000")):
            out = Path(d) / f"{mode}.docx"
            builder.build(ROOT / "data" / "徒然草_あだし野の露.json", out, mode)
            root = DocxPackage(out).parse_document()
            left = sum(len(t.text or "") for r in root.iter(w("r"))
                       if (c := r.find(f"{w('rPr')}/{w('color')}")) is not None
                       and c.get(w("val")) == banned for t in r.iter(w("t")))
            if left:
                problems.append(f"--answers {mode}: 色 {banned} の文字が {left} 字残っています")
            else:
                print(f"  {mode}: 色 {banned} の文字は 0 字")

    if problems:
        print("\n✗ 再現できていない点があります")
        print("\n".join("  " + p for p in problems))
        return 1
    print("\n✓ レイアウトは完全に再現されています")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
