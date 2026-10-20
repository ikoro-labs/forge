#!/usr/bin/env bash
# Start the session that takes over from a handoff document, stop this one.
#
# At the context limit the session drains its agents, writes its handoff (handoff_trigger.py)
# and then calls this script from the project directory. The new session runs in the
# background, and the session that called the script is stopped and deleted once it has had
# time to give its last reply. A daily cap per project keeps a chain of relays from running
# unattended forever.
#
# Source: ikoro-labs/forge#3. Closing a session kills its subagents, so the relay refuses
# (exit 5) while an agent of the calling session is alive or the handoff header lists agents
# `en_vol`. --force is the hard cap of the drain: it is admitted only when the header lists
# the agents left for a rescue under `sauvetage`. Every check runs before the daily counter
# moves. The successor's drain threshold is set here and nowhere else: 400k when the handoff
# carries a feature, 150k otherwise, written in the header as `seuil`. It is always passed
# explicitly: the relay inherits the threshold of the session that runs it, which may be the
# 400k of an orchestration.
#
# State (the daily counters) lives in ~/.claude/hooks/state, outside the plugin cache.
#
# Usage: handoff_relay.sh [--force] <handoff document>
# Exit: 1 usage, 2 invalid header, 3 daily cap, 4 relay id unreadable, 5 agents alive.
# Environment: CLAUDE_HANDOFF_RELAY_MAX (default 5), CLAUDE_HANDOFF_CLOSE_DELAY seconds
# before closing the old session (default 45, 0 keeps it open), CLAUDE_HANDOFF_TERMINAL (a
# terminal command that runs the words after it, such as `ghostty -e` or `gnome-terminal --`:
# the relay opens `claude attach <id>` in it; unset, no window opens), and
# CLAUDE_HANDOFF_CLOSE_DRY_RUN (set: print the relay and closing commands instead of running
# them; the counter and the handoff are left untouched).
set -euo pipefail
force=""
if [ "${1:-}" = "--force" ]; then
    force=1
    shift
fi
handoff="${1:?usage: handoff_relay.sh [--force] <handoff document>}"
[ -f "$handoff" ] || { echo "handoff document not found: $handoff" >&2; exit 1; }
handoff="$(realpath "$handoff")"
hooks="$(dirname "$(realpath "$0")")"
header="$hooks/handoff_header.py"
dry_run="${CLAUDE_HANDOFF_CLOSE_DRY_RUN:-}"
max="${CLAUDE_HANDOFF_RELAY_MAX:-5}"
close_delay="${CLAUDE_HANDOFF_CLOSE_DELAY:-45}"
terminal="${CLAUDE_HANDOFF_TERMINAL:-}"
state="$HOME/.claude/hooks/state"
mkdir -p "$state"
project="$(pwd)"
counts="$(python3 "$header" check "$handoff")" || { echo "invalid handoff header: $counts" >&2; exit 2; }
en_vol="$(printf '%s' "$counts" | sed -n 's/^en_vol=\([0-9]*\) .*/\1/p')"
sauvetage="$(printf '%s' "$counts" | sed -n 's/.* sauvetage=\([0-9]*\) .*/\1/p')"
feature="$(printf '%s' "$counts" | sed -n 's/.* feature=\([0-9]*\)$/\1/p')"
threshold=150000
[ "$feature" -gt 0 ] && threshold=400000
# Only the agents of the calling session: another session's agents in the same
# repository do not die with this one. Run by hand, without CLAUDE_PID, every live
# agent of the repository counts, the prudent side.
live="$(python3 "$header" live "$project" ${CLAUDE_PID:+"$CLAUDE_PID"})" || {
    echo "could not list the agent worktrees: $live" >&2
    exit 5
}
if [ -n "$force" ]; then
    if [ "$sauvetage" -eq 0 ]; then
        echo "--force refused: the handoff lists no agent under sauvetage; wait for the agents instead" >&2
        exit 5
    fi
elif [ -n "$live" ] || [ "$en_vol" -gt 0 ]; then
    echo "relay refused: agents of this session are still in flight; let them finish, or at the hard cap list them under sauvetage and pass --force" >&2
    [ -n "$live" ] && printf 'live agent worktree: %s\n' "$live" >&2
    [ "$en_vol" -gt 0 ] && echo "en_vol in the header: $en_vol" >&2
    exit 5
