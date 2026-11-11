# Kong バックエンド メモ

## パッケージ
- **パッケージ名**: `piano-transcription-inference`
- **バージョン**: 0.0.6
- **PyPI**: https://pypi.org/project/piano-transcription-inference/
- **論文**: Kong et al., "High-resolution Piano Transcription with Pedals by Regressing Onsets and Offsets Times" (2020)

## 重みファイル
- **ファイル名**: `CRNN_note_F1=0.9677_pedal_F1=0.9186.pth`
- **サイズ**: 171,966,578 バイト (~163.6 MB)
- **ソースURL**: https://zenodo.org/record/4034264
- **ダウンロードURL**: https://zenodo.org/record/4034264/files/CRNN_note_F1%3D0.9677_pedal_F1%3D0.9186.pth?download=1
- **SHA256**: `c3fa9730725bf4a762f1c14bc80cd5986eacda01b026f5a4a2525cd607876141`
- **ライセンス**: MIT License (パッケージのライセンスに準拠)
- **配置場所**: `${MT_MODELS_DIR:-<repo>/data/models}/kong/`

## 依存パッケージ
- torch==2.15.0
- piano-transcription-inference==0.0.6
- librosa==0.10.1
- numpy==1.24.4
- scipy==1.11.4
- soundfile==0.14.0
- mido==1.3.3
- matplotlib==3.10.9
- torchlibrosa==0.1.0
- audioread==3.1.0
- ffmpeg-python==0.2.0
- setuptools==79.0.1

## デバイス
- **使用デバイス**: MPS (Apple Silicon) - 実際に使用
- **動作確認**: MPSで推論実行を確認（内部で一部CPUを使用するメッセージあり）
- **優先順位**: MPS > CPU

## 実行環境
- Python: 3.11.13 (uv venv)
- 仮想環境: `backends/kong/.venv`
- モデル格納場所: `data/models/kong/` (ワークスペース外のシンボリックリンク経由)

## オーディオ処理
- **入力**: stereo 44.1 kHz WAV
- **変換**: soundfileで読み込み → 平均によりモノラル化 → scipy.signal.resampleで16 kHzにリサンプリング
- **形式**: float32 numpy array

## API
```python
from piano_transcription_inference import PianoTranscription, sample_rate

transcriptor = PianoTranscription(device='mps', checkpoint_path=checkpoint_path)
transcribed_dict = transcriptor.transcribe(audio, midi_path=None)
# transcribed_dict['est_note_events']: list of {midi_note, onset_time, offset_time, velocity}
# transcribed_dict['est_pedal_events']: list of {onset_time, offset_time}
```

## 評価結果 (実ピアノ音源: scarlatti_k525.wav)
- 正解ノート: 882
- 検出ノート: 860
- Onset-only (tolerance=0.05s): P=0.978, R=0.954, F1=0.966
- 推論時間: ~26秒 (MPS, MacBook Pro M1 Max)

## 実行方法
```bash
# セットアップ
bash backends/kong/setup.sh

# 実行
backends/kong/.venv/bin/python backends/kong/run.py input.wav output.json
```

## 既知の問題
- `librosa` 0.10.1 と `lazy_loader` 0.6 の互換性: `librosa.filters.get_window` が古いAPIを使用
- `setuptools<80` を使用して `pkg_resources` の互換性を確保
- Matplotlibのキャッシュディレクトリが書き込み不可のため、一時ディレクトリを使用

## 変更点 (Stage 2 fix)
- Python 3.11を使用（uv venv --python 3.11）
- モデルファイルを `data/models/kong/` に配置（MT_MODELS_DIR環境変数対応）
- SHA256チェックサムでモデルファイルを検証
- オーディオ読み込みをsoundfileで直接実施（モノラル化・16kHzリサンプリングを明示）
- MPSデバイスを優先使用（動作確認済み）
- 出力JSONにmetaフィールドを追加（device, package, version）
- 不要なファイル（backends/kong/models/）を削除
