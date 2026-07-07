# 沙箱网络前置条件（重要）

本机处于中国网络 + Clash Verge 代理（fake-ip / TUN 模式，fake-ip 段 `198.18.0.0/15`）。
在该模式下，容器内对 **Ubuntu/Debian 官方 apt 镜像**（`ports.ubuntu.com`、`deb.debian.org`、
`archive.ubuntu.com`）的直连会被 fake-ip 路由并返回 **502 Bad Gateway**，导致 87 个任务里
**80 个**的 Docker 镜像构建（多为 `ubuntu:24.04` / `python:3.12-slim`）与部分 verifier 的
`apt-get` 失败。pypi / github / astral.sh / api.deepseek.com 则可正常经代理访问。

## 解决办法：让 Docker 走 Clash 的 HTTP 代理

Clash Verge 混合端口 = **7897**（见 `verge.yaml: verge_mixed_port`）。
在 `~/.docker/config.json` 增加 `proxies`，Docker 会把代理**同时注入到 `docker build`
（build-arg）与 `docker run`（容器 env）**，无需重启 Docker：

```json
{
  "proxies": {
    "default": {
      "httpProxy": "http://host.docker.internal:7897",
      "httpsProxy": "http://host.docker.internal:7897",
      "noProxy": "localhost,127.0.0.1,*.local,10.0.0.0/8,192.168.0.0/16,172.16.0.0/12"
    }
  }
}
```

原始 config 已备份到 `~/.docker/config.json.bak-preproxy`。

## 验证

```bash
docker run --rm ubuntu:24.04 sh -c 'apt-get update'          # 应成功 Fetched ...
docker build ...(FROM ubuntu:24.04; RUN apt-get update)      # 应成功
```

如果换机器 / 代理端口不同，改上面的 7897 即可；若不用代理（能直连 apt 镜像），可删掉
`proxies` 段还原。
