"""教材データの文字列で使う短縮記法。

    "花園の左大臣の家に、初めて[①|参り][②|たり][③|ける]侍"
    "①（{ 立ち消えないで }）（いるように）"

================  ======================================================
``[①|参り]``      傍線番号（上付き）＋傍線を引く語。番号を ``#`` にすると
                  出現順に ①②③… を自動で振る
``{語}``          答え（赤字）
``{{語}}``        隠し答え（白字。印刷すると空欄に見える）
``_語_``          傍線のみ
``^語^``          上付きのみ
``<<名前|語>>``   書式表（template/…/spans.json）で定義した書式
``\\x``           直後の 1 文字をそのまま出す（``\\[`` など）
================  ======================================================

改行は ``\\n``（Word の強制改行）、タブは ``\\t``。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CIRCLED = (
    [chr(0x2460 + i) for i in range(20)]      # ①〜⑳
    + [chr(0x3251 + i) for i in range(15)]    # ㉑〜㉟
    + [chr(0x32B1 + i) for i in range(15)]    # ㊱〜㊿
)


def circled(n: int) -> str:
    return CIRCLED[n - 1] if 1 <= n <= len(CIRCLED) else str(n)


@dataclass
class Piece:
    text: str
    span: str | None = None


class MarkupError(ValueError):
    pass


_SPECIAL = "[]{}_^<>\\"


def escape(text: str) -> str:
    return re.sub(r"([%s])" % re.escape(_SPECIAL), r"\\\1", text)


def parse(source: str, *, auto_start: int = 1) -> tuple[list[Piece], int]:
    """記法を Piece の並びに分解する。戻り値は (並び, 次の自動番号)。"""
    pieces: list[Piece] = []
    buf: list[str] = []
    counter = auto_start
    i, n = 0, len(source)

    def flush() -> None:
        if buf:
            pieces.append(Piece("".join(buf)))
            buf.clear()

    def read_until(start: int, closer: str) -> tuple[str, int]:
        out: list[str] = []
        j = start
        while j < n:
            if source[j] == "\\" and j + 1 < n:
                out.append(source[j + 1])
                j += 2
                continue
            if source.startswith(closer, j):
                return "".join(out), j + len(closer)
            out.append(source[j])
            j += 1
        raise MarkupError(f"閉じ記号 {closer!r} が見つかりません: {source!r}")

    while i < n:
        ch = source[i]
        if ch == "\\" and i + 1 < n:
            buf.append(source[i + 1])
            i += 2
        elif ch == "[":
            body, i = read_until(i + 1, "]")
            if "|" not in body:
                raise MarkupError(f"[番号|語] の形ではありません: [{body}]"
                                  "（記号の [ をそのまま出すときは \\[ と書く）")
            label, word = body.split("|", 1)
            label = label.strip()
            if label in ("#", ""):
                label = circled(counter)
                counter += 1
            flush()
            pieces.append(Piece(label, "sup"))
            if word:
                pieces.append(Piece(word, "u"))
        elif source.startswith("{{", i):
            body, i = read_until(i + 2, "}}")
            flush()
            pieces.append(Piece(body, "hide"))
        elif ch == "{":
            body, i = read_until(i + 1, "}")
            flush()
            pieces.append(Piece(body, "ans"))
        elif source.startswith("<<", i):
            body, i = read_until(i + 2, ">>")
            if "|" not in body:
                raise MarkupError(f"<<名前|語>> の形ではありません: <<{body}>>")
            name, word = body.split("|", 1)
            flush()
            pieces.append(Piece(word, name.strip()))
        elif ch in "_^":
            body, i = read_until(i + 1, ch)
            flush()
            pieces.append(Piece(body, "u" if ch == "_" else "sup"))
        else:
            buf.append(ch)
            i += 1
    flush()
    return [p for p in pieces if p.text], counter


def render(pieces: list[Piece]) -> str:
    """Piece の並びを記法に戻す（抽出ツールが使う）。"""
    out: list[str] = []
    i = 0
    while i < len(pieces):
        p = pieces[i]
        nxt = pieces[i + 1] if i + 1 < len(pieces) else None
        if p.span == "sup" and len(p.text) == 1 and nxt is not None and nxt.span == "u":
            out.append("[%s|%s]" % (escape(p.text), escape(nxt.text)))
            i += 2
            continue
        body = escape(p.text)
        out.append({
            None: "%s", "ans": "{%s}", "hide": "{{%s}}", "u": "_%s_", "sup": "^%s^",
        }.get(p.span, "<<%s|%%s>>" % p.span) % body)
        i += 1
    return "".join(out)


def plain(source: str) -> str:
    """記法を外した素の文字列。"""
    return "".join(p.text for p in parse(source)[0])
