# 绿联 NAS 自建 RustDesk：Docker、FRP 与 A/B 配置

本说明用于在 A 实时观看、人工操作 B 的 Windows/SOLIDWORKS 画面。
RustDesk 独立运行，现有 `remote-b-hub` 服务继续保留，无需停止或重新安装。
RustDesk 视频不会自动嵌入 `RemoteBClient.exe`，也不会自动让模型看见画面；
模型看图仍通过项目的截图、附件下载和本地图片读取工具完成。

## 部署前提与线路

- 绿联 NAS 可以运行 Docker，并能通过 SSH 登录执行命令。
- 已有 FRP 公网服务器，允许新增 TCP 21115/21116/21117 和 UDP 21116。
- 若使用第三方穿透，仅有 HTTPS 入口还不够，需要申请下表对应的 TCP/UDP 映射。
- 本说明使用现代 TOML 格式 `frpc.toml`；旧版 INI 配置不能直接粘贴 TOML。

```text
A / B RustDesk → 公网 FRP 服务器 → 绿联 NAS：hbbs + hbbr
```

这表示中继路径；客户端也可能直接连接。自建是否降低延迟取决于公网服务器线路、
NAS 上传带宽和 A/B 网络，部署后需要比较实际效果。保留自动直连，不强制走中继。
若 A/B 都在同一局域网，可先用 NAS 局域网地址验收，暂不经过 FRP。

下面以 NAS 局域网地址 `192.168.1.10` 为例，须替换为真实地址；
`YOUR_PUBLIC_IP` 须替换为 FRP 公网服务器 IP。客户端地址不加 `http://` 或 `https://`。

## 1. 在 NAS 创建 Compose 项目

在绿联应用中心安装并启动 Docker，启用 SSH，登录 NAS 后执行：

```bash
mkdir -p "$HOME/rustdesk/data"
cd "$HOME/rustdesk"
```

在该目录创建 `compose.yml`，将 `YOUR_PUBLIC_IP` 替换后保存：

```yaml
services:
  hbbs:
    image: rustdesk/rustdesk-server:latest
    container_name: remoteb-rustdesk-hbbs
    command: ["hbbs", "-r", "YOUR_PUBLIC_IP:21117", "-k", "_"]
    ports:
      - "21115:21115/tcp"
      - "21116:21116/tcp"
      - "21116:21116/udp"
    volumes:
      - ./data:/root
    restart: unless-stopped

  hbbr:
    image: rustdesk/rustdesk-server:latest
    container_name: remoteb-rustdesk-hbbr
    command: ["hbbr", "-k", "_"]
    ports:
      - "21117:21117/tcp"
    volumes:
      - ./data:/root
    restart: unless-stopped
```

