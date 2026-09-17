# Sourced at the start of each remote command. Not a convenience -- a necessity.
#
# `ssh host 'cmd'` starts a *new* non-interactive shell every time. ControlMaster
# multiplexes the TCP transport, not a shell session: there is no long-lived
# shell on the far side holding state, so a `module load` done by one command is
# gone by the next. Anything environmental has to be re-established per command.
#
# The alternative -- putting these lines in ~/.bashrc -- would apply them to
# every command anyone runs on CSF, including unrelated work, and module loads in
# .bashrc are a well-known source of confusing breakage. This file keeps the
# effect explicit and scoped.
#
# Usage:  ssh csf3 'source ~/selas-env.sh && <command>'

# CSF defines `module` for non-interactive ssh shells, but fall back if that
# ever changes rather than failing with "module: command not found".
if ! command -v module >/dev/null 2>&1; then
    for f in /etc/profile.d/modules.sh /usr/share/Modules/init/bash; do
        [ -r "$f" ] && . "$f" && break
    done
fi

module load apps/binapps/anaconda3/2024.10   # python 3.12.7; vllm is in its user site
module load libs/cuda/12.8.1                 # pinned: bare `libs/cuda` resolves to 11.6.2, pre-Hopper

export HF_HOME="$HOME/h200-scratch/hf"       # token and weight cache together, on the volume the H200 nodes mount
export SELAS_ENDPOINTS="$HOME/h200-scratch/endpoints"
export SELAS_MODEL="google/gemma-3-27b-it"
