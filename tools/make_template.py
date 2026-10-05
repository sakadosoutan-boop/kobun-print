#!/usr/bin/env python3
"""益田先生のプリント（docx）から、古文教材のテンプレートを作る。

    python3 tools/make_template.py prints/徒然草_あだし野の露_改訂.docx \\
        --name 授業プリント --data data/徒然草_あだし野の露.json

できるもの
  template/<名前>/base.docx      組版の正本。文字の入る場所が ⟦s0001⟧ の目印になっている
  template/<名前>/spans.json     書式表（傍線・答えの色、原本に残る細かな書式の差）
  template/<名前>/regions.json   区画表（プリントごとの「本文」「現代語訳」「設問」…）
  template/<名前>/defaults.json  元のプリントの文言（見出しなど、教材によらない部分に使う）
  data/<教材>.json               元のプリントの中身を教材形式で書いたもの
  data/_雛形_<名前>.json          空の雛形
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kobunprint import markup  # noqa: E402
from kobunprint import slots as slotlib  # noqa: E402
from kobunprint.docxpkg import DocxPackage  # noqa: E402

# 教材によらず、元のプリントの文字をそのまま使う区画
FIXED = ["氏名欄", "見出し・現代語訳", "見出し・文法事項", "見出し・品詞分解",
         "飾り", "図中の文字", "文言"]

# 区画を並べる順番（regions.json と雛形の見やすさのため）
ORDER = ["ヘッダ", "氏名欄", "題名", "本文", "見出し・品詞分解", "品詞分解", "品詞分解・敬意",
         "見出し・現代語訳", "現代語訳", "見出し・文法事項", "文法事項",
         "見出し・文学史", "文学史", "設問", "図解", "コラム", "飾り", "図中の文字", "文言"]


def _dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sheet_name(header: str, index: int, used: set[str]) -> str:
    """ヘッダ行の末尾の「表」「裏」をプリント名にする。無ければ N枚目。"""
    m = re.search(r"(表|裏)\s*$", markup.plain(header).strip())
    name = m.group(1) if m else f"{index}枚目"
    if name in used:
        name = f"{index}枚目"
    used.add(name)
    return name


def group_regions(slots: list[slotlib.Slot]) -> dict[str, list[str]]:
    """1 枚のプリントのスロットを区画にまとめる。設問は 設問N・問／設問N・答 に分ける。"""
    regions: dict[str, list[str]] = {}
    n = 0
    for slot in slots:
        if slot.label == "設問":
            n += 1
            name = f"設問{n}・問"
        elif slot.label == "答":
            name = f"設問{max(n, 1)}・答"
        else:
            name = slot.label
        regions.setdefault(name, []).append(slot.slot_id)

    def key(name: str):
        base = re.sub(r"\d+・(問|答)$", "", name)
        rank = ORDER.index(base) if base in ORDER else len(ORDER)
        m = re.match(r"設問(\d+)・(問|答)", name)
        return (rank, int(m.group(1)) if m else 0, m.group(2) == "答" if m else 0)

    return {k: regions[k] for k in sorted(regions, key=key)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="元にするプリント（docx）")
    parser.add_argument("--name", required=True, help="テンプレートの名前（例: 授業プリント）")
    parser.add_argument("--data", required=True, help="元のプリントの中身を書き出す教材データ")
    args = parser.parse_args(argv)

    tdir = ROOT / "template" / args.name
    package = DocxPackage(args.source)
    root = package.parse_document()
    found = slotlib.extract(root)
    package.set_document(root)
    package.save(tdir / "base.docx")

    shared: dict[str, dict] = {}
    for slot in found:
        shared.update(slot.extra_spans)
    _dump(tdir / "spans.json", {
        "説明": "書式表。共通の 書式NN と、スロットごとの上書き（原本に残る細かな書式の差）。",
        "共通": shared,
        "スロット別": {s.slot_id: s.local_spans for s in found if s.local_spans},
    })
    _dump(tdir / "defaults.json", {s.slot_id: s.text for s in found})

    sheets, used = [], set()
    for index in sorted({s.sheet for s in found}):
        own = [s for s in found if s.sheet == index]
        header = next((s.text for s in own if s.label == "ヘッダ"), "")
        regions = group_regions(own)
        sheets.append({
            "名前": sheet_name(header, index, used),
            "見出し": markup.plain(header).strip(),
            "区画": regions,
            "原本の文字を使う": [r for r in regions if r in FIXED],
            "削除可": [r for r in regions if r.endswith("・問")],
        })
    _dump(tdir / "regions.json", {
        "説明": "区画表。教材形式の JSON は、プリント名と区画名でこの表を引いて流し込む。"
                "『原本の文字を使う』区画は、教材データで書かなければ元のプリントの文字のまま。",
        "元のプリント": Path(args.source).name,
        "ページ数": 2,
        "sheets": sheets,
    })

    # 元のプリントの中身を教材形式で書き出す（テンプレートから組めば元と同じになる）
    texts = {s.slot_id: s.text for s in found}
    content: dict[str, dict] = {}
    blank: dict[str, dict] = {}
    for sheet in sheets:
        body, empty = {}, {}
        questions, empties = [], []
        for name, ids in sheet["区画"].items():
            if name in sheet["原本の文字を使う"]:
                continue
            lines = [texts[i] for i in ids]
            m = re.match(r"設問(\d+)・(問|答)", name)
            if m:
                k = int(m.group(1)) - 1
                while len(questions) <= k:
                    questions.append({"問": "", "答": []})
                    empties.append({"問": "", "答": []})
                if m.group(2) == "問":
                    questions[k]["問"] = lines[0]
                    empties[k]["問"] = f"☆{k + 1}　（設問）"
                else:
                    questions[k]["答"] = lines
                    empties[k]["答"] = ["　{（解答）}"] + [""] * (len(ids) - 1)
                continue
            single = len(ids) == 1 and name in ("ヘッダ", "題名")
            body[name] = lines[0] if single else lines
            # 雛形は原本と同じ行数にしておく。行を減らすと、段落に結び付いた枠や
            # 巻物が寄り集まって崩れるので、残りは空行で場所を取っておく。
            empty[name] = f"（{name}）" if single else [f"（{name}）"] + [""] * (len(ids) - 1)
        if questions:
            body["設問"], empty["設問"] = questions, empties
        content[sheet["名前"]], blank[sheet["名前"]] = body, empty

    meta = {"テンプレート": f"template/{args.name}"}
    _dump(Path(args.data), {"meta": {**meta, "題名": Path(args.data).stem},
                            "options": {"answer_mode": "原本どおり"}, "sheets": content})
    _dump(ROOT / "data" / f"_雛形_{args.name}.json", {
        "meta": {**meta, "題名": "（作品名・章段名）"},
        "options": {"answer_mode": "原本どおり"},
        "_記法": {
            "[①|参り]": "傍線番号（上付き）＋傍線を引く語。[#|語] で自動採番",
            "{語}": "答え（赤字）",
            "{{語}}": "隠し答え（白字。印刷すると空欄に見える）",
            "_語_": "傍線のみ", "^語^": "上付きのみ",
            "{\"品詞分解\": {...}}": "品詞分解の行を自動で組む（README 参照）",
            "行頭の全角スペース": "字下げ（段落の始まり）",
        },
        "sheets": blank,
    })

    for sheet in sheets:
        print(f"■ {sheet['名前']}（{sheet['見出し'][:30]}…）")
        for name, ids in sheet["区画"].items():
            mark = "　※原本の文字" if name in sheet["原本の文字を使う"] else ""
            print(f"    {name}: {len(ids)} 行{mark}")
    print(f"→ {tdir.relative_to(ROOT)}/ と {args.data}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
