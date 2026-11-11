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
- 選択された曲:
  - Sergei Rachmaninoff - 2004 - Etude-Tableaux, Opus 39 No. 8 in D Minor (190.85s)
  - Domenico Scarlatti - 2006 - Two Sonatas (373.61s)
  - Johann Sebastian Bach - 2008 - Prelude and Fugue in B-flat Minor, WTC II (360.53s)
  - Frédéric Chopin - 2009 - Nocturne in B Major, Op. 9, No. 3 (346.92s)
  - Franz Liszt - 2011 - Concert Etude No. 2, "Gnomenreigen", S. 145/2 (154.98s)
- 総時間: 23.8分
- 状態: ✅ 完了

### 3. SMD (Saarland Music Data) (smd5)
- 目的: 分布外評価
- 選択基準: sort by filename, composerごとに1曲, 90 <= duration <= 420s, 最大5曲
- 状態: ❌ 未測定
- 原因: Zenodoからの3.2GB zipファイルダウンロードがネットワーク制限により失敗

### 4. MAESTRO 劣化版 (maestro_test5_degraded)
- 目的: 頑健性評価
- 処理: 部屋リバーブ (aecho) + ピンクノイズ (30dB SNR) + MP3 96kbps 圧縮
- 時刻オフセット: 0.000s (クロス相関により確認)
- 状態: ✅ 完了

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
| naive | 1.0000 | 1.0000 | 0.5000 | 0.18x | 299.0 MB |

**メモ**: 素朴バックエンドは合成テストで 16/16 の完璧な検出を達成。Velocity は 0.500 だが、これは簡易的な速度マッピングのため。

### MAESTRO v3 test split (maestro_test5)
| Backend | Onset F1 | Onset+Offset F1 | Onset+Velocity F1 | RT Factor | Peak RSS |
|---------|----------|-----------------|-------------------|-----------|----------|
| naive | 0.2588 | 0.0316 | 0.1968 | 0.02x | 5591.2 MB |
| basic_pitch | 0.6766 | 0.1196 | 0.3726 | 0.03x | 646.9 MB |
| kong | 0.9716 | 0.2196 | 0.9558 | 0.39x | 2805.4 MB |
| transkun | 0.9875 | 0.2956 | 0.9828 | 0.10x | 948.9 MB |

**メモ**: kong (0.972) と transkun (0.988) は期待値 (0.97, 0.99) に近い結果を示した。basic_pitch (0.677) も期待値 (0.65) に近い。

### SMD (smd5)
| Backend | Onset F1 | Onset+Offset F1 | Onset+Velocity F1 | RT Factor | Peak RSS |
|---------|----------|-----------------|-------------------|-----------|----------|
| naive | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 |
| basic_pitch | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 |
| kong | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 |
| transkun | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 |

**状態**: 未測定 - Zenodoからのデータセットダウンロードがネットワーク制限により失敗

### MAESTRO 劣化版 (maestro_test5_degraded)
| Backend | Onset F1 | Onset+Offset F1 | Onset+Velocity F1 | RT Factor | Peak RSS |
|---------|----------|-----------------|-------------------|-----------|----------|
| naive | 0.2496 | 0.0308 | 0.1902 | 0.02x | 6038.8 MB |
| basic_pitch | 0.5838 | 0.0938 | 0.3228 | 0.03x | 651.4 MB |
| kong | 0.7703 | 0.1678 | 0.7298 | 0.38x | 2740.0 MB |
| transkun | 0.7773 | 0.1978 | 0.7708 | 0.10x | 949.0 MB |

**メモ**: 劣化処理により全バックエンドの性能が低下。kongとtranskunは依然として高い性能を維持 (0.77-0.78)。

## 採用決定 (PLAN.md 4.5)

### 基準
1. (b) MAESTRO test split と (c) SMD の onset F1 平均が素朴バックエンドを上回ること
2. 候補間の優劣は (c) SMD を優先する
3. 差が 1 ポイント未満なら軽い方を採る
4. (c) が未測定の場合は「暫定採用」

### 現状
- (b) MAESTRO test split: 
  - naive: 0.2588
  - basic_pitch: 0.6766 (> naive ✓)
  - kong: 0.9716 (> naive ✓)
  - transkun: 0.9875 (> naive ✓)
- (c) SMD: 未測定

### 決定
**暫定採用**: SMD (分布外データセット) が未測定のため、PLAN.md 4.5 に従い「暫定採用」とする。

## 失敗・未測定項目

### 失敗
- なし

### 未測定
1. **SMD (Saarland Music Data)**: 
   - 原因: Zenodoからの3.2GB zipファイルダウンロードがネットワーク制限により失敗
   - 試行した方法:
     - remotezipを使用した個別ファイル抽出 (タイムアウト)
     - curlを使用した全体ダウンロード (転送速度が極めて遅い: ~50 KB/s, 16時間以上かかる見込み)
     - requestsを使用したストリーミングダウンロード (タイムアウト)
   - 状態: 未測定

## 実行コマンド

### 合成テスト
```bash
.venv/bin/python scripts/eval_detect.py --dataset out/synth --backends naive
```

### MAESTRO test split
```bash
# データ取得
.venv/bin/python scripts/fetch_maestro_subset.py --out _staging/maestro_test5

# 評価
.venv/bin/python scripts/eval_detect.py --dataset _staging/maestro_test5 --backends naive,basic_pitch,kong,transkun
```

### SMD (未測定)
```bash
# データ取得 (失敗)
.venv/bin/python scripts/fetch_smd_subset.py --out _staging/smd5

# 評価 (未実行)
.venv/bin/python scripts/eval_detect.py --dataset _staging/smd5 --backends naive,basic_pitch,kong,transkun
```

### MAESTRO 劣化版
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
   - `basic_pitch`: 別 venv (backends/basic_pitch/.venv)
   - `kong`: 別 venv (backends/kong/.venv)
   - `transkun`: 別 venv (backends/transkun/.venv)

3. **修正内容**:
   - `scripts/fetch_maestro_subset.py`: manifestに `split` フィールドを追加
   - `backends/basic_pitch/run.py`: metaの `wall_time` を文字列に変換 (schema validation対応)
   - `scripts/make_degraded.py`: 
     - pink noise生成の `pn=1` を `color=pink` に修正 (ffmpeg 9.0.2対応)
     - 時刻オフセットチェックのステレオ対応
   - `scripts/fetch_smd_subset.py`: SMDデータセット取得スクリプト (未完了)

## 今後の作業

1. SMDデータセットを取得し評価を実行 (ネットワーク環境の改善が必要)
2. SMDの結果に基づき採用決定を最終化
