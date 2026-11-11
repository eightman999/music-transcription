# 音声採譜プログラム Phase 1a: 検出部の比較と選定

## 概要

WAV音声を入力し、音符イベント (pitch/onset/offset/velocity) を検出するバックエンドの比較と評価を行います。

主指標: **onset-only F1** (onset_tolerance=0.05, offset_ratio=None)

## 環境

- macOS (Apple Silicon M2 Max)
- Python 3.11.13 (uv 経由)
- バックエンド: naive (組み込み), basic_pitch, kong, transkun (別 venv)

## セットアップ

### 共通依存

```bash
# 仮想環境を作成
uv python install 3.11
uv pip install numpy scipy soundfile mir_eval pretty_midi music21 pytest remotezip
```

### バックエンド別 venv

各バックエンドは別の venv で動作します。導入方法は `backends/` 参照。

## データセットの再構築

### 1. 合成テスト (synth)

```bash
# 合成テストクリップを生成 (16音)
.venv/bin/python scripts/make_test_wav.py

# 評価
.venv/bin/python scripts/eval_detect.py --dataset synth --backends naive
```

### 2. MAESTRO v3 test split (maestro_test5)

```bash
# データ取得 (5曲, 合計 ~24分)
.venv/bin/python scripts/fetch_maestro_subset.py --out _staging/maestro_test5

# 評価 (キャッシュ利用)
.venv/bin/python scripts/eval_detect.py --dataset _staging/maestro_test5 --backends naive,basic_pitch,kong,transkun
```

### 3. SMD (Saarland Music Data) (smd5)

```bash
# データ取得 (5曲, 分布外評価用)
.venv/bin/python scripts/fetch_smd_subset.py --out _staging/smd5 --cache data/_downloads/smd

# 評価
.venv/bin/python scripts/eval_detect.py --dataset _staging/smd5 --backends naive,basic_pitch,transkun
.venv/bin/python scripts/eval_detect.py --dataset _staging/smd5 --backends kong
```

### 4. MAESTRO 劣化版 (maestro_test5_degraded)

```bash
# 劣化版作成 (残響 + ピンクノイズ + MP3 96kbps)
.venv/bin/python scripts/make_degraded.py --input _staging/maestro_test5 --output _staging/maestro_test5_degraded

# 評価
.venv/bin/python scripts/eval_detect.py --dataset _staging/maestro_test5_degraded --backends naive,basic_pitch,transkun
.venv/bin/python scripts/eval_detect.py --dataset _staging/maestro_test5_degraded --backends kong
```

## サマリー生成

```bash
# 全データセットの結果からサマリーを生成
.venv/bin/python scripts/make_summary.py
```

出力: `results/phase1a_summary.md`

## 評価結果

詳細な結果は `results/detect_*.json` と `results/detect_*.md` を参照。

サマリー: `results/phase1a_summary.md`

## キャッシュ

- キャッシュディレクトリ: `out/detect/<dataset>/<backend>/`
- 各クリップの出力 JSON と実行メタデータ (SHA256, 実行時間, RSS) がキャッシュされます
- 同じ WAV ファイルの場合、キャッシュが再利用されます
- `--no-cache` フラグでキャッシュを無効化
- `--cache-dir` フラグでキャッシュディレクトリを指定 (デフォルト: `out/detect`)

## オフセットの基準 (2 通り)

1. **On+Off key (鍵を離した時刻)**: MIDI に記録された raw offset
2. **On+Off sustained (サステインペダルで延長した時刻)**: `mt.gt.sustain_extended()` によりペダル情報で延長

主指標は **onset-only** (onset のみ) です。

## テスト

```bash
# 全てのテストを実行
.venv/bin/python -m pytest -q
```

## ディレクトリ構造

```
music-transcription/
├── mt/
│   ├── schema.py      # JSONスキーマ
│   ├── gt.py          # Ground truth 変換
│   ├── evaluate.py    # 評価指標
│   └── backends.py    # バックエンドレジストリ
├── backends/
│   ├── naive/         # 素朴バックエンド
│   ├── basic_pitch/   # Basic Pitch
│   ├── kong/          # Kong et al.
│   └── transkun/      # Transkun
├── scripts/
│   ├── make_test_wav.py          # 合成テスト生成
│   ├── fetch_maestro_subset.py   # MAESTRO 取得
│   ├── fetch_smd_subset.py       # SMD 取得
│   ├── make_degraded.py           # 劣化版作成
│   ├── eval_detect.py             # 評価ハーネス
│   └── make_summary.py            # サマリー生成
├── tests/
│   ├── test_eval_detect.py        # 評価テスト
│   ├── test_smd.py                # SMD 選択ルールテスト
│   └── test_summary.py            # 決定ロジックテスト
├── _staging/          # データセット (開発用)
├── out/               # 生成物
│   └── detect/        # 評価キャッシュ
├── results/           # 評価結果
└── data/              # データ (シンボリックリンク)
```

## 注意事項

- `data/` は `/Users/eightman/dev/data/music-transcription` へのシンボリックリンク
- 開発中は `_staging/` を使用
- 本番実行時は `--out data/<set>` を使用
- WAV, MIDI, MP3 ファイルは Git にコミットしない (`git ls-files | grep -E '\.(wav|midi?|mp3)$'` が空であること)
- バックエンドの venv は Git にコミットしない

## 採用決定

PLAN.md 4.5 に基づく採用条件:
1. MAESTRO test split (b) と SMD (c) の onset F1 平均が素朴バックエンドを上回ること
2. 候補間の優劣は SMD を優先
3. 差が 1 ポイント未満なら軽い方 (RT factor) を採る
4. SMD が未測定の場合は「暫定採用」

詳細: `results/phase1a_summary.md` を参照
