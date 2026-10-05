#!/usr/bin/env python3
"""『徒然草』「あだし野の露消ゆる時なく」プリントの後半（裏面）を組み直す。

前半（表面＝授業プリント①）には一切触れない。裏面のうち、
下書きのまま残っていた段落（☆３の前教材からの残骸、板書例の断片、
学習活動３のメモ）を、設問と「筆者の主張のまとめ」の図解に置き換える。

書式は既存の段落から丸ごと借りるので、見た目は元のプリントのまま。
解答は赤字（FF0000）で入れる。表面の【現代語訳】や☆１☆２と同じ約束。
"""

from __future__ import annotations

import copy
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML = "http://www.w3.org/XML/1998/namespace"
DOCUMENT = "word/document.xml"


def w(tag: str) -> str:
    return "{%s}%s" % (W, tag)


def register(xml: bytes) -> None:
    for prefix, uri in re.findall(rb'xmlns:([A-Za-z0-9_.-]+)\s*=\s*"([^"]*)"', xml[:8192]):
        if not re.match(rb"^ns\d+$", prefix):
            ET.register_namespace(prefix.decode(), uri.decode())


def is_layout_run(run: ET.Element) -> bool:
    """図形・枠を抱えた run か。mc:AlternateContent は w: ではないので局所名で見る。"""
    return any(c.tag.split("}")[-1] in ("AlternateContent", "drawing", "pict") for c in run)


def text_of(p: ET.Element) -> str:
    return "".join(t.text or "" for t in p.iter(w("t")))


# ---------------------------------------------------------------- 本文づくり
# {…} で囲んだところが解答（赤字）になる。
RED = "FF0000"
_SEG = re.compile(r"\{([^}]*)\}")


def make_runs(line: str, model: ET.Element) -> list[ET.Element]:
    """1 行ぶんの run を作る。model の rPr を基準の書式として使う。"""
    base = model.find(w("rPr"))
    runs: list[ET.Element] = []
    pieces = []
    pos = 0
    for m in _SEG.finditer(line):
        if m.start() > pos:
            pieces.append((line[pos:m.start()], None))
        pieces.append((m.group(1), RED))
        pos = m.end()
    if pos < len(line):
        pieces.append((line[pos:], None))

    for text, colour in pieces:
        if not text:
            continue
        run = ET.Element(w("r"))
        rpr = copy.deepcopy(base) if base is not None else ET.Element(w("rPr"))
        for old in rpr.findall(w("color")):
            rpr.remove(old)
        if colour:
            col = ET.Element(w("color"))
            col.set(w("val"), colour)
            # w:rPr の中で色は rFonts の後ろあたり。末尾でも Word は読む。
            rpr.append(col)
        if len(rpr):
            run.append(rpr)
        t = ET.SubElement(run, w("t"))
        t.set("{%s}space" % XML, "preserve")
        t.text = text
        runs.append(run)
    return runs


def make_para(line: str, model: ET.Element) -> ET.Element:
    """model の段落書式を借りて、1 行ぶんの段落を作る。"""
    para = ET.Element(w("p"))
    ppr = model.find(w("pPr"))
    if ppr is not None:
        para.append(copy.deepcopy(ppr))
    model_run = model.find(w("r"))
    for run in make_runs(line, model_run if model_run is not None else ET.Element(w("r"))):
        para.append(run)
    return para


# ---------------------------------------------------------------- 差し替え内容
QUESTION_3 = (
    "☆３ 本文は三つの段落からなる。それぞれ何について述べた段落かを書き、その働きを考えよう。"
)

