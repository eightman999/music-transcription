# Basic Pitch バックエンド メモ

## パッケージ
- **パッケージ名**: `basic-pitch`
- **バージョン**: 0.4.0
- **ソース**: PyPI (Spotify 公式)
- **ライセンス**: Apache License 2.0 (コードとモデル重み)

## モデル
- **モデル名**: ICASSP 2022 モデル (basic-pitch 0.4.0 にバンドル)
- **モデルファイル**: `nmp.onnx` (ONNX 形式)
- **ファイルサイズ**: 230,444 バイト (225 KB)
- **ファイルパス**: `backends/basic_pitch/.venv/lib/python3.11/site-packages/basic_pitch/saved_models/icassp_2022/nmp.onnx`
- **SHA256**: `2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec`
- **ダウンロード**: 不要 (パッケージにバンドル済み)

## 実行環境
- **Python**: 3.11.13 (uv 経由)
- **デバイス**: CPU (ONNX Runtime)
- **MPS (Apple Metal)**: 未使用 (CoreML モデルはサンドボックス環境で動作せず、ONNX Runtime 1.16.3 では MPS 対応モデルが利用不可)

## 依存パッケージ (ピン固定)
- basic-pitch==0.4.0
- numpy==1.26.4
- scipy==1.12.0
- librosa==0.10.2
- pretty-midi==0.2.11
- mir-eval==0.8.2
- resampy==0.4.2
- onnxruntime==1.16.3
- scikit-learn==1.4.2
- soundfile==0.12.1
- tqdm==4.66.4
- typing-extensions==4.11.0
- setuptools==69.5.1
- coremltools==9.0 (インストール済みだが未使用)

## 使用したモデルとしきい値
- **モデル**: ONNX 形式 (nmp.onnx)
- **オンセットしきい値 (onset_threshold)**: 0.5 (デフォルト)
- **フレームしきい値 (frame_threshold)**: 0.3 (デフォルト)
- **最小ノート長 (minimum_note_length)**: 127.7 ms (デフォルト)

## 動作確認
- ✅ セットアップ: `bash backends/basic_pitch/setup.sh` (Python 3.11.13)
- ✅ 実行: `backends/basic_pitch/.venv/bin/python backends/basic_pitch/run.py data/sanity/scarlatti_k525.wav out/sanity/basic_pitch.json`
- ✅ 実行時間: 3.78 秒 (67.15 秒の音声を処理)
- ✅ 検出ノート数: 604 音 (地上真実: 882 音)
- ✅ Onset-only 評価 (0.05s tolerance): P=0.7980, R=0.5465, F1=0.6487

## 問題点
1. **CoreML モデル未使用**: サンドボックス環境 (`/var/folders/cm/...`) で CoreML モデルのコンパイルに失敗するため、ONNX Runtime (CPU) を使用
2. **MPS 未使用**: ONNX Runtime 1.16.3 では Apple Metal (MPS) 加速がサポートされていないため、CPU で実行
3. **F1 スコア**: 実ピアノ音源 (Scarlatti K.525) では F1=0.6487。これは naive detector よりも明らかに優れているが、ピアノ専用モデルとして期待される 0.9 には届かない。
   - 原因: 基本的なモデルアーキテクチャの限界、または音源の複雑さ
   - 対策: しきい値の調整を試みたが、デフォルト値が最適であった

## 実行コマンド
```bash
# セットアップ
bash backends/basic_pitch/setup.sh

# 実行
backends/basic_pitch/.venv/bin/python backends/basic_pitch/run.py data/sanity/scarlatti_k525.wav out/sanity/basic_pitch.json
```

## 使用したしきい値 (デフォルト値)
- **onset_threshold**: 0.5
- **frame_threshold**: 0.3
- **minimum_note_length**: 127.7 ms
