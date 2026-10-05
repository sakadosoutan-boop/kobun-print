#!/usr/bin/env python3
"""教材データの表記チェック（二つのプリントを突き合わせて見つかった揺れを拾う）。

    python3 tools/check.py data/例_方丈記_ゆく河の流れ.json

  1. 本文の傍線番号と、現代語訳の空欄番号が対応しているか
  2. 解答の括弧に半角 ( ) と全角（ ）が混ざっていないか
  3. 丸数字に、装飾用の別字（➀〜➉ など）が紛れていないか
  4. 題名がヘッダの作品名と食い違っていないか（前の教材の残り物を拾う）

問題があれば終了コード 1 を返す。ただし、どれも「確かめてほしい」程度の
指摘で、直すかどうかは先生の判断。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kobunprint import markup, material  # noqa: E402

CIRCLED = set(markup.CIRCLED)
DINGBAT = re.compile(r"[❶-➓]")        # ❶〜➓ のうち、➀〜➉ ➊〜➓ など
CIRCLED_RE = re.compile("[%s]" % "".join(markup.CIRCLED))


def sheets_of(payload: dict) -> dict[str, dict[str, list[str]]]:
    """教材形式を {プリント: {区画: [行の素の文字列]}} にする。"""
    out = {}
    for name, sheet in payload.get("sheets", {}).items():
        regions: dict[str, list[str]] = {}
        for key, value in sheet.items():
            if key.startswith("_"):
                continue
            if key == "設問":
                for k, item in enumerate(value, 1):
                    regions[f"設問{k}・問"] = material.lines_of(item.get("問", ""))
                    regions[f"設問{k}・答"] = material.lines_of(item.get("答", []))
            else:
                regions[key] = material.lines_of(value)
        out[name] = regions
    return out


def check(payload: dict) -> list[str]:
    notes: list[str] = []
    for name, regions in sheets_of(payload).items():
        # 1. 傍線番号と現代語訳の番号
        body = regions.get("本文", [])
        marks = [p.text for line in body for p in markup.parse(line)[0]
                 if p.span == "sup" and p.text in CIRCLED]
        if marks and regions.get("現代語訳"):
            yaku = set(CIRCLED_RE.findall("".join(markup.plain(l) for l in regions["現代語訳"])))
            missing = [m for m in marks if m not in yaku]
            extra = sorted(yaku - set(marks), key=markup.CIRCLED.index)
            if missing:
                notes.append(f"{name}: 本文の傍線 {''.join(missing)} が現代語訳にありません")
            if extra:
                notes.append(f"{name}: 現代語訳の {''.join(extra)} に当たる傍線が本文にありません")
        if marks:
            expected = markup.CIRCLED[:len(marks)]
            if marks != expected:
                notes.append(f"{name}: 本文の傍線番号が連番になっていません（{''.join(marks)}）")

        for region, lines in regions.items():
            for i, line in enumerate(lines, 1):
                text = markup.plain(line)
                # 2. 括弧の全角・半角
                if re.search(r"[（(][^（()）]*[)）]", text) and (
                        re.search(r"（[^（()）]*\)", text) or re.search(r"\([^（()）]*）", text)
                        or ("(" in text and "（" in text and region in ("現代語訳", "答"))):
                    notes.append(f"{name}・{region} {i}行目: 括弧に全角と半角が混ざっています"
                                 f"「{text.strip()[:30]}」")
                # 3. 装飾用の丸数字
                if DINGBAT.search(text):
                    ch = DINGBAT.search(text).group()
                    notes.append(f"{name}・{region} {i}行目: 「{ch}」は装飾用の別字です"
                                 "（①〜⑳ の丸数字にそろえると検索や番号照合が効きます）")

        # 4. 題名とヘッダ
        header = markup.plain("".join(regions.get("ヘッダ", [])))
        title = markup.plain("".join(regions.get("題名", []))).strip()
        if header and title and title not in header:
            notes.append(f"{name}: 題名「{title}」がヘッダ「{header.strip()[:40]}」にありません"
                         "（前の教材の残りではありませんか）")
    return notes


def main(argv: list[str] | None = None) -> int:
    paths = [Path(p) for p in (argv if argv is not None else sys.argv[1:])]
    if not paths:
        print(__doc__)
        return 2
    status = 0
    for path in paths:
        notes = check(json.loads(path.read_text(encoding="utf-8")))
        print(f"■ {path.name}: {'指摘なし' if not notes else f'{len(notes)} 件'}")
        for note in notes:
            print("  ・" + note)
        status |= bool(notes)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
