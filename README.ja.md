# ai-slack-bot

[English Readme](./README.md)

## 1. Overview

- AI Slack ボット
- [Slack Bolt](https://tools.slack.dev/bolt-python/ja-jp/)、[FastAPI](https://fastapi.tiangolo.com/ja/) を利用

## 2. 主な機能

- OpenAI、Azure OpenAI Service の API を利用した Slack ボット
  - 業務利用など特定ドメインの RAG 機能などを追加実装すると有用
- システムプロンプトの設定機能
- LLM に渡す会話履歴の最大数の設定機能
  - コンテキストが長くなるとモデルの性能が低下する場合に有用
- FastAPI、Uvicorn、Gunicorn による HTTP サーバー機能
  - 高負荷環境など実運用が可能

## 3. 使い方

1. Slack のサイトで Slack アプリを構成する
2. 環境変数を設定する
3. アプリを実行する
4. Slack アプリで Slack ボットにメンションして会話を開始する

### 3.1. Slack アプリの構成

[Slack](https://api.slack.com/lang/ja-jp) のサイトで Slack アプリを構成してください。 (参考: [Bolt 入門ガイド | Bolt for Python](https://tools.slack.dev/bolt-python/ja-jp/getting-started/))

以下のボットイベントを購読してください。

- message.channels
- message.groups
- message.im
- message.mpim
- app_mention

ボットトークンには以下のスコープが必要です。

- channels:history
- groups:history
- im:history
- mpim:history
- app_mentions:read
- chat:write
- reactions:write

アプリレベルトークンには以下のスコープが必要です。

- connections:write

### 3.2. 環境変数

環境変数の設定が必要です。

ローカル環境ではプロジェクトのルートに`.env`を作成して環境変数を設定してください。  
[.env.example](./.env.example) がテンプレートです。

以下の環境変数があります。

#### 3.2.1. 全般

- LOG_LEVEL
  - ログレベル (`DEBUG`, `INFO`, `WARNING`, `ERROR`)
- IS_DEVELOPMENT
  - 開発モードで実行するかどうか
- PORT
  - ポート番号
- LLM_INSTRUCTION_FILE_PATH
  - LLM への指示 (システムプロンプト) の設定ファイルのパス (e.g. `data/llm_instruction.txt`)
- LLM_MAX_MESSAGES
  - LLM に渡す会話履歴の最大数 (<0: 無制限)
  - より新しいメッセージを優先に最大数まで渡す
- LLM_INCLUDES_OTHER_BOT_MESSAGES
  - 他の Slack ボットのメッセージを LLM に渡すかどうか

#### 3.2.2. LLM 関連

- LLM_PROVIDER
  - LLM プロバイダ (`azure`, `openai`)
- LLM_NAME
  - LLM 名 (e.g. gpt-4.1-mini)
- LLM_DEPLOY_NAME
  - LLM デプロイ名 (e.g. gpt-4.1-mini-dev-001)
  - Azure: 要, OpenAI: 不
- LLM_ENDPOINT
  - LLM API の URL (e.g. Azure: `https://oai-foo-dev.openai.azure.com/`, OpenAI: `https://api.openai.com/`)
  - OpenAI で未指定の場合はデフォルトの `https://api.openai.com/` を使用
- LLM_API_KEY
  - LLM API のキー
- LLM_API_VER
  - LLM API のバージョン (e.g. 2025-01-01-preview)
  - Azure: 要, OpenAI: 不
- LLM_TEMPERATURE
  - LLM の温度 (生成する出力のランダム性、創造性) (0.0-1.0)

#### 3.2.3. Slack 関連

- SLACK_IS_SOCKET_MODE
  - ソケットモードで実行するかどうか
  - ローカルでの開発用途
- SLACK_APP_TOKEN
  - アプリレベルトークン
  - ソケットモードで必要
- SLACK_BOT_TOKEN
  - ボットトークン
- SLACK_SIGNING_SECRET
  - 署名シークレット
- SLACK_MAX_THREAD_MESSAGES
  - スレッド内の取得するメッセージの最大数
  - message イベントや app_mention イベントで受け取ったメッセージは除く、  
    より新しいメッセージを優先に最大数まで取得する
  - それとは別にスレッドの親メッセージは必ず含まれる
  - 結果的には「スレッドの親メッセージ + 取得したメッセージ + イベントで受け取ったメッセージ」

### 3.3. プログラムの実行

#### 3.3.1. ローカル環境での実行

```sh
poetry run python app/main.py
```

もしくは

```sh
.venv/Scripts/activate
python app/main.py
```

[Uvicorn](https://www.uvicorn.org/) のコマンドを利用する場合は、例えば以下のようにして実行できます。

```sh
.venv/Scripts/activate
uvicorn app.main:server_app --port 3000 --reload
```

#### 3.3.2. サーバー環境での実行

[Gunicorn](https://docs.gunicorn.org/en/latest/run.html) を利用して、例えば以下のようにして実行できます。

```sh
gunicorn "app.main:server_app" \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 4 \
  --log-level warning \
  --access-logfile - \
  --error-logfile -
```

## 4. リポジトリ

- [Bubbles877/ai-slack-bot](https://github.com/Bubbles877/ai-slack-bot)
