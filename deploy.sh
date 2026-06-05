#!/usr/bin/env bash
# deploy.sh — build and deploy invitio (Evite-style invitations app)
#
# LOCAL (Docker / Podman):
#   ./deploy.sh local up             — build + start (SQLite + HTTP on :8080)
#   ./deploy.sh local build          — build image only
#   ./deploy.sh local down           — stop containers
#   ./deploy.sh local logs           — tail logs
#   ./deploy.sh local clean          — remove containers, volumes, image
#
# NAS (remote Docker over SSH — Asustor reverse proxy terminates SSL):
#   ./deploy.sh nas deploy           — build locally, ship image + compose to NAS, start
#   ./deploy.sh nas up               — (re)start on NAS without rebuilding
#   ./deploy.sh nas down             — stop on NAS
#   ./deploy.sh nas logs             — tail NAS logs
#   ./deploy.sh nas shell            — shell into the NAS app container
#
# NAS connection (env vars):
#   export NAS_HOST=192.168.1.100
#   export NAS_USER=admin                          (default: current user)
#   export NAS_PATH=/volume1/docker/invitio        (default: ~/invitio)
#   export NAS_SSH_KEY=~/.ssh/id_rsa               (default: SSH agent / default key)
#   export NAS_SSH_PORT=22
#
# Example:
#   NAS_HOST=192.168.1.100 NAS_USER=admin ./deploy.sh nas deploy

set -euo pipefail
cd "$(dirname "$0")"

