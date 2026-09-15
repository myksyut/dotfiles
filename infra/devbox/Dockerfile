# Build context MUST be infra/devbox, never the repository or HOME.
# Supply immutable Ubuntu digest and locally reviewed official release artifacts.
ARG UBUNTU_IMAGE
FROM ${UBUNTU_IMAGE}
ARG NIX_SHA256
ARG ORCA_SHA256
ARG ORCA_VERSION
ARG TAILSCALE_SHA256
RUN test "$(dpkg --print-architecture)" = amd64 && apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl xz-utils bzip2 tar git python3 jq zsh \
    util-linux procps iproute2 nftables openssh-client restic \
    && groupadd --gid 10001 miyakishota \
    && useradd --no-create-home --uid 10001 --gid 10001 --home-dir /home/miyakishota --shell /bin/zsh miyakishota
RUN groupadd --gid 30000 nixbld \
    && for i in 1 2 3 4; do \
      useradd --no-create-home --uid "$((30000 + i))" --gid nixbld --groups nixbld \
        --home-dir /var/empty --shell /usr/sbin/nologin "nixbld$i"; \
    done
COPY artifacts/nix.tar.xz artifacts/orca.deb artifacts/tailscale.tgz /opt/artifacts/
RUN test -n "$NIX_SHA256" && test -n "$ORCA_SHA256" && test -n "$TAILSCALE_SHA256" && test -n "$ORCA_VERSION" \
    && printf '%s  %s\n' "$NIX_SHA256" /opt/artifacts/nix.tar.xz \
      "$ORCA_SHA256" /opt/artifacts/orca.deb "$TAILSCALE_SHA256" /opt/artifacts/tailscale.tgz | sha256sum -c - \
    && test "$(dpkg-deb -f /opt/artifacts/orca.deb Package)" = orca-ide \
    && test "$(dpkg-deb -f /opt/artifacts/orca.deb Architecture)" = amd64 \
    && test "$(dpkg-deb -f /opt/artifacts/orca.deb Version)" = "$ORCA_VERSION" \
    && apt-get install -y /opt/artifacts/orca.deb \
    && test "$(readlink -f /usr/bin/orca-ide)" = /opt/Orca/resources/bin/orca-ide \
    && test -x /usr/bin/orca-ide \
    && mkdir -p /opt/tailscale \
    && tar -xzf /opt/artifacts/tailscale.tgz -C /opt/tailscale --strip-components=1 \
    && mkdir -p /nix /home/miyakishota \
    && touch /etc/devbox-host \
    && dpkg-query -W > /opt/artifacts/dpkg-packages.txt
# Orca 1.4.197's deb omits ALSA, which its Electron Node-mode CLI still links.
# Refresh the inventory after installing this supplemental runtime dependency.
RUN apt-get update && apt-get install -y --no-install-recommends libasound2t64 \
    && dpkg-query -W > /opt/artifacts/dpkg-packages.txt
COPY entrypoint.sh bootstrap.sh bootstrap_state.py backup.sh firewall.nft /opt/devbox/
COPY nix/ /opt/devbox/nix/
COPY supervisor/ /opt/devbox/supervisor/
COPY orca/ /opt/devbox/orca/
COPY idle-controller/ /opt/devbox/idle-controller/
COPY orca-state-adapter/ /opt/devbox/orca-state-adapter/
COPY state-paths.json /opt/devbox/state-paths.json
RUN chmod 755 /opt/devbox/*.sh /opt/devbox/orca/*.sh \
    && mkdir -p /etc/nix /etc/devbox \
    && /usr/bin/python3 -I -c 'import sys; from pathlib import Path; sys.path.insert(0,"/opt/devbox"); from nix.provision import CONFIG, SEED_SHA256, validate_accounts; assert sys.argv[1] == SEED_SHA256; validate_accounts(); Path("/etc/nix/nix.conf").write_text(CONFIG)' "$NIX_SHA256" \
    && chmod 644 /etc/nix/nix.conf
ENV HOME=/root USER=root LOGNAME=root
# No EXPOSE, public services, SSH daemon, secrets, or Fly token.
ENTRYPOINT ["/opt/devbox/entrypoint.sh"]