fi
counter="$state/relay-$(printf '%s' "$project" | tr '/' '-')-$(date +%F).count"
count="$(cat "$counter" 2>/dev/null || echo 0)"
if [ "$count" -ge "$max" ]; then
    echo "relay cap reached: $count/$max relays today for $project; open the next session by hand" >&2
    exit 3
fi
count=$((count + 1))
prompt="Reprise automatique (relais $count/$max du jour). Avant tout geste, lance \`python3 $header successor-ok $handoff\` : s'il sort en code 3, une autre session est le successeur désigné, arrête-toi sans rien faire. Sinon, lis le document de passation $handoff, confronte son en-tête à GitHub, sauve d'abord chaque worktree listé sous sauvetage, puis poursuis la suite qu'il décrit, en respectant les règles du projet."
# The counter alone repeats across days and machines: the time keeps the name free.
name="relais-$count-$(basename "$project")-$(date +%H%M)"
if [ -n "$dry_run" ]; then
    echo "dry run, would run: CLAUDE_SESSION_TOKEN_LIMIT=$threshold claude --bg --permission-mode auto -n $name <prompt>"
    echo "dry run, prompt: $prompt"
    id="00000000"
else
    echo "$count" > "$counter"
    output="$(CLAUDE_SESSION_TOKEN_LIMIT="$threshold" claude --bg --permission-mode auto -n "$name" "$prompt" 2>&1)"
    echo "$output"
    id="$(printf '%s\n' "$output" | sed -n 's/.*backgrounded · \([0-9a-f]*\) ·.*/\1/p' | head -n 1)"
    [ -n "$id" ] || { echo "could not read the relay session id" >&2; exit 4; }
    python3 "$header" set-successor "$handoff" "$id" "$threshold"
    echo "successeur: $id and seuil: $threshold written in $handoff"
fi
# Only a desktop session can show a window; without one, or without a terminal named by
# the user, the relay is followed with `claude attach`.
if [ -n "$terminal" ] && [ -z "$dry_run" ] && [ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ]; then
    # shellcheck disable=SC2086 # the terminal command is split into its words on purpose
    setsid -f $terminal claude attach "$id" >/dev/null 2>&1 || true
    echo "relay $id opened in a new terminal window"
else
    echo "follow the relay with: claude attach $id"
fi
# CLAUDE_PID is the session that runs this script. The delay lets it finish its reply.
if [ "$close_delay" -gt 0 ] && [ -n "${CLAUDE_PID:-}" ]; then
    if [ "${CLAUDE_CODE_CHILD_SESSION:-}" = 1 ] && [ -n "${CLAUDE_CODE_SESSION_ID:-}" ]; then
        # A background session (a previous relay). A stopped session restarts on the next
        # message or `claude attach`, so it is deleted after the stop: only `claude rm` ends
        # everything it carries. Its viewers, `claude attach <id>` in their own windows,
        # fall back to the agent view and stay open, so they are ended first.
        short="${CLAUDE_CODE_SESSION_ID:0:8}"
        closer="pkill -TERM -f '^claude attach ${short}( |\$)'; claude stop $short || kill -TERM $CLAUDE_PID; claude rm $short"
    else
        # An interactive session. Its window closes only when the shell that started
        # claude exits, so that shell is hung up too, but only when the user's terminal
        # (CLAUDE_HANDOFF_TERMINAL) is its direct parent: a claude started from a script or
        # tmux keeps its parent.
        closer="kill -TERM $CLAUDE_PID"
        shell_pid="$(ps -o ppid= -p "$CLAUDE_PID" | tr -d ' ')"
        shell_name="$(ps -o comm= -p "$shell_pid" 2>/dev/null || true)"
        term_pid="$(ps -o ppid= -p "$shell_pid" 2>/dev/null | tr -d ' ')"
        term_name="$(ps -o comm= -p "$term_pid" 2>/dev/null || true)"
        # The kernel keeps 15 characters of a command name.
        term_command=""
        [ -n "$terminal" ] && term_command="$(basename "${terminal%% *}")"
        term_command="${term_command:0:15}"
        case "$shell_name" in
            bash|zsh|fish)
                if [ -n "$term_command" ] && [ "${term_name#"$term_command"}" != "$term_name" ]; then
                    closer="$closer; sleep 2; kill -HUP $shell_pid"
                fi ;;
        esac
    fi
    if [ -n "$dry_run" ]; then
        echo "dry run, would run in ${close_delay}s: $closer"
    else
        setsid -f bash -c "sleep $close_delay; $closer" >/dev/null 2>&1
        echo "this session (pid $CLAUDE_PID) closes in ${close_delay}s"
    fi
fi
