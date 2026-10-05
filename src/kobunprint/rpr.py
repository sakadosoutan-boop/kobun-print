"""文字書式（w:rPr）の差分計算と適用。

段落の中の各 run は「段落の基準書式＋わずかな差分」でできている。本文なら差分は
傍線（下線）と傍線番号（上付き）、解答欄なら赤字（答え）や白字（隠し答え）。
差分そのものが教材の意味を担っているので、それを名前付きの「スパン」として扱う。

rPr は「プロパティ名 → 生 XML 断片」の辞書で持ち回る。rFonts のように属性の多い
要素でも情報が落ちない。
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from .docxpkg import W, w

# CT_RPr の子要素はスキーマ上の順序が決まっている。差し込むときもこの順を守る。
RPR_ORDER = [
    "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike",
    "dstrike", "outline", "shadow", "emboss", "imprint", "noProof",
    "snapToGrid", "vanish", "webHidden", "color", "spacing", "w", "kern",
    "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd",
    "fitText", "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout",
    "specVanish", "oMath",
]
_ORDER = {name: i for i, name in enumerate(RPR_ORDER)}


def _local(el: ET.Element) -> str:
    return el.tag.split("}")[-1]


def to_dict(rpr: ET.Element | None) -> dict[str, str]:
    if rpr is None:
        return {}
    return {_local(c): ET.tostring(c, encoding="unicode") for c in rpr}


def diff(base: dict[str, str], other: dict[str, str]) -> dict:
    """base → other の差分を {"set": {...}, "unset": [...]} で返す。"""
    set_ = {k: v for k, v in other.items() if base.get(k) != v}
    unset = sorted(k for k in base if k not in other)
    delta: dict = {}
    if set_:
        delta["set"] = set_
    if unset:
        delta["unset"] = unset
    return delta


def apply(base: dict[str, str], delta: dict) -> dict[str, str]:
    out = dict(base)
    for key in delta.get("unset", []):
        out.pop(key, None)
    out.update(delta.get("set", {}))
    return out


def build(props: dict[str, str]) -> ET.Element | None:
    if not props:
        return None
    rpr = ET.Element(w("rPr"))
    for name in sorted(props, key=lambda n: (_ORDER.get(n, len(RPR_ORDER)), n)):
        rpr.append(ET.fromstring(props[name]))
    return rpr


def signature(delta: dict) -> str:
    parts = [f"+{k}={v}" for k, v in sorted(delta.get("set", {}).items())]
    parts += [f"-{k}" for k in delta.get("unset", [])]
    return "|".join(parts)


def colour_fragment(value: str) -> str:
    return '<w:color xmlns:w="%s" w:val="%s" />' % (W, value)


# 差分に意味の名前を与える。教材データの短縮記法はこの名前に対応する。
SEMANTIC_SPANS: dict[str, dict] = {
    "ans": {"set": {"color": colour_fragment("FF0000")}},             # 答え（赤字）
    "hide": {"set": {"color": colour_fragment("FFFFFF")}},            # 隠し答え（白字）
    "u": {"set": {"u": '<w:u xmlns:w="%s" w:val="single" />' % W}},  # 傍線
    "sup": {"set": {"vertAlign":                                       # 傍線番号
                    '<w:vertAlign xmlns:w="%s" w:val="superscript" />' % W}},
}


def _val_of(fragment: str) -> str | None:
    return ET.fromstring(fragment).get(w("val"))


_SEMANTIC_BY_VAL = {
    (next(iter(d["set"])), _val_of(next(iter(d["set"].values())))): name
    for name, d in SEMANTIC_SPANS.items()
}
_CORE_PROPS = {"u", "vertAlign", "color"}


def semantic_name(delta: dict) -> str | None:
    """差分がちょうど既知の意味スパンなら、その名前を返す。

    照合はプロパティ名と w:val だけで行う。原本の白字には
    w:themeColor="background1" が付いていることがあるが、見た目は同じなので
    同じ「隠し答え」とみなす。
    """
    if delta.get("unset"):
        return None
    props = delta.get("set", {})
    if len(props) != 1:
        return None
    name, fragment = next(iter(props.items()))
    return _SEMANTIC_BY_VAL.get((name, _val_of(fragment)))


def semantic_core(delta: dict) -> str | None:
    """「傍線＋余計なフォント指定」のような差分の、意味の芯の名前を返す。

    Word は編集の履歴で、和文には効かない欧文フォント指定を run に残すことがある。
    記法まで引きずられると本文が読めなくなるので、芯が 1 つだけでほかが rFonts
    だけなら、芯の名前で呼ぶ。実際の書式はスロットごとの上書きとして別に持つ。
    """
    if delta.get("unset"):
        return None
    props = delta.get("set", {})
    cores = [k for k in props if k in _CORE_PROPS]
    if len(cores) != 1 or set(props) - {cores[0], "rFonts"}:
        return None
    return _SEMANTIC_BY_VAL.get((cores[0], _val_of(props[cores[0]])))


def recolour(props: dict[str, str], mapping: dict[str, str] | None) -> dict[str, str]:
    """文字色を読み替える（解答の見せ方の切り替えに使う）。"""
    if not mapping or "color" not in props:
        return props
    target = mapping.get(_val_of(props["color"]))
    if target is None:
        return props
    return {**props, "color": colour_fragment(target)}
