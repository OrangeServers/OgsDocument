#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
    echo "Usage: $0 --version vX.Y.Z --output-dir DIR"
}

VERSION=""
OUTPUT_DIR=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --version)
            VERSION="${2:-}"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="${2:-}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "[FAIL] unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "[FAIL] --version must use stable SemVer, for example v1.2.3" >&2
    exit 2
fi
if [ -z "$OUTPUT_DIR" ]; then
    echo "[FAIL] --output-dir is required" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ARCHIVE="orangeserver-deploy-${VERSION}.tar.gz"
STAGE="$(mktemp -d)"
trap 'rm -rf -- "$STAGE"' EXIT

required=(
    ".env.example"
    "Makefile"
    "backend/.env.example"
    "backend/mysqldir/orange.sql"
    "deploy/docker-compose.yml"
    "deploy/docker-compose.host.yml"
    "deploy/nginx/frontend_container.conf"
    "deploy/nginx/ogs_proxy_common.conf"
    "frontend/dist/index.html"
    "ops/bootstrap-compose.sh"
    "ops/preflight-compose.sh"
)
for path in "${required[@]}"; do
    if [ ! -e "${ROOT}/${path}" ]; then
        echo "[FAIL] release bundle input missing: ${path}" >&2
        exit 1
    fi
done

while IFS= read -r asset; do
    asset="${asset#/}"
    if [ ! -f "${ROOT}/frontend/dist/${asset}" ]; then
        echo "[FAIL] frontend/dist/index.html references missing file: ${asset}" >&2
        exit 1
    fi
done < <(
    grep -oE '(src|href)="(/)?assets/[^"]+"' "${ROOT}/frontend/dist/index.html" \
        | sed -E 's/^(src|href)="//; s/"$//' \
        | sort -u
)

bundle_root="${STAGE}/orangeserver"
mkdir -p \
    "${bundle_root}/backend/mysqldir" \
    "${bundle_root}/deploy/nginx" \
    "${bundle_root}/frontend" \
    "${bundle_root}/ops"

cp "${ROOT}/.env.example" "${bundle_root}/"
cp "${ROOT}/Makefile" "${bundle_root}/"
cp "${ROOT}/backend/.env.example" "${bundle_root}/backend/"
cp "${ROOT}/backend/mysqldir/orange.sql" "${bundle_root}/backend/mysqldir/"
cp "${ROOT}/deploy/docker-compose.yml" "${bundle_root}/deploy/"
cp "${ROOT}/deploy/docker-compose.host.yml" "${bundle_root}/deploy/"
cp "${ROOT}/deploy/nginx/frontend_container.conf" "${bundle_root}/deploy/nginx/"
cp "${ROOT}/deploy/nginx/ogs_proxy_common.conf" "${bundle_root}/deploy/nginx/"
cp -a "${ROOT}/frontend/dist" "${bundle_root}/frontend/"
cp "${ROOT}/ops/preflight-compose.sh" "${bundle_root}/ops/"
cp "${ROOT}/ops/bootstrap-compose.sh" "${bundle_root}/ops/"

mkdir -p "$OUTPUT_DIR"
tar -C "$STAGE" -czf "${OUTPUT_DIR}/${ARCHIVE}" orangeserver
(
    cd "$OUTPUT_DIR"
    sha256sum "$ARCHIVE" > "${ARCHIVE}.sha256"
)
install -m 0755 \
    "${ROOT}/ops/bootstrap-compose.sh" \
    "${OUTPUT_DIR}/bootstrap-compose.sh"

echo "[OK] ${OUTPUT_DIR}/${ARCHIVE}"
echo "[OK] ${OUTPUT_DIR}/${ARCHIVE}.sha256"
echo "[OK] ${OUTPUT_DIR}/bootstrap-compose.sh"
