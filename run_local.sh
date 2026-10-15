#!/bin/sh
set -eu

usage() {
    cat <<'EOF'
Usage: ./run_local.sh [--port PORT]

Start this checkout of Gel Analyzer using its local .venv.
The default port is 8502; GEL_ANALYZER_PORT or --port can override it.

Options:
  --port PORT   Listen on this local port (1–65535).
  -h, --help    Show this help without starting the app.
EOF
}

gel_port=${GEL_ANALYZER_PORT:-8502}
while [ "$#" -gt 0 ]; do
    case "$1" in
        --port)
            if [ "$#" -lt 2 ]; then
                printf '%s\n' 'Missing port after --port.' >&2
                exit 2
            fi
            gel_port=$2
            shift 2
            ;;
        --port=*)
            gel_port=${1#--port=}
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown argument: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

case "$gel_port" in
    ''|*[!0-9]*)
        printf '%s\n' 'Port must be a number from 1 to 65535.' >&2
        exit 2
        ;;
esac
if [ "${#gel_port}" -gt 5 ] || [ "$gel_port" -lt 1 ] || [ "$gel_port" -gt 65535 ]; then
    printf '%s\n' 'Port must be a number from 1 to 65535.' >&2
    exit 2
fi

gel_project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
gel_python="$gel_project_dir/.venv/bin/python"
if [ ! -x "$gel_python" ]; then
    printf 'The local Python environment is missing. In %s, run:\n\n  uv sync --locked\n\nThen run this launcher again.\n' "$gel_project_dir" >&2
    exit 1
fi

cd "$gel_project_dir"
printf 'Starting Gel Analyzer from %s\nOpen http://127.0.0.1:%s\n' "$gel_project_dir" "$gel_port"
exec "$gel_python" -m streamlit run "$gel_project_dir/app.py" \
    --server.address=127.0.0.1 --server.port="$gel_port" --server.headless=true