# ── colour helpers ────────────────────────────────────────────────────────────
RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'; CYAN=$'\033[0;36m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
info()    { echo -e "${CYAN}[deploy]${RESET} $*"; }
ok()      { echo -e "${GREEN}[deploy]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[deploy]${RESET} $*"; }
die()     { echo -e "${RED}[deploy] ERROR:${RESET} $*" >&2; exit 1; }
banner()  { echo -e "\n${BOLD}${BLUE}━━━ $* ━━━${RESET}\n"; }

# ── config ────────────────────────────────────────────────────────────────────
IMAGE_NAME="invitio"
IMAGE_TAG="latest"
IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

# Cache-busting build id baked into the image (git short-sha + build time). The
# backend stamps it into each page's ?v=, so every build invalidates the
# versioned css/js while plain container restarts of the same image don't. The
# timestamp also covers rebuilds of uncommitted changes.
build_version() {
    local sha; sha="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
    echo "${sha}-$(date +%s)"
}

NAS_HOST="${NAS_HOST:-}"
NAS_USER="${NAS_USER:-$(whoami)}"
NAS_PATH="${NAS_PATH:-invitio}"          # relative = home dir on NAS
NAS_SSH_KEY="${NAS_SSH_KEY:-}"
NAS_SSH_PORT="${NAS_SSH_PORT:-22}"
NAS_SSH_CTL="/tmp/.invitio-ssh-$$"       # ControlMaster socket — one password prompt per deploy

COMPOSE_LOCAL="docker-compose.yml"
COMPOSE_NAS="docker-compose.nas.yml"

# ── runtime detection ─────────────────────────────────────────────────────────
detect_runtime() {
    if command -v docker &>/dev/null; then echo "docker"
    elif command -v podman &>/dev/null; then echo "podman"
    else die "Neither docker nor podman found. Install one and retry."; fi
}

detect_compose() {
    local rt="$1"
    if [ "$rt" = "podman" ]; then
        if command -v podman-compose &>/dev/null; then echo "podman-compose"
        elif podman compose version &>/dev/null 2>&1; then echo "podman compose"
        else die "podman-compose not found. Install it: pip install podman-compose"; fi
    else
        if docker compose version &>/dev/null 2>&1; then echo "docker compose"
        elif command -v docker-compose &>/dev/null; then echo "docker-compose"
        else die "docker compose plugin not found."; fi
    fi
}

# ── SSH helpers ───────────────────────────────────────────────────────────────
require_nas_host() {
    [ -n "$NAS_HOST" ] || die "NAS_HOST is not set. Export it or pass NAS_HOST=<ip> before the command."
}

ssh_opts() {
    local opts="-p ${NAS_SSH_PORT} -o StrictHostKeyChecking=no -o ConnectTimeout=10"
    opts="$opts -o ControlMaster=auto -o ControlPath=${NAS_SSH_CTL} -o ControlPersist=120"
    [ -n "$NAS_SSH_KEY" ] && opts="$opts -i $NAS_SSH_KEY"
    echo "$opts"
}

nas_ssh_open()  { info "Connecting to ${NAS_HOST} …"; ssh $(ssh_opts) -o ControlMaster=yes -fN "${NAS_USER}@${NAS_HOST}"; }
nas_ssh_close() { ssh -O exit -o "ControlPath=${NAS_SSH_CTL}" "${NAS_USER}@${NAS_HOST}" 2>/dev/null || true; rm -f "${NAS_SSH_CTL}"; }

nas_ssh() {
    local tty_flag=""
    if [ "${1:-}" = "-t" ]; then tty_flag="-tt"; shift; fi
    ssh $(ssh_opts) $tty_flag "${NAS_USER}@${NAS_HOST}" "$@"
}

nas_scp() {
    local src="$1" dst="$2" key_opt=""
    [ -n "$NAS_SSH_KEY" ] && key_opt="-i $NAS_SSH_KEY"
    scp -P "${NAS_SSH_PORT}" -o StrictHostKeyChecking=no \
        -o ControlMaster=auto -o "ControlPath=${NAS_SSH_CTL}" -o ControlPersist=120 \
        ${key_opt} "$src" "${NAS_USER}@${NAS_HOST}:${dst}"
}

check_env() { [ -f .env ] || die ".env not found. Run: cp .env.example .env  then fill in your values."; }

# ══════════════════════════════════════════════════════════════════════════════
#  LOCAL
# ══════════════════════════════════════════════════════════════════════════════
local_build() {
    banner "Local build"
    local rt; rt=$(detect_runtime)
    local bv; bv=$(build_version)
    info "Runtime: $rt — building ${IMAGE} (BUILD_VERSION=${bv}) …"
    $rt build --build-arg BUILD_VERSION="$bv" -t "$IMAGE" .
    ok "Image built: ${IMAGE}"
}

local_up() {
    banner "Local up ($COMPOSE_LOCAL)"
    [ -f .env ] || { warn ".env not found — copying from .env.example"; cp .env.example .env; }
    local rt; rt=$(detect_runtime); local compose; compose=$(detect_compose "$rt")
    # Compose reads BUILD_VERSION from the environment (build.args in the file).
    BUILD_VERSION="$(build_version)"; export BUILD_VERSION
    info "Runtime: $rt  |  Compose: $compose  |  BUILD_VERSION=${BUILD_VERSION}"
    $compose -f "$COMPOSE_LOCAL" up --build -d
    echo ""; ok "invitio is up → http://localhost:8080"
    info "Logs: ./deploy.sh local logs   |   Stop: ./deploy.sh local down"
}

local_down() {
    banner "Local down"
    local rt; rt=$(detect_runtime); local compose; compose=$(detect_compose "$rt")
    $compose -f "$COMPOSE_LOCAL" down 2>/dev/null || true
    ok "Containers stopped."
}

local_logs() {
    local rt; rt=$(detect_runtime); local compose; compose=$(detect_compose "$rt")
    $compose -f "$COMPOSE_LOCAL" logs -f
}

local_clean() {
    banner "Local clean"
    local rt; rt=$(detect_runtime); local compose; compose=$(detect_compose "$rt")
    warn "This removes containers, volumes, and the local image."
    read -rp "Continue? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || { info "Aborted."; exit 0; }
    $compose -f "$COMPOSE_LOCAL" down -v 2>/dev/null || true
    $rt rmi "$IMAGE" 2>/dev/null && ok "Image removed." || warn "Image not found."
    ok "Clean complete."
}

# ══════════════════════════════════════════════════════════════════════════════
#  NAS
# ══════════════════════════════════════════════════════════════════════════════
nas_deploy() {
    banner "NAS deploy ($COMPOSE_NAS)"
    require_nas_host
    check_env

    nas_ssh_open
    trap nas_ssh_close EXIT

    local rt; rt=$(detect_runtime)
    local bv; bv=$(build_version)
    info "Building image ${IMAGE} locally (runtime: $rt, BUILD_VERSION=${bv}) …"
    $rt build --build-arg BUILD_VERSION="$bv" -t "$IMAGE" .

    local tarfile="/tmp/${IMAGE_NAME}.tar.gz"
    info "Exporting image → ${tarfile}"
    $rt save "$IMAGE" | gzip > "$tarfile"
    ok "Image exported ($(du -sh "$tarfile" | cut -f1))"

    info "Preparing remote path ${NAS_PATH} on ${NAS_HOST} …"
    nas_ssh "mkdir -p '${NAS_PATH}/nginx' '${NAS_PATH}/uploads' '${NAS_PATH}/postgres-data'"

    info "Transferring image to NAS …"
    nas_scp "$tarfile" "${NAS_PATH}/"

    info "Syncing compose + config …"
    nas_scp "$COMPOSE_NAS"          "${NAS_PATH}/docker-compose.yml"
    nas_scp ".env"                  "${NAS_PATH}/.env"
    nas_scp "nginx/nginx-nossl.conf" "${NAS_PATH}/nginx/nginx-nossl.conf"

    info "Loading image on NAS and starting containers …"
    nas_ssh -t "
        set -e
        cd '${NAS_PATH}'
        echo '[nas] Loading image …'
        sudo docker rmi localhost/${IMAGE} ${IMAGE} 2>/dev/null || true
        sudo docker load < ${IMAGE_NAME}.tar.gz
        sudo docker tag localhost/${IMAGE} ${IMAGE} 2>/dev/null || true
        echo '[nas] Restarting services …'
        sudo docker compose down 2>/dev/null || true
        sudo docker compose up -d --remove-orphans
        sudo docker compose ps
    "

    rm -f "$tarfile"
    nas_ssh_close
    trap - EXIT

    echo ""; ok "Deployed to NAS (${NAS_HOST})"
    ok "App → via Asustor reverse proxy → ${NAS_HOST}:18080"
    info "Logs: ./deploy.sh nas logs   |   Stop: ./deploy.sh nas down"
}

nas_up() {
    banner "NAS up"; require_nas_host; nas_ssh_open
    nas_ssh -t "cd '${NAS_PATH}' && sudo docker compose up -d --remove-orphans && sudo docker compose ps"
    nas_ssh_close; ok "Done."
}
nas_down() {
    banner "NAS down"; require_nas_host; nas_ssh_open
    nas_ssh -t "cd '${NAS_PATH}' && sudo docker compose down"
    nas_ssh_close; ok "Done."
}
nas_logs() {
    require_nas_host; nas_ssh_open
    info "Tailing logs on ${NAS_HOST} … (Ctrl-C to stop)"
    nas_ssh -t "cd '${NAS_PATH}' && sudo docker compose logs -f"
    nas_ssh_close
}
nas_shell() {
    require_nas_host; nas_ssh_open
    nas_ssh -t "cd '${NAS_PATH}' && sudo docker compose exec app /bin/sh"
    nas_ssh_close
}

# ══════════════════════════════════════════════════════════════════════════════
usage() {
    cat <<EOF
${BOLD}invitio — deploy.sh${RESET}

${BOLD}USAGE${RESET}
  ./deploy.sh <target> <command>

${BOLD}LOCAL (Docker / Podman)${RESET}
  ./deploy.sh local up        Build + start (SQLite, HTTP on :8080)
  ./deploy.sh local build     Build image only
  ./deploy.sh local down      Stop containers
  ./deploy.sh local logs      Tail logs
  ./deploy.sh local clean     Remove containers, volumes, image

${BOLD}NAS (remote Docker over SSH)${RESET}
  ./deploy.sh nas deploy      Build + ship to NAS, start behind Asustor reverse proxy
  ./deploy.sh nas up          (Re)start on NAS without rebuilding
  ./deploy.sh nas down        Stop containers on NAS
  ./deploy.sh nas logs        Tail NAS logs
  ./deploy.sh nas shell       Shell into the NAS app container

${BOLD}NAS CONFIGURATION${RESET}  (env vars)
  NAS_HOST      IP/hostname of your NAS      (required for nas commands)
  NAS_USER      SSH user                     (default: $(whoami))
  NAS_PATH      Remote deploy directory      (default: ~/invitio)
  NAS_SSH_KEY   Path to SSH private key      (default: SSH agent key)
  NAS_SSH_PORT  SSH port                     (default: 22)

${BOLD}EXAMPLES${RESET}
  ./deploy.sh local up
  NAS_HOST=192.168.1.100 ./deploy.sh nas deploy
EOF
}

# ── dispatch ──
TARGET="${1:-}"; COMMAND="${2:-}"
case "$TARGET" in
    local)
        case "$COMMAND" in
            build) local_build ;; up) local_up ;; down) local_down ;;
            logs) local_logs ;; clean) local_clean ;;
            *) die "Unknown local command: '$COMMAND'. Run ./deploy.sh for help." ;;
        esac ;;
    nas)
        case "$COMMAND" in
            deploy) nas_deploy ;; up) nas_up ;; down) nas_down ;;
            logs) nas_logs ;; shell) nas_shell ;;
            *) die "Unknown nas command: '$COMMAND'. Run ./deploy.sh for help." ;;
        esac ;;
    -h|--help|help|"") usage ;;
    *) die "Unknown target: '$TARGET'. Use 'local' or 'nas'." ;;
esac
