# ai-slack-bot

[日本語 Readme](./README.ja.md)

## 1. Overview

- AI Slack Bot
- Built with [Slack Bolt](https://tools.slack.dev/bolt-python/) and [FastAPI](https://fastapi.tiangolo.com/)

## 2. Key Features

- Slack bot using APIs from OpenAI and Azure OpenAI Service
  - Useful to implement additional features like RAG for specific domains, such as business use
- Feature to set the system prompt
- Feature to set the maximum number of conversation history entries to pass to the LLM
  - Useful when model performance degrades with longer contexts
- HTTP server functionality using FastAPI, Uvicorn, and Gunicorn
  - Enables practical operation in high-load environments

## 3. Usage

1. Configure the Slack app on the Slack website
2. Set up the required environment variables
3. Run the app
4. Mention the Slack bot in your Slack app to start a conversation

### 3.1. Slack App Configuration

Configure your Slack app on the [Slack](https://api.slack.com/) website. (Reference: [Getting Started | Bolt for Python](https://tools.slack.dev/bolt-python/getting-started/))

Subscribe to the following bot events:

- message.channels
- message.groups
- message.im
- message.mpim
- app_mention

The following scopes are required for the bot token:

- channels:history
- groups:history
- im:history
- mpim:history
- app_mentions:read
- chat:write
- reactions:write

The following scopes are required for the app-level token:

- connections:write

### 3.2. Environment Variables

Environment variables are required.

Create a `.env` file at the project root in your local environment and set the environment variables.  
[.env.example](./.env.example) is the template.

Available environment variables:

#### 3.2.1. General

- LOG_LEVEL
  - Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)
- IS_DEVELOPMENT
  - Whether to run in development mode (`True`, `False`)
- PORT
  - Port number
- LLM_INSTRUCTIONS_FILE_PATH
  - File path for the system prompt file used as instructions for the LLM (e.g. `data/llm_instructions.txt`)
- LLM_MAX_MESSAGES
  - Maximum number of messages to include in the conversation history passed to the LLM (<0: unlimited)
  - The most recent messages are prioritized up to the maximum count
- LLM_INCLUDES_OTHER_BOT_MESSAGES
  - Whether to pass messages from other Slack bots to the LLM
- REDIS_URL
  - Redis URL (e.g. `redis://localhost:6379/0`)

#### 3.2.2. LLM Related

- LLM_PROVIDER
  - LLM provider (`azure`, `openai`)
- LLM_NAME
  - LLM model name (e.g. gpt-4.1-mini)
- LLM_DEPLOY_NAME
  - LLM deployment name (e.g. gpt-4.1-mini-dev-001)
  - Required for Azure, not for OpenAI
- LLM_ENDPOINT
  - URL of the LLM API (e.g. Azure: `https://oai-foo-dev.openai.azure.com/`, OpenAI: `https://api.openai.com/`)
  - If not specified for OpenAI, the default `https://api.openai.com/` will be used
- LLM_API_KEY
  - LLM API key
- LLM_API_VER
  - LLM API version (e.g. 2025-01-01-preview)
  - Required for Azure, not for OpenAI
- LLM_TEMPERATURE
  - Diversity of LLM Outputs (0.0–1.0)

#### 3.2.3. Slack Related

- SLACK_IS_SOCKET_MODE
  - Whether to run in socket mode (`True`, `False`)
  - For local development purposes
- SLACK_APP_TOKEN
  - App-level token
  - Required for socket mode
- SLACK_BOT_TOKEN
  - Bot token
- SLACK_SIGNING_SECRET
  - Signing secret
- SLACK_MAX_THREAD_MESSAGES
  - Maximum number of messages to retrieve within a thread
  - Excludes message received via message event or app_mention event,  
    prioritizing the most recent messages up to the maximum count
  - The parent message of the thread is always included separately
  - The result is "parent message of the thread + retrieved messages + message received via event"

### 3.3. Running the App

#### 3.3.1. Running in a Local Environment

```sh
poetry run python app/main.py
```

Or

```sh
.venv/Scripts/activate
python app/main.py
```

If you want to use [Uvicorn](https://www.uvicorn.org/) commands, you can run it as follows, for example:

```sh
.venv/Scripts/activate
uvicorn app.main:server_app --port 3000 --reload
```

#### 3.3.2. Running in a Server Environment

Using [Gunicorn](https://docs.gunicorn.org/en/latest/run.html), you can run it as follows, for example:

```sh
gunicorn "app.main:server_app" \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 4 \
  --log-level warning \
  --access-logfile - \
  --error-logfile -
```

## 4. Dependencies & Verified Versions

Please see [pyproject.toml](./pyproject.toml).

We also use the following:

- [python-utilities/llm_chat at main · Bubbles877/python-utilities](https://github.com/Bubbles877/python-utilities/tree/main/llm_chat)
- [python-utilities/env_settings at main · Bubbles877/python-utilities](https://github.com/Bubbles877/python-utilities/tree/main/env_settings)

## 5. Repository

- [Bubbles877/ai-slack-bot](https://github.com/Bubbles877/ai-slack-bot)
