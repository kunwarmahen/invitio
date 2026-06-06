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
# `nas deploy` asks whether to bundle a NEW postgres container or reuse an
# EXISTING postgres instance, then deploys only the containers that mode needs
# (app + nginx + db, or app + nginx pointed at your existing DB).
#
# NAS connection (env vars):
#   export NAS_HOST=192.168.1.100
#   export NAS_USER=admin                          (default: current user)
#   export NAS_PATH=/volume1/docker/invitio        (default: ~/invitio)
#   export NAS_SSH_KEY=~/.ssh/id_rsa               (default: SSH agent / default key)
#   export NAS_SSH_PORT=22
#   export NAS_HTTP_PORT=18081                      (nginx host port; default 18080 —
#                                                    change if another app's nginx has it)
#
# Database choice (env vars — set to skip the interactive prompt):
#   export NAS_DB_MODE=new                         (bundle a fresh postgres; default)
#   export NAS_DB_MODE=existing                    (reuse an existing postgres, then:)
#     export NAS_DB_HOST=db-container-or-ip        (required)
#     export NAS_DB_PORT=5432                      (default 5432)
#     export NAS_DB_NAME=invitio                   (default invitio)
#     export NAS_DB_USER=invitio                   (default invitio)
#     export NAS_DB_PASSWORD=...                   (required)
#     export NAS_DB_NETWORK=shared-net             (only if the DB is a container on
#                                                   a shared Docker network)
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

# Database choice for `nas deploy`. Leave NAS_DB_MODE unset to be prompted, or set
# it to skip the prompt in scripted runs:
#   NAS_DB_MODE=new        bundle a fresh postgres container (default)
#   NAS_DB_MODE=existing   reuse an existing postgres; supply the rest below
#     NAS_DB_HOST      DB host — container/service name or IP   (required)
#     NAS_DB_PORT      DB port                                  (default 5432)
#     NAS_DB_NAME      database name                            (default invitio)
#     NAS_DB_USER      username                                 (default invitio)
#     NAS_DB_PASSWORD  password                                 (required)
#     NAS_DB_NETWORK   shared Docker network the DB container is on, so the app
#                      can reach it by name (blank if DB is reachable by IP/host)
NAS_DB_MODE="${NAS_DB_MODE:-}"

COMPOSE_LOCAL="docker-compose.yml"
COMPOSE_NAS="docker-compose.nas.yml"               # bundled postgres
COMPOSE_NAS_EXTDB="docker-compose.nas-extdb.yml"   # reuse external postgres (app + nginx)
COMPOSE_NAS_EXTDB_NET="docker-compose.nas-extdb-net.yml"  # override: join shared DB network

# Set by gather_db_choice / gather_external_db before a nas deploy.
DB_MODE=""
EXT_DB_URL=""
EXT_DB_NETWORK=""

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

# ── database choice (nas deploy) ───────────────────────────────────────────────
# Ask whether to bundle a fresh postgres or reuse an existing one, then gather the
# connection details for the "existing" case. Honours the NAS_DB_* env vars so the
# whole thing can run unattended. Sets DB_MODE / EXT_DB_URL / EXT_DB_NETWORK.
gather_db_choice() {
    case "$NAS_DB_MODE" in
        new|existing) DB_MODE="$NAS_DB_MODE" ;;
        "")
            echo ""
            info "PostgreSQL for this deployment:"
            echo "  1) Create a NEW postgres container   (bundled with the app — default)"
            echo "  2) Reuse an EXISTING postgres instance"
            local ans; read -rp "Choose [1/2] (default 1): " ans
            case "${ans:-1}" in
                1) DB_MODE="new" ;;
                2) DB_MODE="existing" ;;
                *) die "Invalid choice: '$ans'. Pick 1 or 2." ;;
            esac ;;
        *) die "NAS_DB_MODE must be 'new' or 'existing' (got '$NAS_DB_MODE')." ;;
    esac

    if [ "$DB_MODE" = "new" ]; then
        ok "Database: bundled postgres container (${COMPOSE_NAS})."
        return
    fi

    # ── existing instance: collect connection details ──
    ok "Database: reusing an existing postgres instance (${COMPOSE_NAS_EXTDB})."
    local host="${NAS_DB_HOST:-}" port="${NAS_DB_PORT:-5432}"
    local name="${NAS_DB_NAME:-invitio}" user="${NAS_DB_USER:-invitio}"
    local pass="${NAS_DB_PASSWORD:-}" net="${NAS_DB_NETWORK:-}" ans
    if [ -z "$host" ]; then read -rp "  Postgres host (DB container/service name or IP): " host; fi
    [ -n "$host" ] || die "A postgres host is required to reuse an existing instance."
    if [ -z "${NAS_DB_PORT:-}" ];     then read -rp "  Port [5432]: " ans;          port="${ans:-5432}";   fi
    if [ -z "${NAS_DB_NAME:-}" ];     then read -rp "  Database name [invitio]: " ans; name="${ans:-invitio}"; fi
    if [ -z "${NAS_DB_USER:-}" ];     then read -rp "  Username [invitio]: " ans;    user="${ans:-invitio}"; fi
    if [ -z "$pass" ];                then read -rsp "  Password: " pass; echo; fi
    [ -n "$pass" ] || die "A postgres password is required."
    if [ -z "${NAS_DB_NETWORK:-}" ]; then
        read -rp "  Shared Docker network the DB is on (blank if reachable by IP/host): " net
    fi
    case "$pass" in
        *[:@/]*) warn "Password contains a ':', '@' or '/' — embedded raw in DATABASE_URL; URL-encode it in .env if the app can't connect." ;;
    esac
    EXT_DB_URL="postgresql+asyncpg://${user}:${pass}@${host}:${port}/${name}"
    EXT_DB_NETWORK="$net"
    info "DATABASE_URL → postgresql+asyncpg://${user}:***@${host}:${port}/${name}"
    [ -n "$net" ] && info "App will join shared Docker network: ${net}"
}