`hbbs` 负责注册、连接协调，`hbbr` 负责中继。两者共用 `data` 的密钥；
显式 `-k _` 让中继也加载同一密钥进行校验。
参考 [官方 Compose 示例](https://github.com/rustdesk/rustdesk-server/blob/master/docker-compose.yml)
和 [官方密钥参数说明](https://github.com/rustdesk/rustdesk-server/blob/master/docs/environment-variables.md)。

先检查配置，再启动 `hbbs` 生成密钥：

```bash
sudo docker compose config
sudo docker compose up -d hbbs
sudo docker compose logs --tail=30 hbbs
```

等待几秒，确认启动没有报错，然后读取公钥并启动中继：

```bash
sudo cat data/id_ed25519.pub
sudo docker compose up -d hbbr
sudo docker compose ps
sudo docker compose logs --tail=30 hbbr
```

保存公钥的完整一行内容。客户端填写的是 `id_ed25519.pub`；
不要发送不带 `.pub` 的私钥，也不要把实际 `data` 目录上传 GitHub。
备份 `data`，更新或重建容器时保留此目录，避免客户端需要重新配置公钥。

如果提示 `docker compose` 不存在，先检查 NAS Docker 的 Compose 支持；
也可在 NAS Docker 的项目管理功能中导入此 YAML，挂载目录要对应实际项目目录。
容器反复重启时先查看日志；端口被占用、镜像拉取失败需先处理，不算部署成功。

## 2. 配置公网入口与 FRP

需要四条映射，公网端口保持下表数值：

| 协议 | 公网端口 | 转发到 NAS |
| --- | --- | --- |
| TCP | 21115 | NAS局域网IP:21115 |
| TCP | 21116 | NAS局域网IP:21116 |
| UDP | 21116 | NAS局域网IP:21116 |
| TCP | 21117 | NAS局域网IP:21117 |

原生 Windows 客户端本次无需开放 21118/21119 网页客户端端口，
也无需开放 Pro 的 21114。[官方端口说明](https://rustdesk.com/docs/en/self-host/rustdesk-server-oss/docker/)

在已有 `frpc.toml` 后追加下面内容。保留原来的 `serverAddr`、认证和其他项目代理，
将全部 `192.168.1.10` 替换为 NAS 真实局域网 IP：

```toml
[[proxies]]
name = "rustdesk-tcp-21115"
type = "tcp"
localIP = "192.168.1.10"
localPort = 21115
remotePort = 21115

[[proxies]]
name = "rustdesk-tcp-21116"
type = "tcp"
localIP = "192.168.1.10"
localPort = 21116
remotePort = 21116

[[proxies]]
name = "rustdesk-udp-21116"
type = "udp"
localIP = "192.168.1.10"
localPort = 21116
remotePort = 21116

[[proxies]]
name = "rustdesk-tcp-21117"
type = "tcp"
localIP = "192.168.1.10"
localPort = 21117
remotePort = 21117
```

`localIP` 必须是运行 frpc 的环境能够访问的 NAS 地址；frpc 在容器中时，
`127.0.0.1` 通常指 frpc 容器自身，因此这里使用 NAS 局域网 IP。
参考 [FRP 官方 TCP/UDP 配置](https://gofrp.org/zh-cn/docs/features/tcp-udp/)。

保存后重启既有 frpc 服务或容器，检查四条代理注册成功。
公网服务器的防火墙、安全组以及 frps 端口限制也需允许这四条映射，NAS 防火墙需允许 frpc 访问。
第三方 FRP 面板用户按上表新增映射；如果无法开放这些公网端口，先联系服务提供方。
NAS 当前 HTTPS 入口不会自动转发这些原生 TCP/UDP 连接。

## 3. 在 A、B 配置 RustDesk

两台电脑都进入 RustDesk「设置 → 网络 → ID/中继服务器」，解锁设置并填写：

| 项目 | 内容 |
| --- | --- |
| ID 服务器 | `公网服务器IP:21116` |
| 中继服务器 | `公网服务器IP:21117` |
| API 服务器 | 留空 |
| Key／密钥 | `data/id_ed25519.pub` 的完整公钥 |

这些值与 `remote-b-hub` 的 A/B Token 分开。
保存后重启两边 RustDesk，等待就绪，在 B 设置独立的永久访问密码，
再从 A 输入 B 当前显示的 ID 连接。[官方客户端配置](https://rustdesk.com/docs/en/self-host/client-configuration/)

若先做局域网验收，将 Compose 中 `-r` 的地址和 A/B 的服务器地址都改为 NAS 局域网 IP，
端口不变；改动后运行 `sudo docker compose up -d` 应用配置。
切换到外网使用时再改回公网入口。

## 4. 验收与延迟排查

在 A 的 PowerShell 执行，替换公网 IP：

```powershell
Test-NetConnection 公网IP -Port 21115
Test-NetConnection 公网IP -Port 21116
Test-NetConnection 公网IP -Port 21117
```

三项应返回 `TcpTestSucceeded : True`。这些命令只验证 TCP，
UDP 21116 另查 FRP 注册日志、端口规则及 RustDesk 的实际就绪状态。

- **容器运行但外网 TCP 不通**：检查公网安全组、防火墙、frps 端口限制、frpc 注册以及 NAS 地址。
- **密钥不匹配**：A/B 填写同一个 `.pub` 完整内容，hbbs/hbbr 保留同一份 `data`；不要通过删密钥来盲目重试。
- **未就绪/无法注册**：检查 21116 TCP/UDP 和 A/B 服务器地址，先对照 NAS 日志。
- **已连接但延迟明显**：查看直连/中继状态，比较桌面与 SolidWorks 的操作延迟；尝试速度优先、降低 B 分辨率，记录调整前后结果。

容器运行、端口通过、A/B 就绪、实际可连接和延迟改善是不同的验收项。
本仓库提供配置说明，没有代替用户在 NAS 上执行部署或保证线路性能。
