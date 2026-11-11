# 音声採譜プログラム (Music Transcription)

## 概要

WAV音声を入力し、楽譜 (MusicXML / PDF) と MIDI を自動生成するプログラムです。

## 環境

- macOS (Apple Silicon)
- Python 3.15 (システム既定)
- uv 経由で依存パッケージを管理

## セットアップ

```bash
# リポジトリをクローン
cd /Users/eightman/dev/tools/music-transcription

# 仮想環境を作成
python3 -m venv .venv

# 依存パッケージをインストール
.venv/bin/pip install numpy scipy soundfile mir_eval pretty_midi music21 pytest

# あるいは uv を使用
uv pip install numpy scipy soundfile mir_eval pretty_midi music21 pytest
```

## 使用方法

### 合成テストデータの生成

```bash
# 合成テストクリップを生成 (16音)
uv run python scripts/make_test_wav.py
```

### 検出バックエンドの実行

```bash
# 素朴バックエンドで検出
uv run python backends/naive/run.py out/synth/test.wav out/synth/test.naive.json
```

### 評価

```bash
# 合成データセットで評価
uv run python scripts/eval_detect.py --dataset synth --backends naive
```

### CLI 経由で採譜

```bash
# WAVを採譜してMIDIとMusicXMLを生成
uv run python -m mt.cli transcribe out/synth/test.wav --backend naive --bpm 120 -o out/transcribe
```

## テスト

```bash
# 全てのテストを実行
uv run pytest -q

# 詳細な出力
uv run pytest -v
```

## ディレクトリ構造

```
music-transcription/
├── mt/
│   ├── __init__.py
│   ├── schema.py      # JSONスキーマの定義と検証
│   ├── backends.py    # バックエンドレジストリと実行
│   ├── evaluate.py    # 評価指標 (mir_eval)
│   ├── score_naive.py # 固定BPMグリッド量子化、MIDI/MusicXML出力
│   └── cli.py         # CLI
├── backends/
│   └── naive/
│       └── run.py     # 素朴検出器
├── scripts/
│   ├── make_test_wav.py  # 合成テストクリップ生成
│   └── eval_detect.py     # 評価ハーネス
├── tests/
│   ├── test_schema.py     # スキーマテスト
│   ├── test_evaluate.py   # 評価テスト
│   └── test_synthetic.py  # 合成テスト
├── out/
│   └── synth/          # 生成されたテストデータ
├── results/            # 評価結果
├── pyproject.toml
├── .gitignore
└── README.md
```

## 実装状況

- [x] 素朴バックエンド (STFT + 倍音抑制 + 半音隣接抑制)
- [x] 合成テストデータ生成 (16音)
- [x] 評価ハーネス (mir_eval)
- [x] CLI (transcribe コマンド)
- [x] MusicXML 出力
- [x] テストスイート

## 注意事項

- 現行のプロトタイプ (`transcribe.py`, `make_test_wav.py`) はこのマシンには存在しません。
  この実装は PLAN.md の記述に基づいて再実装されたものです。
- 合成テストでは、素朴バックエンドで precision 1.0 と recall 1.0 (16/16) を目指しています。
  達成できない場合は、実測値を報告します。