# write_env_override SRC OUT KEY=VAL [KEY=VAL...] — copy SRC to OUT, replacing (or
# appending) each KEY's line. Used to inject the external DATABASE_URL into the
# shipped .env without touching the developer's local .env.
write_env_override() {
    local src="$1" out="$2"; shift 2
    cp "$src" "$out"
    local pair key
    for pair in "$@"; do
        key="${pair%%=*}"
        grep -vE "^[[:space:]]*${key}=" "$out" > "${out}.t" 2>/dev/null || true
        mv "${out}.t" "$out"
        printf '%s\n' "$pair" >> "$out"
    done
}

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
    banner "NAS deploy"
    require_nas_host
    check_env

    # Ask (or read NAS_DB_* env) which postgres to use, and collect details. Done
    # before the SSH connection so prompts aren't tangled with connection output.
    gather_db_choice

    local compose_file="$COMPOSE_NAS"
    [ "$DB_MODE" = "existing" ] && compose_file="$COMPOSE_NAS_EXTDB"

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
    if [ "$DB_MODE" = "new" ]; then
        nas_ssh "mkdir -p '${NAS_PATH}/nginx' '${NAS_PATH}/uploads' '${NAS_PATH}/postgres-data'"
    else
        nas_ssh "mkdir -p '${NAS_PATH}/nginx' '${NAS_PATH}/uploads'"
    fi

    info "Transferring image to NAS …"
    nas_scp "$tarfile" "${NAS_PATH}/"

    info "Syncing compose + config (db mode: ${DB_MODE}) …"
    nas_scp "$compose_file"          "${NAS_PATH}/docker-compose.yml"
    nas_scp "nginx/nginx-nossl.conf" "${NAS_PATH}/nginx/nginx-nossl.conf"

    # Build the .env to ship: start from the local .env and override only what
    # this deploy needs, so the developer's local file is never clobbered.
    local -a env_overrides=()
    if [ "$DB_MODE" = "existing" ]; then
        env_overrides+=(
            "DATABASE_PROVIDER=postgres"
            "DATABASE_URL=${EXT_DB_URL}"
            "NAS_DB_NETWORK=${EXT_DB_NETWORK}"   # for the override's ${NAS_DB_NETWORK} substitution
        )
    fi
    # nginx host port — override when 18080 collides with another app's nginx.
    [ -n "${NAS_HTTP_PORT:-}" ] && env_overrides+=("INVITIO_HTTP_PORT=${NAS_HTTP_PORT}")

    if [ ${#env_overrides[@]} -gt 0 ]; then
        local tmpenv; tmpenv="$(mktemp)"
        write_env_override .env "$tmpenv" "${env_overrides[@]}"
        nas_scp "$tmpenv" "${NAS_PATH}/.env"
        rm -f "$tmpenv"
    else
        nas_scp ".env" "${NAS_PATH}/.env"
    fi

    # Network override: only when reusing a DB on a shared Docker network.
    if [ "$DB_MODE" = "existing" ] && [ -n "$EXT_DB_NETWORK" ]; then
        nas_scp "$COMPOSE_NAS_EXTDB_NET" "${NAS_PATH}/docker-compose.override.yml"
    else
        # Drop any override left from a previous external-db deploy.
        nas_ssh "rm -f '${NAS_PATH}/docker-compose.override.yml'"
    fi

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

    local http_port="${NAS_HTTP_PORT:-18080}"
    echo ""; ok "Deployed to NAS (${NAS_HOST})"
    if [ "$DB_MODE" = "existing" ]; then
        ok "Database: existing postgres instance (no db container deployed)"
    else
        ok "Database: bundled postgres container (data in ${NAS_PATH}/postgres-data)"
    fi
    ok "nginx listening on 127.0.0.1:${http_port} — point the Asustor reverse proxy rule here"
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
                              (asks: bundle a new postgres, or reuse an existing one)
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
  NAS_HTTP_PORT nginx host port on the NAS   (default: 18080; change on a clash)

${BOLD}DATABASE${RESET}  (env vars — set to skip the deploy-time prompt)
  NAS_DB_MODE   new | existing               (default: prompt; 'new' = bundled postgres)
  NAS_DB_HOST   existing DB host / container  (required when NAS_DB_MODE=existing)
  NAS_DB_PORT   existing DB port             (default: 5432)
  NAS_DB_NAME   existing database name       (default: invitio)
  NAS_DB_USER   existing DB user             (default: invitio)
  NAS_DB_PASSWORD  existing DB password      (required when NAS_DB_MODE=existing)
  NAS_DB_NETWORK   shared Docker network the DB container is on (optional)

${BOLD}EXAMPLES${RESET}
  ./deploy.sh local up
  NAS_HOST=192.168.1.100 ./deploy.sh nas deploy
  # unattended, reuse an existing postgres container on a shared network:
  NAS_HOST=192.168.1.100 NAS_DB_MODE=existing NAS_DB_HOST=pg \\
    NAS_DB_PASSWORD=secret NAS_DB_NETWORK=db-net ./deploy.sh nas deploy
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
