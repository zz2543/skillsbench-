#!/usr/bin/env bash
# Patch the base images SkillsBench tasks build FROM so their apt uses the aliyun
# HTTP mirror instead of ports.ubuntu.com / deb.debian.org.
#
# Why: on this host (China + Clash fake-ip/TUN), the official ubuntu/debian apt
# mirrors 502 through the proxy and TLS-break on the direct fake-ip route, but the
# aliyun mirror over plain HTTP works. HTTPS (pypi/github/uv/deepseek) already works
# via Clash's node routing, so no Docker proxy is used. We bake aliyun apt sources
# into a patched copy of each base image and retag it as the canonical tag; benchflow
# does not --pull, so `FROM ubuntu:24.04` then resolves to the patched image.
#
# Reversible: `docker pull ubuntu:24.04` (etc.) restores the upstream image.
set -euo pipefail

if [ "$#" -eq 0 ]; then set -- ubuntu:24.04 python:3.12-slim; fi

TMP="$(mktemp -d)"
cat > "$TMP/patch_apt.sh" <<'PATCH'
#!/bin/sh
set -e
for f in /etc/apt/sources.list.d/*.sources /etc/apt/sources.list; do
  [ -f "$f" ] || continue
  sed -i -E \
    -e 's#https?://ports.ubuntu.com/ubuntu-ports#http://mirrors.aliyun.com/ubuntu-ports#g' \
    -e 's#https?://(archive|security).ubuntu.com/ubuntu#http://mirrors.aliyun.com/ubuntu#g' \
    -e 's#https?://deb.debian.org/debian-security#http://mirrors.aliyun.com/debian-security#g' \
    -e 's#https?://deb.debian.org/debian#http://mirrors.aliyun.com/debian#g' \
    -e 's#https?://security.debian.org/debian-security#http://mirrors.aliyun.com/debian-security#g' \
    "$f" || true
done
apt-get update >/dev/null 2>&1 && echo PATCHED_APT_OK
PATCH

for img in "$@"; do
  echo "=== patching base image: $img ==="
  docker image inspect "$img" >/dev/null 2>&1 || docker pull "$img"
  if docker image inspect "$img" --format '{{ index .Config.Labels "lib-experiment.apt-mirror" }}' 2>/dev/null | grep -q aliyun; then
    echo "  already patched, skipping"; continue
  fi
  cat > "$TMP/Dockerfile" <<EOF
FROM $img
COPY patch_apt.sh /tmp/patch_apt.sh
RUN sh /tmp/patch_apt.sh && rm -f /tmp/patch_apt.sh
LABEL lib-experiment.apt-mirror=aliyun
EOF
  docker build --network default -t "$img" "$TMP"
  echo "  retagged patched -> $img"
done
rm -rf "$TMP"
echo "done."