BLOCK = [
    "",
    "　第一段落…〔{　世　}〕について　→　兼好の〔{　主張　}〕",
    "　第二段落…〔{　人（命）　}〕について　→　主張の〔{　根拠①　}〕",
    "　第三段落…〔{　老い（長命）　}〕について　→　主張の〔{　根拠②　}〕",
    "",
    "☆４ この文章に「無常」という語は一度も出てこない。それでも「無常」が読み取れるのは",
    "　　なぜか。手がかりになる本文の語句を三つ挙げて説明しよう。",
    "　語句…〔{　露　・　煙　・　定めなき　（かげろふ・夏の蟬　も可）　}〕",
    "　説明…〔{　消える・立ち去る・短い命など、とどまらず移り変わることを表す語が　}〕",
    "　　　　〔{　重ねられ、世も人も永遠ではないことが示されているから。　}〕",
    "",
    "〖 兼好の主張をまとめよう 〗　空欄をうめながら、三つの段落のつながりをたどろう。",
    "",
    "【第一段落】＝主張",
    "　住み果つるならひ ＝〔{　常住　}〕…　もののあはれも〔{　なからん　}〕",
    "　　　　　　　　　⇔",
    "　世は定めなきこそ ＝〔{　無常　}〕…〔{　いみじけれ　}〕＝肯定　←〔{　逆説　}〕",
    "",
    "【第二段落】＝根拠①〔{　命の長さ　}〕",
    "　かげろふ・夏の蟬　＜　人　…　人ばかり久しきはなし",
    "　一年を暮らすほどだにも、こよなう〔{　のどけしや　}〕",
    "　　　　　　　　　⇔　千年を過ぐすとも、一夜の〔{　夢　}〕の心地こそせめ",
    "　→　問題は命の〔{　長さ　}〕ではなく、〔{　飽かず、惜し　}〕と思ふ心にある",
    "",
    "【第三段落】＝根拠②〔{　長命の害　}〕",
    "　四十に足らぬほどにて死なんこそ ＝〔{　めやすかるべけれ　}〕",
    "　　　　　　　　　⇔　そのほど過ぎぬれば　→　長命がもたらす〔{　欲　}〕",
    "　　・かたちを恥づる心もなく　・人に出で交じらはんことを思ひ　・子孫を愛し",
    "　　・さかゆく末を見んまでの命をあらまし　・ひたすら世を貪る心のみ深く",
    "　→　もののあはれも〔{　知らずなりゆく　}〕　※第一段落の「もののあはれ」と呼応",
    "",
    "〖まとめ〗　人は〔{　有限　}〕で、必ず〔{　死ぬ　}〕存在であるからこそ、",
    "　　　　　〔{　もののあはれ　}〕を感じることができる。だから、定めなき一生を",
    "　　　　　〔{　前向きに美しく　}〕生きるべきだ、と兼好は述べている。",
]


def main() -> int:
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])

    with zipfile.ZipFile(src) as zf:
        names = zf.namelist()
        parts = {n: zf.read(n) for n in names}
        compress = {i.filename: i.compress_type for i in zf.infolist()}

    register(parts[DOCUMENT])
    root = ET.fromstring(parts[DOCUMENT])
    body = root.find(w("body"))
    paras = [c for c in body if c.tag == w("p")]

    # 目印になる段落を内容で探す（添字を直接書くと原本を差し替えたとき壊れる）
    def find(pattern: str, start: int = 0) -> int:
        for i in range(start, len(paras)):
            if re.search(pattern, text_of(paras[i])):
                return i
        raise SystemExit(f"目印の段落が見つかりません: {pattern}")

    i_q3 = find(r"☆\s*３")
    i_first = find(r"露消ゆる時なもなからん")          # 板書例の断片の先頭
    i_keep = find(r"読解のために")                     # 図形を抱えた段落＝残す
    model = paras[i_first]

    # ☆３ を差し替え（前教材『古今著聞集』の設問が残っていた）
    # 文字の run だけを差し替える。☆３の枠（角丸四角形）は同じ段落に錨があるので残す。
    q3 = paras[i_q3]
    text_runs = [r for r in q3.findall(w("r")) if not is_layout_run(r)]
    position = list(q3).index(text_runs[0]) if text_runs else len(q3)
    for run in text_runs:
        q3.remove(run)
    for offset, run in enumerate(make_runs(QUESTION_3, model.find(w("r")))):
        q3.insert(position + offset, run)

    # 下書きの段落を新しい本文で置き換える
    anchor = list(body).index(paras[i_first])
    for para in paras[i_first:i_keep]:
        body.remove(para)
    for offset, line in enumerate(BLOCK):
        body.insert(anchor + offset, make_para(line, model))

    # 図形を抱えた段落に残っていた下書きの一文を落とす。
    # 図形（【ー読解のためにー】や「自／他」の軸）はレイアウトなので残す。
    keep = paras[i_keep]
    for run in list(keep.findall(w("r"))):
        if is_layout_run(run):
            break
        if re.match(r"^〇長く生きて", "".join(t.text or "" for t in run.iter(w("t")))):
            keep.remove(run)

    # 末尾の空段落を整理（Word で 3 ページ目に溢れていた）
    tail = [c for c in body if c.tag == w("p")]
    blanks = 0
    for para in reversed(tail):
        if text_of(para).strip() or list(para.iter(w("drawing"))):
            break
        blanks += 1
        if blanks > 1:                      # 1 つだけ残す
            body.remove(para)

    xml = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
    xml = xml.replace(
        b"<?xml version='1.0' encoding='UTF-8'?>\n",
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n', 1)
    parts[DOCUMENT] = xml

    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dst, "w") as zf:
        for name in names:
            zf.writestr(zipfile.ZipInfo(name), parts[name],
                        compress_type=compress.get(name, zipfile.ZIP_DEFLATED))
    print(f"☆３を差し替え、下書き {i_keep - i_first} 段落を {len(BLOCK)} 段落に組み直しました")
    print(f"  出力: {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
