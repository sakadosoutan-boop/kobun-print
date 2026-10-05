"""レイアウト（テンプレート）と文言（教材データ）を切り分ける層。

原本の組版は A4 横・縦書き・段組と、枠・巻物・イラストなどのフローティング図形で
できている。これを作り直すと必ずどこかがずれるので、**原本の XML を組版の正本と
して残し、文字の入る場所だけを「スロット」に置き換える**。

スロットにするのは「w:t だけを持つ素の run」の連なり。図形・ルビ・フィールドを
含む run はレイアウトの一部として触らない。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from . import markup, rpr
from .docxpkg import XML_NS, w

SLOT_OPEN, SLOT_CLOSE = "⟦", "⟧"
SLOT_RE = re.compile(r"⟦([^⟧]+)⟧")

# run を丸ごとレイアウトとして残す子要素
OPAQUE = {"drawing", "AlternateContent", "ruby", "fldChar", "instrText", "pict"}


def _local(el: ET.Element) -> str:
    return el.tag.split("}")[-1]


def is_plain_text_run(el: ET.Element) -> bool:
    if el.tag != w("r"):
        return False
    kids = {_local(c) for c in el}
    return not (kids & OPAQUE) and bool(kids & {"t", "tab", "br"})


def run_text(run: ET.Element) -> str:
    out = []
    for c in run:
        name = _local(c)
        if name == "t":
            out.append(c.text or "")
        elif name == "tab":
            out.append("\t")
        elif name == "br":
            out.append("\n")
    return "".join(out)


def has_layout(para: ET.Element) -> bool:
    """段落が図形の錨や改セクションを抱えているか（＝消したり複製したりできない）。"""
    for run in para.findall(w("r")):
        if {_local(c) for c in run} & OPAQUE:
            return True
    ppr = para.find(w("pPr"))
    return ppr is not None and ppr.find(w("sectPr")) is not None


@dataclass
class Slot:
    slot_id: str
    text: str                                   # 短縮記法の文字列
    label: str = ""                             # 推定した役割（本文・現代語訳 など）
    base: dict[str, str] = field(default_factory=dict)          # 基準の文字書式
    extra_spans: dict[str, dict] = field(default_factory=dict)  # 書式NN の定義
    local_spans: dict[str, dict] = field(default_factory=dict)  # このスロットだけの上書き
    sheet: int = 0              # 何枚目のプリントか（ヘッダ行で数える）
    boxed: bool = False         # 罫線で囲まれた段落か（現代語訳の枠など）
    in_shape: bool = False      # フローティング図形の中の文字か
    sole: bool = False          # 段落にこのスロットしか無く、図形も無い（増減できる）
    font: str = ""              # 基準書式の和文フォント


# ---------------------------------------------------------------- 役割の推定
# 益田先生の二つのプリント（能は歌詠み／あだし野の露）を突き合わせて決めた規則。
# 見出しの括弧は【】〖】《》が混在していたので、どれでも拾う。
_LABEL_RULES = [
    (re.compile(r"^【.*】.*プリント"), "ヘッダ"),
    (re.compile(r"組.*番.*氏名"), "氏名欄"),
    (re.compile(r"^[【《〖]\s*現代語訳\s*[】》〗]"), "見出し・現代語訳"),
    (re.compile(r"^[【《〖]\s*品詞分解\s*[】》〗]"), "見出し・品詞分解"),
    (re.compile(r"^[【《〖]\s*文法事項\s*[】》〗]"), "見出し・文法事項"),
    (re.compile(r"^文学史"), "見出し・文学史"),
    (re.compile(r"^敬語の種類"), "品詞分解・敬意"),
    (re.compile(r"^[①-⑳㉑-㉟㊱-㊿➆]\s*[（(].*(詞|活用)"), "品詞分解"),
    (re.compile(r"^コラム"), "コラム"),
    (re.compile(r"^[☆★❶-❿]"), "設問"),
    (re.compile(r"^〖"), "図解"),
    (re.compile(r"^※"), "文法事項"),
]
_BODY_FONT = re.compile(r"教科書体|Kyokasho")
_TITLE_FONT = re.compile(r"はれのそら")


def guess_label(text: str, font: str = "") -> str:
    plain = markup.plain(text).strip()
    for pattern, label in _LABEL_RULES:
        if pattern.search(plain):
            return label
    if _TITLE_FONT.search(font):
        return "題名"
    if _BODY_FONT.search(font) or any(p.span == "sup" for p in markup.parse(text)[0]):
        return "本文"
    return "文言"


def _refine_labels(slots: list[Slot]) -> None:
    """文字だけでは分からない役割を、前後関係から補う。

    ・見出し（【現代語訳】【文法事項】文学史）より後ろの段落は、その見出しの中身
      （現代語訳と文法事項は罫線の枠の中だけ）
    ・図形の中の文字は「図中の文字」
    ・設問より後ろで設問でも図解でもない行は、その設問の「答」
    ・図形と同じ段落にある設問・図解まわりの文字は「飾り」
    ・〖…〗で始まる行より後ろは、プリントの終わりまで「図解」
    """
    mode, sheet = "", 0
    for slot in slots:
        if slot.sheet != sheet:
            sheet, mode = slot.sheet, ""
        if slot.in_shape:
            if slot.label in ("文言", "本文"):
                slot.label = "図中の文字"
            continue
        if slot.label.startswith("見出し・"):
            mode = slot.label.split("・", 1)[1]
            continue
        if slot.label == "設問":
            mode = "設問"
            continue
        if slot.label == "図解":
            mode = "図解"
            continue
        if not slot.sole and slot.label in ("文言", "本文", "図解") and mode in ("図解", "設問"):
            slot.label = "飾り"           # 図形と同じ段落に置かれた飾りの文字（自／他 など）
        elif mode == "図解":
            slot.label = "図解"
        elif mode == "設問" and slot.label in ("文言", "本文", "品詞分解"):
            slot.label = "答"
        elif mode in ("現代語訳", "文法事項") and slot.boxed and slot.label in (
                "文言", "本文", "品詞分解", "文法事項"):
            slot.label = mode
        elif mode == "文学史" and slot.label == "文言":
            slot.label = "文学史"


# ---------------------------------------------------------------- 抽出
def extract(root: ET.Element) -> list[Slot]:
    """文書をスロット化する（root は書き換わる）。文書順のスロットを返す。"""
    paragraphs = list(root.iter(w("p")))
    registry: dict[str, str] = {}        # 差分の署名 → 書式NN
    definitions: dict[str, dict] = {}    # 書式NN → 差分

    inside_shape: set[int] = set()
    for para in paragraphs:
        for nested in para.iter(w("p")):
            if nested is not para:
                inside_shape.add(id(nested))

    plan: list[tuple[ET.Element, list[list[ET.Element]]]] = []
    slots: list[Slot] = []
    for para in paragraphs:
        groups: list[list[ET.Element]] = []
        current: list[ET.Element] = []
        for child in para:
            if is_plain_text_run(child):
                current.append(child)
            elif current:
                groups.append(current)
                current = []
        if current:
            groups.append(current)
        if not groups:
            continue
        ppr = para.find(w("pPr"))
        boxed = ppr is not None and ppr.find(w("pBdr")) is not None
        sole = len(groups) == 1 and not has_layout(para)
        for group in groups:
            slot = _make_slot("s%04d" % (len(slots) + 1), group, registry, definitions)
            slot.boxed, slot.in_shape, slot.sole = boxed, id(para) in inside_shape, sole
            slot.label = guess_label(slot.text, slot.font)
            slots.append(slot)
        plan.append((para, groups))

    # 置換は段落ごとに後ろのグループから（前のグループの位置がずれない）
    index = 0
    for para, groups in plan:
        own = slots[index:index + len(groups)]
        index += len(groups)
        for group, slot in zip(reversed(groups), reversed(own)):
            position = list(para).index(group[0])
            para.insert(position, make_marker(slot.slot_id, slot.base))
            for run in group:
                para.remove(run)

    sheet = 0
    for slot in slots:
        if slot.label == "ヘッダ" and not slot.in_shape:
            sheet += 1
        slot.sheet = max(sheet, 1)
    _refine_labels(slots)

    for slot in slots:
        used = {p.span for p in markup.parse(slot.text)[0] if p.span}
        slot.extra_spans = {n: definitions[n] for n in sorted(used) if n in definitions}
    return slots


def _make_slot(slot_id, runs, registry, definitions) -> Slot:
    props = [rpr.to_dict(r.find(w("rPr"))) for r in runs]
    texts = [run_text(r) for r in runs]
    # 基準書式は「最も多くの文字を占める書式」。run の数で数えると、1 文字ずつに
    # 細切れになる傍線番号のほうが多数派になってしまう。
    weight: Counter = Counter()
    for prop, text in zip(props, texts):
        weight[rpr.signature({"set": prop})] += len(text)
    best = max(weight, key=lambda s: (weight[s], s))
    base = next(p for p in props if rpr.signature({"set": p}) == best)

    pieces: list[markup.Piece] = []
    local: dict[str, dict] = {}
    for prop, text in zip(props, texts):
        if not text:
            continue
        delta = rpr.diff(base, prop)
        if not delta:
            span = None
        else:
            span = rpr.semantic_name(delta)
            if span is None:
                core = rpr.semantic_core(delta)
                if core is not None and local.get(core, delta) == delta:
                    local[core] = delta          # 意味の名前で呼び、書式は上書きで持つ
                    span = core
                else:
                    sig = rpr.signature(delta)
                    if sig not in registry:
                        registry[sig] = "書式%02d" % (len(registry) + 1)
                    span = registry[sig]
                    definitions[span] = delta
        if pieces and pieces[-1].span == span:
            pieces[-1].text += text
        else:
            pieces.append(markup.Piece(text, span))

    font = ""
    if "rFonts" in base:
        el = ET.fromstring(base["rFonts"])
        font = el.get(w("eastAsia")) or el.get(w("ascii")) or ""
    return Slot(slot_id, markup.render(pieces), base=base, local_spans=local, font=font)


def make_marker(slot_id: str, base: dict[str, str]) -> ET.Element:
    run = ET.Element(w("r"))
    el = rpr.build(base)
    if el is not None:
        run.append(el)
    t = ET.SubElement(run, w("t"))
    t.set("{%s}space" % XML_NS, "preserve")
    t.text = f"{SLOT_OPEN}{slot_id}{SLOT_CLOSE}"
    return run


# ---------------------------------------------------------------- 目印の検索
def marker_of(run: ET.Element) -> str | None:
    if run.tag != w("r"):
        return None
    t = run.find(w("t"))
    if t is None or not t.text:
        return None
    m = SLOT_RE.fullmatch(t.text.strip())
    return m.group(1) if m else None


def locate(root: ET.Element) -> dict[str, tuple[ET.Element, ET.Element]]:
    """スロット ID → (段落, 目印の run)。"""
    found = {}
    for para in root.iter(w("p")):
        for run in para.findall(w("r")):
            sid = marker_of(run)
            if sid:
                found[sid] = (para, run)
    return found


# ---------------------------------------------------------------- 流し込み
def fill(
    root: ET.Element,
    values: dict[str, str],
    spans: dict[str, dict],
    local_spans: dict[str, dict[str, dict]] | None = None,
    recolour: dict[str, str] | None = None,
) -> list[str]:
    """目印を文言で置き換える。値の無い目印は消す（空欄にする）。

    ``recolour`` は「この色を別の色に読み替える」表。段落まるごと赤字で書かれた
    解答行は色が基準書式に乗っているので、ここで基準書式ごと塗り替える。
    戻り値は値が無かったスロット ID。
    """
    local_spans = local_spans or {}
    missing = []
    for sid, (para, run) in locate(root).items():
        if sid not in values:
            missing.append(sid)
            para.remove(run)
            continue
        base = rpr.recolour(rpr.to_dict(run.find(w("rPr"))), recolour)
        merged = {**spans, **local_spans.get(sid, {})}
        position = list(para).index(run)
        para.remove(run)
        for offset, new in enumerate(build_runs(values[sid], base, merged)):
            para.insert(position + offset, new)
    return missing


def build_runs(text: str, base: dict[str, str], spans: dict[str, dict]) -> list[ET.Element]:
    pieces, _ = markup.parse(text)
    runs = []
    for piece in pieces:
        delta = {} if piece.span is None else spans.get(piece.span) \
            or rpr.SEMANTIC_SPANS.get(piece.span)
        if delta is None:
            raise KeyError(f"書式表に無い書式名です: {piece.span}（{text!r}）")
        run = ET.Element(w("r"))
        el = rpr.build(rpr.apply(base, delta))
        if el is not None:
            run.append(el)
        for token in re.split(r"([\t\n])", piece.text):
            if token == "\t":
                ET.SubElement(run, w("tab"))
            elif token == "\n":
                ET.SubElement(run, w("br"))
            elif token:
                t = ET.SubElement(run, w("t"))
                t.set("{%s}space" % XML_NS, "preserve")
                t.text = token
        runs.append(run)
    return runs


def recolour_opaque(root: ET.Element, mapping: dict[str, str] | None) -> None:
    """ルビなど、スロットにならない run の文字色も読み替える。"""
    if not mapping:
        return
    for run in root.iter(w("r")):
        if not ({_local(c) for c in run} & OPAQUE):
            continue
        for target in [run, *run.iter(w("r"))]:
            el = target.find(w("rPr"))
            colour = el.find(w("color")) if el is not None else None
            if colour is not None and colour.get(w("val")) in mapping:
                colour.set(w("val"), mapping[colour.get(w("val"))])
                colour.attrib.pop(w("themeColor"), None)
