# Getting started

The fastest path is Docker Compose. Requirements: Docker Engine with Docker
Compose v2, Git, and Make.

```bash
git clone https://github.com/OrangeServers/OrangeServer.git
cd OrangeServer
cp .env.example .env
cp backend/.env.example backend/.env
```

Replace every `CHANGE_ME` value and set production secrets in both environment
files, then start the stack:

```bash
make docker-up
```

Open `http://<server>:8080` and sign in with `admin` / `admin`. Change this
initial password immediately.

::: tip First-run setup wizard
If required configuration (MySQL, secret key, Fernet keys) is missing at boot,
the backend serves a guided web setup at `/setup` instead of failing: it
validates connectivity, creates the schema and an administrator account, writes
the configuration, and restarts automatically.
:::

## Configure AI providers

Sign in as an administrator and open **System settings → AI providers**: pick a
preset (OpenAI, Anthropic, xAI, DeepSeek, MiniMax, Kimi, Qwen, GLM, or
SiliconFlow), fill in the model ID and API key, test tool calling, then save
and enable. Keys are Fernet-encrypted on the backend and never returned to the
browser.

## Upgrading

When upgrading an existing instance, do not just `git pull`. Back up first,
then run database migrations and verification in order following the
[upgrade procedure](https://github.com/OrangeServers/OrangeServer/blob/main/docs/operations/UPGRADE.md).

## Where to go next

- [Deployment options](/guide/deployment) — Compose, physical machine, systemd
- [AI operations](/guide/ai-ops) — what the assistant can and cannot do
- [Full documentation](https://github.com/OrangeServers/OrangeServer/tree/main/docs)
