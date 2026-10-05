"""品詞分解の行を、文法の中身から組み立てる（『能は歌詠み』文法プリントの書式）。

    {"品詞分解": {"番号": "①", "品詞": "動詞", "行": "ラ", "活用": "四段",
                 "活用形": "連用", "敬語": {"種類": "謙譲語", "から": "作者", "へ": "大臣"}}}

は次の 2 行になる（解答部分は赤字）::

    ① ( 動　詞)([ ラ行] 四段 活用)（連用 形）
    敬語の種類：〔謙譲 語〕〔作者〕から〔大臣〕への敬意

教材データのどの区画の行にも書ける。
"""

from __future__ import annotations

from . import markup

CONJUGATING = {"動詞", "形容詞", "形容動詞"}


class BunkaiError(ValueError):
    pass


def _ans(text) -> str:
    return "{%s}" % markup.escape(str(text))


def render(entry: dict) -> list[str]:
    """品詞分解 1 項目を、記法つきの行（1〜2 行）にする。"""
    number = entry.get("番号", "")
    kind = entry.get("品詞", "")
    if not kind:
        raise BunkaiError(f"{number or '(番号なし)'}: 「品詞」がありません")
    prefix = "（補・本）" if entry.get("補助") else ""

    def need(*fields):
        for f in fields:
            if f not in entry:
                raise BunkaiError(f"{number}: {kind}には「{f}」が要ります")

    if kind in CONJUGATING:
        need("行", "活用", "活用形")
        line = (f"{number} {prefix}( {_ans(kind[:-1])}　詞)"
                f"(\\[ {_ans(entry['行'])}行\\] {_ans(entry['活用'])} 活用)"
                f"（{_ans(entry['活用形'])} 形）")
    elif kind == "助動詞":
        need("意味", "語", "活用形")
        line = (f"{number}{prefix}（{_ans(entry['意味'])}）の({_ans('助動')} 詞)"
                f"「{_ans(entry['語'])}」の（{_ans(entry['活用形'])}形）")
    elif kind.endswith("助詞"):
        need("語")
        line = f"{number} ( {_ans(kind[:-1])} 詞) の「{markup.escape(str(entry['語']))}」"
        if "用法" in entry:
            line += f"（{_ans(entry['用法'])}）"
        elif "意味" in entry:
            line += f"意味：（{_ans(entry['意味'])}）"
        if "訳" in entry:
            line += f"【訳】「{_ans(entry['訳'])}」"
    else:
        raise BunkaiError(f"{number}: 「{kind}」は扱えません"
                          "（動詞・形容詞・形容動詞・助動詞・〜助詞）")

    lines = [line]
    keigo = entry.get("敬語")
    if keigo:
        for f in ("種類", "から", "へ"):
            if f not in keigo:
                raise BunkaiError(f"{number}: 敬語には「{f}」が要ります")
        kind_k = str(keigo["種類"]).removesuffix("語")
        lines.append(f"敬語の種類：〔{_ans(kind_k)} 語〕"
                     f"〔{_ans(keigo['から'])}〕から〔{_ans(keigo['へ'])}〕への敬意")
    return lines
