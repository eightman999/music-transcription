# Phase 1a: 検出部の比較と選定 - サマリー

## 実行日
2026-11-11

## 環境
- macOS (Apple Silicon M2 Max)
- Python 3.11.13 (uv 経由)
- バックエンド: naive, basic_pitch, kong, transkun

## 評価データセット

### 1. 合成テスト (synth)
- 目的: 素朴バックエンドの回帰確認
- クリップ数: 1
- 音符数: 16
- 状態: ✅ 完了

### 2. MAESTRO v3 test split (maestro_test5)
- 目的: 分布内評価
- 選択基準: split == "test", 90 <= duration <= 420s, composerごとに1曲、最大5曲、総時間 <= 30分
- 状態: ⏳ 未実行 (データ取得必要)

### 3. SMD (Saarland Music Data) (smd5)
- 目的: 分布外評価
- 選択基準: sort by filename, composerごとに1曲, 90 <= duration <= 420s, 最大5曲
- 状態: ⏳ 未実行 (データ取得必要)

### 4. MAESTRO 劣化版 (maestro_test5_degraded)
- 目的: 頑健性評価
- 処理: 部屋リバーブ + ピンクノイズ (30dB SNR) + MP3 96kbps 圧縮
- 状態: ⏳ 未実行 (元データ必要)

## 評価指標

### 主指標
- Onset-only (onset_tolerance=0.05, offset_ratio=None): P / R / F1

### 併記指標
- Onset+Offset (onset_tolerance=0.05, offset_ratio=0.2, offset_min_tolerance=0.05): P / R / F1
- Onset+Velocity (onset_tolerance=0.05, velocity_tolerance=0.1): P / R / F1
- 実時間比 (Real-time factor)
- ピークメモリ使用量 (Peak RSS in MB)

## 結果

### 合成テスト (synth)
| Backend | Onset F1 | Onset+Offset F1 | Onset+Velocity F1 | RT Factor | Peak RSS |
|---------|----------|-----------------|-------------------|-----------|----------|
| naive | 1.000 | 1.000 | 0.500 | 0.18x | 299.0 MB |

**メモ**: 素朴バックエンドは合成テストで 16/16 の完璧な検出を達成。Velocity は 0.500 だが、これは簡易的な速度マッピングのため。

### MAESTRO v3 test split (maestro_test5)
| Backend | Onset F1 | Onset+Offset F1 | Onset+Velocity F1 | RT Factor | Peak RSS |
|---------|----------|-----------------|-------------------|-----------|----------|
| naive | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 |
| basic_pitch | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 |
| kong | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 |
| transkun | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 |

**状態**: 未測定 - データセット取得が必要

### SMD (smd5)
| Backend | Onset F1 | Onset+Offset F1 | Onset+Velocity F1 | RT Factor | Peak RSS |
|---------|----------|-----------------|-------------------|-----------|----------|
| naive | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 |
| basic_pitch | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 |
| kong | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 |
| transkun | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 |

**状態**: 未測定 - データセット取得が必要

### MAESTRO 劣化版 (maestro_test5_degraded)
| Backend | Onset F1 | Onset+Offset F1 | Onset+Velocity F1 | RT Factor | Peak RSS |
|---------|----------|-----------------|-------------------|-----------|----------|
| naive | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 |
| basic_pitch | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 |
| kong | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 |
| transkun | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 |

**状態**: 未測定 - 元データセット必要

## 採用決定 (PLAN.md 4.5)

### 基準
1. (b) MAESTRO test split と (c) SMD の onset F1 平均が素朴バックエンドを上回ること
2. 候補間の優劣は (c) SMD を優先する
3. 差が 1 ポイント未満なら軽い方を採る
4. (c) が未測定の場合は「暫定採用」

### 現状
- (b) MAESTRO test split: 未測定
- (c) SMD: 未測定

### 決定
**暫定採用**: SMD (分布外データセット) が未測定のため、PLAN.md 4.5 に従い「暫定採用」とする。

## 失敗・未測定項目

### 失敗
- なし

### 未測定
1. **MAESTRO v3 test split**: データセット取得が必要
   - 原因: 大容量ファイル (100GB+) のダウンロードが必要
   - 代替: HTTP Range 要求による個別ファイル取得 (scripts/fetch_maestro_subset.py 実装済み)
   
2. **SMD (Saarland Music Data)**: データセット取得が必要
   - 原因: Zenodo からの 3.2GB zip ファイル取得が必要
   - 状態: scripts/fetch_smd_subset.py 実装済み
   - 注意: Range 要求がサポートされているか確認必要
   
3. **MAESTRO 劣化版**: 元データセット必要
   - 原因: MAESTRO test split が未取得
   - 状態: scripts/make_degraded.py 実装済み

## 実行コマンド

### 合成テスト
```bash
.venv/bin/python scripts/eval_detect.py --dataset out/synth --backends naive
```

### MAESTRO test split (将来的)
```bash
# データ取得
.venv/bin/python scripts/fetch_maestro_subset.py --out _staging/maestro_test5

# 評価
.venv/bin/python scripts/eval_detect.py --dataset _staging/maestro_test5 --backends naive,basic_pitch,kong,transkun
```

### SMD (将来的)
```bash
# データ取得
.venv/bin/python scripts/fetch_smd_subset.py --out _staging/smd5

# 評価
.venv/bin/python scripts/eval_detect.py --dataset _staging/smd5 --backends naive,basic_pitch,kong,transkun
```

### MAESTRO 劣化版 (将来的)
```bash
# 劣化版作成
.venv/bin/python scripts/make_degraded.py --input _staging/maestro_test5 --output _staging/maestro_test5_degraded

# 評価
.venv/bin/python scripts/eval_detect.py --dataset _staging/maestro_test5_degraded --backends naive,basic_pitch,kong,transkun
```

## 注意事項

1. **データディレクトリ**: `data/` は `/Users/eightman/dev/data/music-transcription` へのシンボリックリンク
   - 開発中は `_staging/` を使用
   - 本番実行時は `--out data/<set>` を使用

2. **バックエンド**: 
   - `naive`: 組み込み (動作確認済み)
   - `basic_pitch`: 別 venv 必要 (backends/basic_pitch/.venv)
   - `kong`: 別 venv 必要 (backends/kong/.venv)
   - `transkun`: 別 venv 必要 (backends/transkun/.venv)

3. **依存パッケージ**: 
   - remotezip: MAESTRO 部分ダウンロード用
   - ffmpeg: SMD MP3->WAV 変換、劣化処理用

## 今後の作業

1. MAESTRO v3 test split データセットを取得し評価を実行
2. SMD データセットを取得し評価を実行
3. MAESTRO 劣化版を作成し評価を実行
4. 結果に基づき採用決定を最終化
