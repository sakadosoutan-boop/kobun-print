"""区画（本文・現代語訳・設問の答…）の行数を、教材に合わせて増減する。

区画は「同じ書式の段落が縦に並んだもの」。原本の行数と教材の行数が同じなら、
原本の段落をそのまま使う（＝完全再現）。違うときは、区画の段落を一度取り除き、
区画でいちばん多く使われている段落書式を見本にして必要な行数だけ作り直す。
字下げは段落書式ではなく、行頭の全角スペースで表すことになる。

項目のあいだに 1 行ずつ空行をはさむ区画（文学史の一覧など）は、その間隔も保つ。
図形の錨や改セクションを抱えた段落は、動かすとレイアウトが崩れるので増減しない。
"""

from __future__ import annotations

import copy
from collections import Counter
from xml.etree import ElementTree as ET

from . import slots as slotlib
from .docxpkg import w


class RegionError(ValueError):
    pass


def _parent_map(root: ET.Element) -> dict[int, ET.Element]:
    return {id(child): parent for parent in root.iter() for child in parent}


def _is_blank(para: ET.Element) -> bool:
    return (para.tag == w("p") and not slotlib.has_layout(para)
            and not any(slotlib.marker_of(r) for r in para.findall(w("r")))
            and not "".join(t.text or "" for t in para.iter(w("t"))).strip())


def _ppr_signature(para: ET.Element) -> str:
    ppr = para.find(w("pPr"))
    return ET.tostring(ppr, encoding="unicode") if ppr is not None else ""


def resize(root: ET.Element, name: str, slot_ids: list[str], count: int) -> list[str]:
    """区画を count 行にして、流し込み先のスロット ID を返す。"""
    if count == len(slot_ids):
        return list(slot_ids)
    located = slotlib.locate(root)
    paras = [located[s][0] for s in slot_ids]
    if not paras:
        raise RegionError(f"「{name}」には行がありません")
    for sid, para in zip(slot_ids, paras):
        markers = [r for r in para.findall(w("r")) if slotlib.marker_of(r)]
        if slotlib.has_layout(para) or len(markers) != 1:
            raise RegionError(
                f"「{name}」は図形と組になっているので行数を変えられません"
                f"（{len(slot_ids)} 行ちょうどで書いてください）")

    parents = _parent_map(root)
    parent = parents[id(paras[0])]
    if any(parents[id(p)] is not parent for p in paras):
        raise RegionError(f"「{name}」の行が離れた場所にあるので行数を変えられません")
    children = list(parent)
    index = [children.index(p) for p in paras]

    # 1 行おきに空行をはさむ区画か
    spaced = len(paras) > 1 and all(
        b - a == 2 and _is_blank(children[a + 1]) for a, b in zip(index, index[1:]))
    spacer = copy.deepcopy(children[index[0] + 1]) if spaced else None

    tally = Counter(_ppr_signature(p) for p in paras)
    best = max(tally, key=lambda s: (tally[s], -[_ppr_signature(p) for p in paras].index(s)))
    prototype = next(p for p in paras if _ppr_signature(p) == best)

    at = index[0]
    for para in paras:
        parent.remove(para)
    if spaced:
        for blank in [children[a + 1] for a in index[:-1]]:
            parent.remove(blank)

    new_ids = []
    offset = 0
    for k in range(count):
        if spaced and k:
            parent.insert(at + offset, copy.deepcopy(spacer))
            offset += 1
        clone = copy.deepcopy(prototype)
        new_id = f"{name}#{k + 1}"
        for run in clone.findall(w("r")):
            if slotlib.marker_of(run):
                run.find(w("t")).text = f"{slotlib.SLOT_OPEN}{new_id}{slotlib.SLOT_CLOSE}"
        parent.insert(at + offset, clone)
        offset += 1
        new_ids.append(new_id)
    return new_ids


def delete(root: ET.Element, slot_ids: list[str]) -> None:
    """区画の段落を、抱えている図形（設問の枠など）ごと取り除く。"""
    located = slotlib.locate(root)
    parents = _parent_map(root)
    for sid in slot_ids:
        para = located[sid][0]
        ppr = para.find(w("pPr"))
        if ppr is not None and ppr.find(w("sectPr")) is not None:
            raise RegionError("改セクションを抱えた段落は消せません")
        parents[id(para)].remove(para)
