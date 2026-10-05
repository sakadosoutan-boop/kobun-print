"""教材データ（教材形式）を、区画ごとの行の並びにほどく。

    {"sheets": {
       "表": {"ヘッダ": "…", "題名": "…", "本文": ["…", "…"], "現代語訳": [...]},
       "裏": {"本文": [...], "設問": [{"問": "☆１ …", "答": ["…"]}], "図解": [...]}}}

区画名は template/<種類>/regions.json に載っているもの。行は記法つきの文字列で、
``{"品詞分解": {...}}`` と書けば品詞分解の行に開く。

「設問」は問と答の組の並びで書ける。テンプレートにある設問の数より多ければ、
あふれた分は最後の設問の答の後ろに続け、少なければ使わない設問を枠ごと取り除く。
"""

from __future__ import annotations

import re

from . import bunkai


class MaterialError(ValueError):
    pass


def lines_of(value) -> list[str]:
    """区画に渡された値を、行の文字列の並びにする。"""
    if value is None:
        return []
    items = [value] if isinstance(value, (str, dict)) else list(value)
    out: list[str] = []
    for item in items:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and "品詞分解" in item:
            out.extend(bunkai.render(item["品詞分解"]))
        else:
            raise MaterialError(f"行として読めない値です: {item!r}")
    return out


_Q_RE = re.compile(r"^設問(\d+)・問$")


def expand_questions(sheet_data: dict, regions: dict) -> dict:
    """「設問」の並びを、テンプレートの 設問N・問 / 設問N・答 に割り振る。"""
    if "設問" not in sheet_data:
        return sheet_data
    numbers = sorted(int(m.group(1)) for name in regions if (m := _Q_RE.match(name)))
    if not numbers:
        raise MaterialError("このプリントには設問の区画がありません")
    items = sheet_data["設問"]
    out = {k: v for k, v in sheet_data.items() if k != "設問"}
    for k, n in enumerate(numbers):
        if k < len(items):
            item = items[k]
            out[f"設問{n}・問"] = item.get("問", "")
            out[f"設問{n}・答"] = lines_of(item.get("答", []))
        else:
            out[f"設問{n}・問"] = None      # 使わない設問（枠ごと取り除く）
            out[f"設問{n}・答"] = []
    for item in items[len(numbers):]:      # あふれた設問は最後の答の後ろへ
        last = f"設問{numbers[-1]}・答"
        out[last] = out[last] + [item.get("問", "")] + lines_of(item.get("答", []))
    return out
