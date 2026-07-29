# Deployment options

OrangeServer ships three verified deployment paths. All of them are covered by
the deployment audit and validated end-to-end against real environments.

## Docker Compose (recommended)

Four containers (nginx, frontend, backend, MySQL/Redis) started with one
command. This is the path described in [Getting started](/guide/getting-started).

For a new installation, run the version-pinned launcher from the stable
GitHub Release:

```bash
curl -fsSL \
  https://github.com/OrangeServers/OrangeServer/releases/download/v1.0.0/bootstrap-compose.sh \
  | sudo bash -s -- --version v1.0.0
```

The launcher downloads and verifies the matching deployment bundle, generates
the MySQL and Redis infrastructure passwords, and starts the published
`ghcr.io/orangeservers/orangeserver-backend:v1.0.0` image. Application
settings—including the administrator, SMTP, and AI providers—remain in the
browser-based `/setup` wizard. Review the launcher first if your environment
does not permit piping downloaded scripts to a shell.

For a source checkout or an existing installation, use the repository targets:

```bash
make docker-up        # bundled mode: everything in containers
make docker-up-host   # host mode: reuse an existing MySQL/Redis on the host
```

## Physical machine

Install MySQL, Redis, nginx, and the Python backend directly on the host. A
preflight script validates the environment before first start:

```bash
ops/preflight-physical-backend.sh
```

## systemd / supervisor

Run the backend under systemd or supervisor with the same gunicorn command the
containers use. Unit files and configuration layouts are documented in the
deployment manual.

## Reference

The full manual — environment variables, nginx configuration, health checks,
and troubleshooting — lives in
[DEPLOY.md](https://github.com/OrangeServers/OrangeServer/blob/main/DEPLOY.md).
For upgrades, always follow the
[upgrade procedure](https://github.com/OrangeServers/OrangeServer/blob/main/docs/operations/UPGRADE.md).
