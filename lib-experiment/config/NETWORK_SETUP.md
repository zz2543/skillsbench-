# 沙箱网络前置条件（重要）

本机处于中国网络 + Clash Verge 代理（fake-ip / TUN 模式，fake-ip 段 `198.18.0.0/15`，
混合端口 127.0.0.1:7897）。在该模式下 Docker 沙箱有三类问题，需要三处配合才能跑通
SkillsBench（Docker 构建 + OpenHands 自装 + verifier）：

| 目标 | 直连(fake-ip) | Clash 代理 | 采用方案 |
|---|---|---|---|
| ubuntu/debian **apt** 官方镜像 | 502 | 502(节点坏) | **aliyun HTTP 镜像**（基础镜像里改写 sources） |
| **astral.sh**（uv 安装脚本） | SSL_ERROR | 偶发失败 | **不用**：基础镜像预装 uv（pip+aliyun） |
| **github / pypi / api.deepseek.com**（HTTPS） | github 失败 | **可用** | **走 Clash 代理** |

## 三处配置

### 1. 代理桥（把 loopback-only 的 Clash 暴露给 Docker VM）
Clash 7897 仅绑 127.0.0.1，Docker 的 `host.docker.internal` 直连它不稳定。用
`scripts/proxy_bridge.py` 起一个 `0.0.0.0:7898 -> 127.0.0.1:7897` 转发：
```bash
python3 scripts/proxy_bridge.py 7898 7897 &   # 需在整个实验期间常驻
```

### 2. Docker 走代理，但 apt(aliyun) 直连
`~/.docker/config.json`（Docker 会把代理同时注入 build 与 run；`noProxy` 让
aliyun 走直连避免二次代理）：
```json
{ "proxies": { "default": {
  "httpProxy":  "http://host.docker.internal:7898",
  "httpsProxy": "http://host.docker.internal:7898",
  "noProxy": "localhost,127.0.0.1,mirrors.aliyun.com,*.local,10.0.0.0/8,192.168.0.0/16,172.16.0.0/12"
}}}
```
原始 config 备份在 `~/.docker/config.json.bak-preproxy`。

### 3. 基础镜像打补丁（apt→aliyun + 预装 uv）
`scripts/setup_base_images.sh ubuntu:24.04 python:3.12-slim` 会：把 apt 源改成
aliyun HTTP、预装 uv（pip+aliyun）、设 `UV_DEFAULT_INDEX`/`PIP_INDEX_URL` 到
aliyun，然后**用原 tag 回填**。benchflow 不 `--pull`，故 `FROM ubuntu:24.04`
即用补丁镜像；OpenHands 自装因 uv 已在而跳过 astral.sh，github 经代理、依赖走
aliyun，稳定成功。

## 验证
```bash
# apt(aliyun) + uv 预装
docker run --rm ubuntu:24.04 sh -c 'apt-get update && uv --version'
# 官方 oracle 冒烟应 reward=1
uv run bench eval run --tasks-dir experiments/sanity-tasks/hello-world --agent oracle --sandbox docker
```

换机器/端口不同时改 7897/7898 与镜像 tag 即可；能直连 apt 镜像则可省去补丁与代理。
