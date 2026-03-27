#!/usr/bin/env bash

GITHUB="github.com/cilt-uct/docker-camera-dashboard.git"
USERS_FILE=/usr/local/serverconfig/users.cfg

SCRIPT_FOLDER=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_FOLDER

CURRENT_USER=$(logname)

# Python runner function - finds nearest venv and executes Python script/module
python_run() {
    set -euo pipefail

    if [ $# -lt 1 ]; then
        echo "Usage: python_run [-m module_name | script.py] [args...]" >&2
        return 1
    fi

    # --- Check if running a module ---
    local RUN_MODULE=false
    local MODULE_NAME=""
    local SCRIPT=""

    if [ "$1" = "-m" ]; then
        if [ $# -lt 2 ]; then
            echo "Error: -m requires a module name" >&2
            return 1
        fi
        RUN_MODULE=true
        MODULE_NAME="$2"
        shift 2
    else
        SCRIPT="$1"
        shift
    fi

    # --- Find nearest venv by walking upward ---
    local SEARCH_DIR=""
    local SCRIPT_PATH=""

    if [ "$RUN_MODULE" = true ]; then
        # Module can be anywhere, start from current directory
        SEARCH_DIR="$(pwd)"
    else
        # Normalize script path
        if [[ "$SCRIPT" = /* ]]; then
            SCRIPT_PATH="$SCRIPT"
        else
            SCRIPT_PATH="$(pwd)/$SCRIPT"
        fi

        if [ ! -f "$SCRIPT_PATH" ]; then
            echo "Error: script '$SCRIPT_PATH' not found" >&2
            return 1
        fi

        SEARCH_DIR="$(dirname "$SCRIPT_PATH")"
    fi

    local PYTHON_BIN=""

    while [ "$SEARCH_DIR" != "/" ]; do
        if [ -x "$SEARCH_DIR/.venv/bin/python" ]; then
            PYTHON_BIN="$SEARCH_DIR/.venv/bin/python"
            break
        elif [ -x "$SEARCH_DIR/venv/bin/python" ]; then
            PYTHON_BIN="$SEARCH_DIR/venv/bin/python"
            break
        fi
        SEARCH_DIR="$(dirname "$SEARCH_DIR")"
    done

    # Fallback to system Python if no venv found
    if [ -z "$PYTHON_BIN" ]; then
        PYTHON_BIN="$(command -v python3 || command -v python)"
    fi

    # --- Execute ---
    if [ "$RUN_MODULE" = true ]; then
        exec "$PYTHON_BIN" -m "$MODULE_NAME" "$@"
    else
        exec "$PYTHON_BIN" "$SCRIPT_PATH" "$@"
    fi
}

# Get the display name of the user
# params:
# $1 -- the section (if any)
# $2 -- the key
getCurrentUser() {

    section="git"
    key=$CURRENT_USER

    value=$(
        if [ -n "$section" ]; then
        sed -n "/^\[$section\]/, /^\[/p" $USERS_FILE
        else
        cat $USERS_FILE
        fi |

        egrep "^ *\b$key\b *=" |

        head -1 | cut -f2 -d'=' |
        sed 's/^[ "'']*//g' |
        sed 's/[ ",'']*$//g' )

    if [ -n "$value" ]; then
        echo $value
        return
    else
        echo 'NA'
        return
    fi
}

# Function to extract name from the string
get_name() {
    local input="$1"
    local name_pattern="^([^<]+)"
    [[ $input =~ $name_pattern ]] && echo "${BASH_REMATCH[1]}"
}

# Function to extract email from the string
get_email() {
    local input="$1"
    local email_pattern="<([^>]+)>"
    [[ $input =~ $email_pattern ]] && echo "${BASH_REMATCH[1]}"
}

# check to see if git exists
if git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    branch_name=$(git rev-parse --symbolic-full-name --abbrev-ref HEAD)
else
    echo "[ERR] Not inside a git repository."
    exit 0
fi

user="$(getCurrentUser)"

name=$(get_name "$user")
email=$(get_email "$user")

export GIT_COMMITTER_NAME="$name"
export GIT_COMMITTER_EMAIL="$email"
export GIT_AUTHOR_NAME="$name"
export GIT_AUTHOR_EMAIL="$email"
