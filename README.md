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

---

# 作曲ハーネス (compose/)

採譜の逆向きパイプライン: メモ → スタイル固定 → DSL → **検証器** → 譜面/MIDI/動画/投稿パック。
正本は専用 DSL (YAML/JSON)。LLM に MusicXML を直接書かせず、DSL を出させて機械検証してから譜面化する。

## フロー

```bash
# 1. 入力メモ (固定形式1枚: 気分/刺さった一言/場面/NGワード)
.venv/bin/python -m compose.cli new <slug>
#   -> songs/<date>-<slug>/memo.md を記入

# 2. スタイル固定 (key/BPM/コード進行/音域/構成をプリセットから)
.venv/bin/python -m compose.cli styles               # 一覧
.venv/bin/python -m compose.cli styles --memo <song_dir>/memo.md  # 気分から推薦

# 3a. LLM に書かせる: 生成指示シートを出力して食わせる
.venv/bin/python -m compose.cli prompt <song_dir> [--style ballad]

# 3b. またはルールベースの骨組みを生成 (スモーク・叩き台用)
.venv/bin/python -m compose.cli draft <song_dir> [--style ballad] [--seed N]

# 4. 検証器 (肝): 拍数/音域/強拍-コード/1音節1音符 を機械チェック
.venv/bin/python -m compose.cli check <song_dir> [--fix]   # --fix で自動修正して保存

# 5. 譜面化: DSL -> notes.json / out.mid / out.musicxml / song.wav / song.meta.json
.venv/bin/python -m compose.cli build <song_dir>

# 6. 歌詞型 (サビ→Aメロの順、文字数と韻だけチェック)
.venv/bin/python -m compose.cli lyrics-init <song_dir>
.venv/bin/python -m compose.cli lyrics-check <song_dir>/lyrics.md [--range 4 16]

# 7. 動画化: 背景+波形+歌詞テロップを ffmpeg で自動合成 (編集ソフト不要)
.venv/bin/python -m compose.cli video <song_dir> [--bg image.png|loop.mp4]

# 8. 投稿パック + 台帳
.venv/bin/python -m compose.cli pack <song_dir>                      # title/description/tags/thumbnail
.venv/bin/python -m compose.cli post <song_dir> --url <URL>          # 投稿を記録
.venv/bin/python -m compose.cli stats <song_dir> --views N --retention P
.venv/bin/python -m compose.cli feedback                             # 次回への示唆
```

## DSL (正本)

`song.yaml` — 小節=コード+音符列 (音高・拍長・歌詞1音節):

```yaml
key: "C major"
bpm: 72
time: "4/4"
vocal_range: [55, 79]          # 歌える範囲 (MIDI)
sections:
  - {name: intro, bars: 2}
  - {name: sabi, bars: 8}
bars:
  - chord: "C"
    notes:
      - {pitch: "E4", len: 1.0, lyric: "き"}   # pitch: 音名 or MIDI値
      - {rest: true, len: 0.5}
      - {pitch: "G4", len: "1/2", lyric: "み"} # len: 拍数 (4分=1.0)
```

## 検証ルール (compose/validate.py)

| ルール | 内容 | --fix |
|---|---|---|
| BAR_LEN | 小節の len 合計 == 拍子 | 不足→休符追加 / 超過→末尾切詰 |
| RANGE | メロディが vocal_range 内 | ±12 移動 |
| STRONG_BEAT | 1・3拍目の音がコードトーン | 最近傍コードトーンへ |
| MORA | 1音符=1モーラ (「きょう」=3) | 音符を等分割 |
| BARS_COUNT | 小節数 == sections 合計 | - |
| SCALE | スケール外音 (半音は warn) | - |

歌詞が音符に紐付くので、テロップのタイミングは実際の音符 onset から自動計算される。

## 出力物 (songs/<date>-<slug>/)

| ファイル | 内容 |
|---|---|
| song.yaml / song.json | DSL 正本 |
| notes.json | 採譜スキーマの音符列 (mt/schema) |
| out.mid / out.musicxml | MIDI / MusicXML (MuseScore で開ける) |
| song.wav | 簡易シンセの試聴音源 |
| song.meta.json | bpm/key/セクション境界/音符数 |
| video.mp4 | 1080p テロップ動画 |
| pack/ | title/description/tags/thumbnail |

`songs/` と `ledger.jsonl` は gitignore。SynthV/NEUTRINO には out.mid + lyrics を手で流す。
譜面スクロール動画は MuseScore/LilyPond 導入後の拡張。
