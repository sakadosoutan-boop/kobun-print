#!/usr/bin/env python3
"""教材データ（JSON）とテンプレートから、古文プリント（docx）を組む。

    python3 src/build.py data/徒然草_あだし野の露.json -o build/あだし野.docx
    python3 src/build.py data/徒然草_あだし野の露.json -o build/配布用.docx --answers 空欄

--answers で解答の見せ方を切り替える。

  原本どおり  赤字の答えは赤字、白字の隠し答えは白字のまま（既定）
  答え        隠し答えも赤字にして、すべて見せる
  空欄        赤字の答えも白字にして、すべて空欄にする（配布用）
  黒          すべての答えを黒字にする（モノクロ印刷の解答例）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kobunprint import material, regions as regionlib, rpr, volume  # noqa: E402
from kobunprint import slots as slotlib  # noqa: E402
from kobunprint.docxpkg import DocxPackage, w  # noqa: E402

ANSWER_MODES = {
    "原本どおり": None,
    "答え": {"FFFFFF": "FF0000"},
    "空欄": {"FF0000": "FFFFFF"},
    "黒": {"FF0000": "000000", "FFFFFF": "000000"},
}


class BuildError(ValueError):
    pass


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _recolour_spans(spans: dict[str, dict], mapping: dict[str, str] | None) -> dict[str, dict]:
    """書式表の色を読み替える。傍線やフォントはそのまま、色だけ差し替える。"""
    out = dict(spans)
    if not mapping:
        return out
    for name, delta in list(rpr.SEMANTIC_SPANS.items()) + list(spans.items()):
        colour = delta.get("set", {}).get("color")
        if colour is None:
            continue
        new = mapping.get(ET.fromstring(colour).get(w("val")))
        if new:
            out[name] = {**delta, "set": {**delta["set"], "color": rpr.colour_fragment(new)}}
    return out


def build(data_path: Path, out_path: Path, answers: str | None = None) -> dict:
    payload = _load(data_path)
    if not payload:
        raise BuildError(f"教材データが読めません: {data_path}")
    mode = answers or payload.get("options", {}).get("answer_mode", "原本どおり")
    if mode not in ANSWER_MODES:
        raise BuildError(f"解答の見せ方は {'・'.join(ANSWER_MODES)} のどれかです（{mode}）")

    tdir = Path(payload.get("meta", {}).get("テンプレート", "template/授業プリント"))
    if not tdir.is_absolute():
        tdir = ROOT / tdir
    if not (tdir / "base.docx").exists():
        raise BuildError(f"テンプレートが見つかりません: {tdir}")
    formats = _load(tdir / "spans.json")
    table = _load(tdir / "regions.json")
    defaults = _load(tdir / "defaults.json")

    package = DocxPackage(tdir / "base.docx")
    root = package.parse_document()
    caps = volume.capacities(root)
    # 分量チェック用: プリントごとに「原本の行数」と「今回の行数」を数える
    amount: dict[str, list[int]] = {}
    local: dict[str, dict] = dict(formats.get("スロット別", {}))
    values: dict[str, str] = {}
    report = {"resized": [], "blank": []}

    if "slots" in payload:                       # スロット形式（原本の完全再現用）
        values = {s["id"]: s["text"] for s in payload["slots"]}
    else:                                        # 教材形式
        given = payload.get("sheets", {})
        known = {s["名前"] for s in table.get("sheets", [])}
        for name in given:
            if name not in known:
                raise BuildError(f"テンプレートに無いプリントです: 「{name}」"
                                 f"（使えるのは {'・'.join(known)}）")
        for sheet in table["sheets"]:
            data = material.expand_questions(given.get(sheet["名前"], {}), sheet["区画"])
            for key in data:
                if not key.startswith("_") and key not in sheet["区画"] and data[key]:
                    raise BuildError(f"{sheet['名前']}に「{key}」という区画はありません"
                                     f"（{'・'.join(sheet['区画'])}）")
            for region, ids in sheet["区画"].items():
                if region not in data:
                    if region in sheet["原本の文字を使う"]:
                        values.update({i: defaults.get(i, "") for i in ids})
                    else:
                        report["blank"].append(f"{sheet['名前']}・{region}")
                    continue
                if data[region] is None and region in sheet["削除可"]:
                    regionlib.delete(root, ids)   # 使わない設問を枠ごと取り除く
                    continue
                lines = material.lines_of(data[region])
                cap = min((caps[i] for i in ids if i in caps), default=None)
                if cap:
                    tally = amount.setdefault(sheet["名前"], [0, 0])
                    tally[0] += sum(volume.columns(defaults.get(i, ""), caps.get(i, cap)) for i in ids)
                    tally[1] += sum(volume.columns(line, cap) for line in lines)
                if len(lines) != len(ids):
                    try:
                        new = regionlib.resize(root, f"{sheet['名前']}・{region}", ids, len(lines))
                    except regionlib.RegionError:
                        if len(lines) > len(ids):
                            raise
                        new = ids
                        lines = lines + [""] * (len(ids) - len(lines))
                    inherited: dict = {}
                    for i in ids:
                        for k, v in local.get(i, {}).items():
                            inherited.setdefault(k, v)
                    for i in new:
                        local.setdefault(i, inherited)
                    report["resized"].append(f"{sheet['名前']}・{region} {len(ids)}→{len(lines)} 行")
                    ids = new
                values.update(zip(ids, lines))

    mapping = ANSWER_MODES[mode]
    spans = _recolour_spans({**formats.get("共通", {}), **payload.get("spans", {})}, mapping)
    local = {k: _recolour_spans(v, mapping) for k, v in local.items()}
    report["missing"] = slotlib.fill(root, values, spans, local, mapping)
    slotlib.recolour_opaque(root, mapping)
    package.set_document(root)
    package.save(out_path)
    report.update(mode=mode, amount=amount)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("data", help="教材データ（JSON）")
    parser.add_argument("-o", "--out", required=True, help="出力する docx")
    parser.add_argument("--answers", choices=list(ANSWER_MODES), help="解答の見せ方")
    args = parser.parse_args(argv)

    try:
        report = build(Path(args.data), Path(args.out), args.answers)
    except (BuildError, material.MaterialError, regionlib.RegionError,
            material.bunkai.BunkaiError) as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1

    print(f"→ {args.out}（解答: {report['mode']}）")
    for line in report["resized"]:
        print(f"  行数を変えた区画: {line}")
    if report["blank"]:
        print(f"  教材データに無いので空欄にした区画: {'、'.join(report['blank'])}")
    over = False
    for name, (before, after) in report["amount"].items():
        ratio = after / before * 100 if before else 0
        mark = "⚠ " if ratio > 100 else ""
        over |= ratio > 100
        print(f"  {mark}分量（{name}）: 原本 {before} 行分 → 今回 {after} 行分（{ratio:.0f}%）")
    if over:
        print("  原本より多い面があります。紙面からはみ出すおそれがあるので、行を減らすか"
              "短くしてください。最終確認は Word で。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
