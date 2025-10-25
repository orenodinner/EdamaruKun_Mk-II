# Phosphobot SO-101 Python SDK & CLI（日本語訳）

## 概要

このリポジトリは、Phosphobot の HTTP API 経由で SO-101 ロボットアームを駆動するための、堅牢な Python 3.10+ クライアントSDKとコマンドラインインターフェイスを提供します。ロボティクスエンジニアの日常運用を想定し、**安全を最優先にしたデフォルト設定**、**可観測性（ログ等）**、そして **TypeScript/Node.js への最小摩擦での移植**を意識した構成になっています。

### 事前条件

* Phosphobot コントローラがローカルで起動し `http://localhost` で到達可能であること（`PHOSPHOBOT_BASE_URL` または CLI フラグで上書き可）。
* Python 3.10 以上。

## インストール

```bash
python -m venv .venv
. .venv/bin/activate  # Windows の場合: .venv\Scripts\activate
pip install -r requirements.txt
```

開発時の依存は `requests` のみに限定し、ロギング、リトライ、テストは標準ライブラリでカバーします。

## クイックスタート

### SDK 例

```bash
python examples/quick_start.py
```

このスクリプトはコントローラに接続し、安全のために `move_init()` を実行、その後にサンプルの `move_absolute()` コマンドを実行します:

```python
from phosphobot_client import PhosphobotClient

with PhosphobotClient() as client:
    client.move_init()
    client.move_absolute(25.0, 0.0, 15.0, 0.0, -30.0, 0.0, 50)
```

### CLI の使い方

```bash
# 初期姿勢へ移動（いかなる動作の前にも推奨）
python so101ctl.py init

# 絶対位置を指定して移動（単位: cm / deg / grip %）
python so101ctl.py move \
  --x 25 --y 0 --z 15 \
  --roll 0 --pitch -30 --yaw 0 \
  --grip 50

# フラグのみで init を実行（スクリプトで便利）
python so101ctl.py --init
```

`--verbose` でデバッグログを有効化、`--limits-file limits.json` で現場ごとの安全範囲（エンベロープ）を読み込めます。

## API

### モジュール `phosphobot_client.py`

* `PhosphobotClient(base_url=None, timeout_sec=5.0, max_retries=3, limits=None)`

  * `base_url` が省略された場合は `PHOSPHOBOT_BASE_URL` を自動検出。
  * タイムアウト、リトライ（指数バックオフ）、モーション制限に安全なデフォルトを提供。
  * コンテキストマネージャとして利用可能（HTTP リソースの確実な解放）。
* `move_init() -> dict`

  * `POST /move/init` を発行。ワークスペースでの操作前に必ず呼ぶこと。
* `move_absolute(x_cm, y_cm, z_cm, roll_deg, pitch_deg, yaw_deg, grip, *, limits=None) -> dict`

  * 単位（cm/deg/%）を検証し、非有限値を拒否、設定済み範囲をチェック。
  * 呼び出し毎に上書き可能な `MovementLimits` を任意指定可。
* 例外

  * `ValidationError`: クライアント側入力の不備。
  * `TimeoutError`: タイムアウトの再試行を使い果たした状態。
  * `HTTPError`: 2xx 以外の応答または輸送層エラー。
  * `ResponseDecodeError`: サーバのペイロードが不正で、点検やアップデートを促す状態。

### CLI `so101ctl.py`

* グローバルオプション: `--base-url`, `--timeout`, `--retries`, `--verbose`, `--limits-file`, `--init`。
* コマンド:

  * `init` - 安全な開始姿勢へ移動。
  * `move` - 単一の絶対姿勢を送信（全パラメータ必須）。
* 出力: 1行の人間向けサマリの後、コントローラからの JSON を整形表示。

## セーフティガイド

* アームの給電後やソフト再起動後は必ず `move_init()`（または `so101ctl.py init`）を実行する。
* 走行前にロボットのワークスペースをクリアに保ち、治具や人が範囲外であることを確認する。
* 制限値の確認: ツーリング変更時は特に、各軸・グリッパの安全範囲を記述したサイト固有の `limits.json` を読み込む。
* 非常停止の準備: ハードウェアの E-stop や電源遮断の位置を把握しておく。
* 想定外の応答は即時調査する—ログには位相ズレ、タイムアウト、不正入力の対処ヒントが含まれる。

## トラブルシューティング

* **接続拒否 / タイムアウト**: Phosphobot が起動しているか確認（`curl http://localhost/status`）。その後、`--timeout` を長くするかリトライ回数を増やして再実行。クライアントは再試行尽きた際にヒントを表示。
* **HTTP 4xx/5xx**: CLI が API エラーメッセージを表示。コントローラのログを確認し、根本原因を修正してから再試行。
* **検証エラー**: 単位（cm/deg/%）と設定した制限を確認。CLI は失敗した値をエコーし、`limits.json` 調整を支援。
* **不正な JSON**: API スキーマ変更に合わせてクライアントを更新、またはコントローラのファームウェア整合性を確認。

## 将来拡張

* クライアントに薄いラッパーを追加し、今後のエンドポイント（`/status`, `/torque_off`, `/record/start|stop`）に対応。CLI には新しいサブコマンドを配線。
* コード構造は Node.js 慣習（単一クライアントクラス、型付きの制限コンテナ、薄い CLI エントリ）を踏襲し、TypeScript への移植を容易にする。
* `so101ctl.py --plan` を拡張して JSON モーションプランをストリーム処理、あるいはトルクオフやロギング機能を新サブコマンドとして統合。

## テスト

以下のいずれかで自動テストを実行:

```bash
pytest -q
# または
python -m unittest
```

テストは `unittest.mock` により HTTP 層を分離しているため、実機ロボットは不要です。
