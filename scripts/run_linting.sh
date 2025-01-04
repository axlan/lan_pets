#!/usr/bin/env bash

set -e

# Find the directory of this file, following symlinks.
#
# Reference:
# - https://stackoverflow.com/questions/59895/how-to-get-the-source-directory-of-a-bash-script-from-within-the-script-itself
get_parent_dir() {
    local SOURCE="${BASH_SOURCE[0]}"
    while [ -h "$SOURCE" ]; do
        local DIR="$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )"
        SOURCE="$(readlink "$SOURCE")"
        [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
    done

    local PARENT_DIR="$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )"
    echo "${PARENT_DIR}"
}

REPO_ROOT=$(get_parent_dir)/..

python -m autopep8 -i -j 0 --recursive $REPO_ROOT --exclude '.env*,.venv*,env*,venv*,ENV,.idea'
python -m isort $REPO_ROOT --sg '.env*' --sg '.venv*' --sg 'env*' --sg 'venv*' --sg 'ENV' --sg '.idea'
