"""分量チェック — 新しい教材が原本の紙面に収まりそうかを、描画せずに見積もる。

Word のページ割りは実フォント（HG丸ゴシック・UD デジタル教科書体など）が無いと
再現できず、LibreOffice で数えたページ数は当てにならない（原本そのものでさえ
裏面の冒頭が 1 ページ目に食い込む）。そこで、縦書き 1 行に入る字数を
「段の長さ ÷ 文字の大きさ」で求め、教材の各行が何行分を占めるかを数えて、
原本と比べる。原本以下なら、紙面からはみ出すことはまずない。
"""

from __future__ import annotations

import math
from xml.etree import ElementTree as ET

from . import markup
from . import slots as slotlib
from .docxpkg import w

TWIP_MM = 25.4 / 1440
PT_MM = 25.4 / 72


def _section_of_paragraphs(root: ET.Element) -> dict[int, ET.Element]:
    """段落 → その段落が属するセクションの sectPr。"""
    body = root.find(w("body"))
    owner: dict[int, ET.Element] = {}
    pending: list[ET.Element] = []
    for child in body:
        if child.tag == w("p"):
            pending.append(child)
            ppr = child.find(w("pPr"))
            sect = ppr.find(w("sectPr")) if ppr is not None else None
            if sect is not None:
                for p in pending:
                    owner[id(p)] = sect
                pending = []
        elif child.tag == w("sectPr"):
            for p in pending:
                owner[id(p)] = child
    return owner


def _line_length_mm(sect: ET.Element) -> float:
    """縦書き 1 行の長さ（mm）。段組なら段の長さ。"""
    size, margin, cols = sect.find(w("pgSz")), sect.find(w("pgMar")), sect.find(w("cols"))
    height = int(size.get(w("h"))) - int(margin.get(w("top"))) - int(margin.get(w("bottom")))
    if sect.find(w("textDirection")) is None:     # 横書きなら幅で数える
        height = int(size.get(w("w"))) - int(margin.get(w("left"))) - int(margin.get(w("right")))
    num = int(cols.get(w("num"), "1")) if cols is not None else 1
    space = int(cols.get(w("space"), "0")) if cols is not None else 0
    return (height - space * (num - 1)) / num * TWIP_MM


def capacities(root: ET.Element, default_sz: int = 21) -> dict[str, int]:
    """スロット ID → そのスロットの段落の 1 行に入る字数。"""
    owner = _section_of_paragraphs(root)
    caps = {}
    for sid, (para, run) in slotlib.locate(root).items():
        sect = owner.get(id(para))
        if sect is None:            # 図形の中の文字などは数えない
            continue
        rpr = run.find(w("rPr"))
        sz = rpr.find(w("sz")) if rpr is not None else None
        points = int(sz.get(w("val")) if sz is not None else default_sz) / 2
        caps[sid] = max(1, int(_line_length_mm(sect) // (points * PT_MM)))
    return caps


def columns(text: str, cap: int) -> int:
    """1 段落が占める行数（縦書きの列数）。空行も 1 行と数える。"""
    return max(1, math.ceil(len(markup.plain(text)) / cap))
