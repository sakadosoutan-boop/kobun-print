# CLAUDE.md

益田先生の古文プリント（A4横・縦書き）の組版を固定し、教材データ(JSON)を流し込んでプリント(docx)を作るテンプレート。詳細は README.md、二つの原本の突き合わせ結果は docs/突合レポート.md。

## 絶対ルール
- `template/*/base.docx` と `docs/原本_*.docx` は手で編集しない。テンプレートを変えるときは原本 docx から `tools/make_template.py` で作り直す。
- 組版（図形・枠・段組・縦書き設定）は原本の XML をそのまま使う。OOXML を自前で組み立てて置き換えない。
- 変更後は必ず `python3 tests/verify.py` を通す（原本・改訂版の可逆性、テンプレートからの完全再現、別教材の組み上げ、解答表示の切り替え）。
- 先生が「変えない」と言った面（例: あだし野の露 の表面）は、誤記を見つけても直さず報告する。
- 外部パッケージを増やさない（Python 標準ライブラリのみ）。
- 図形入りの run の判定は局所名で行う（`mc:AlternateContent` は w: 名前空間ではない）。

## 構成
- `src/kobunprint/` … docxpkg（入出力）/ rpr（書式差分）/ markup（記法）/ slots（抽出・流し込み）/ regions（区画の行数増減）/ volume（分量見積もり）/ bunkai（品詞分解）/ material（教材形式）
- `src/build.py` … 教材データ＋テンプレート → docx（分量チェック付き）
- `tools/` … make_template（原本→テンプレート）/ check（表記チェック）/ edit_adashino（改訂版の出どころ）

## 検証コマンド
| コマンド | 内容 |
|---|---|
| `python3 tests/verify.py` | 一式（LibreOffice と poppler があればページ画像を1ドット比較） |
| `python3 tools/check.py data/*.json` | 表記チェック |

LibreOffice のページ数は Word のページ割りの目安にならない（実フォントが無いため）。紙面に収まるかは build の「分量」で見る。

## コミット規約
`feat:` / `fix:` / `docs:` / `chore:` ＋日本語要約。
