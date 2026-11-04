#!/usr/bin/env bash
# Moves the hot loop and the launch feed onto one small always-on Linux server, off GitHub Actions
# (whose terms allow Actions only to develop and test software). Paste it on the server, as a normal
# user with sudo, on Ubuntu or Debian. Run it twice: the first run makes a key for this repo and
# stops, and the second finishes. Safe to run again.
#
# Paper only. The key below can push to this one repo and nothing else: it is not a wallet, and it
# never leaves the server. Secrets go in ~/memepaper.env by hand, never in this file.
set -euo pipefail
REPO=git@github.com:Jackedwards7/memecoin-paper.git
CODE=$HOME/memecoin-paper
STATE=$HOME/memecoin-state
ENVF=$HOME/memepaper.env
KEY=$HOME/.ssh/memepaper

sudo apt-get update -qq
sudo apt-get install -y -qq git curl python3

# 1 GB of RAM is tight when the daily autopsy runs, so give it room.
if [ ! -f /swapfile ]; then
  sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
[ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N "" -C memepaper-server -f "$KEY"
export GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
if ! git ls-remote "$REPO" HEAD >/dev/null 2>&1; then
  echo
  echo "Add this key to the repo: Settings > Deploy keys > Add deploy key, tick 'Allow write access':"
  echo
  cat "$KEY.pub"
  echo
  echo "Then run this script again."
  exit 0
fi

[ -d "$CODE/.git" ] || git clone -q "$REPO" "$CODE"
git -C "$CODE" config core.sshCommand "$GIT_SSH_COMMAND"
git -C "$CODE" pull -q --ff-only
git -C "$CODE" fetch -q origin state
[ -d "$STATE" ] || git -C "$CODE" worktree add -q -B state "$STATE" origin/state
git -C "$STATE" config user.name "memepaper server"
git -C "$STATE" config user.email "memepaper@users.noreply.github.com"

if [ ! -f "$ENVF" ]; then
  cat > "$ENVF" <<EOF
MEMEPAPER_STATE=$STATE
MEMEPAPER_FEED=$HOME/memepaper-feed.sqlite
MEMEPAPER_BY=server
# Fill these in yourself, on this server only. The last two are optional.
NTFY_TOPIC=
DESK_TOKEN=
HEALTHCHECK_URL=
JUP_API_KEY=
EOF
  chmod 600 "$ENVF"
fi

# Two loops would be two writers on the books. Refuse while the GitHub one is still ticking.
git -C "$STATE" pull -q --rebase origin state
python3 -I - "$STATE/health.json" <<'PY'
import json, sys, time
h = json.load(open(sys.argv[1]))
if h.get("run") != "local" and time.time() - h.get("last_tick_ts", 0) < 900:
    sys.exit('The GitHub hot loop is still running. First run: gh workflow disable "hot loop" -R Jackedwards7/memecoin-paper\n'
             "then cancel its runs, wait 15 minutes, and run this script again.")
PY

unit() {  # name, description, command, extra lines
  sudo tee "/etc/systemd/system/$1.service" >/dev/null <<EOF
[Unit]
Description=$2
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$CODE
EnvironmentFile=$ENVF
$4
ExecStart=$3
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
}
# A day per run, and a pull before each, so merged code arrives by itself.
unit memepaper-loop "memepaper hot loop" "/usr/bin/python3 -I $CODE/memepaper.py loop --minutes 1440 --every 60" "ExecStartPre=-/usr/bin/git -C $CODE pull -q --ff-only"
unit memepaper-feed "memepaper launch feed" "/usr/bin/python3 -I $CODE/memepaper.py feed" ""
sudo systemctl daemon-reload
sudo systemctl enable --now memepaper-loop memepaper-feed
sleep 5
systemctl --no-pager --lines=0 status memepaper-loop memepaper-feed | grep -E 'Active:|●'
echo "Done. Logs: journalctl -u memepaper-loop -f"
