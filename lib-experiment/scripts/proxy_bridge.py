#!/usr/bin/env python3
"""Tiny 0.0.0.0 TCP forwarder: bridges Docker containers to a loopback-bound proxy.

Clash Verge's mixed proxy port (127.0.0.1:7897) is loopback-only, so containers
reaching it via host.docker.internal time out intermittently. This listens on
0.0.0.0:<listen> and forwards every connection to 127.0.0.1:<upstream>, giving the
Docker VM a reliably reachable proxy endpoint.

  python proxy_bridge.py            # 0.0.0.0:7898 -> 127.0.0.1:7897
  python proxy_bridge.py 7898 7897
"""
import socket
import sys
import threading

LISTEN = int(sys.argv[1]) if len(sys.argv) > 1 else 7898
UPSTREAM = int(sys.argv[2]) if len(sys.argv) > 2 else 7897


def pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def handle(client: socket.socket) -> None:
    try:
        upstream = socket.create_connection(("127.0.0.1", UPSTREAM), timeout=15)
    except OSError:
        client.close()
        return
    threading.Thread(target=pipe, args=(client, upstream), daemon=True).start()
    threading.Thread(target=pipe, args=(upstream, client), daemon=True).start()


def main() -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", LISTEN))
    srv.listen(128)
    print(f"proxy bridge: 0.0.0.0:{LISTEN} -> 127.0.0.1:{UPSTREAM}", flush=True)
    while True:
        client, _ = srv.accept()
        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        threading.Thread(target=handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
