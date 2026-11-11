# transkun バックエンド

## パッケージ
- **パッケージ名**: `transkun`
- **バージョン**: 2.0.1
- **作者**: Yujia Yan
- **ライセンス**: MIT License (コードと重み)
- **PyPI**: https://pypi.org/project/transkun/
- **GitHub**: https://github.com/Yujia-Yan/Skipping-The-Frame-Level
- **Pythonバージョン**: 3.11.13

## 重みファイル
- **形式**: PyPIパッケージに同梱 (wheelファイル内)
- **ファイル名**: 2.0.pt (48.4 MB), 2.0.conf
- **保存場所**: バックエンドのvenv内 (`backends/transkun/.venv/lib/python3.11/site-packages/transkun/pretrained/`)
- **data/models/transkun/**: 未使用 (パッケージ内に重みが含まれているため)

## 依存パッケージ
主な依存 (requirements.lock を参照):
- torch==2.15.0
- torchaudio==2.11.1
- pretty-midi==0.2.11.post0
- transkun==2.0.1
- setuptools==79.0.1 (pkg_resources互換性のため)
- pydub==0.25.1
- soxr==1.1.0

## デバイス
- **使用デバイス**: MPS (Apple Silicon)
- **MPSサポート**: PyTorch 2.15.0 で利用可能
- **CPU**: 利用可能 (結果はMPSと同一)

## 実行方法
```bash
# セットアップ
bash backends/transkun/setup.sh

# 実行
backends/transkun/.venv/bin/python backends/transkun/run.py <in.wav> <out.json>
```

## 変換処理
1. transkun コマンドで WAV → MIDI 変換
2. pretty_midi で MIDI パース
3. 音符イベント (pitch, onset, offset, velocity) を抽出
4. サステインペダル (CC64) イベントを抽出
5. JSON スキーマに変換して出力

## 注意事項
- transkun はピアノ特化モデル
- 重みはパッケージ内に同梱されているため、別途ダウンロード不要
- MPS デバイスを使用する場合、PyTorch 2.x 以降が必要
- setuptools 79.0.1 を使用 (pkg_resources 互換性のため)
- pydub は WAV ファイルの読み込みに audioop モジュールを使用するが、Python 3.11 では利用可能

## 実測結果 (scarlatti_k525.wav)
- 検出音符: 862/882
- Onset-only P/R/F1: 1.0000 / 0.9773 / 0.9885
- 処理時間: ~37.9 秒 (67.15 秒のオーディオ)
- 実時間比: ~0.57x (MPS)
- デバイス: MPS (Apple Silicon)
- メタ情報: {"device": "mps", "package": "transkun", "version": "2.0.1"}

## 変更点
- Python 3.13 から 3.11 に変更 (audioop 互換性のため)
- patch_transcribe.py と eval_transkun.py を削除
- setup.sh を更新: Python 3.11 明示指定、setuptools<80 追加
- run.py を更新: pkg_resources ワークアラウンドを importlib_resources に置き換え、meta オブジェクト追加
- NOTES.md を実測結果に更新
