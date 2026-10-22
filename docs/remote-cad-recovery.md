# A 端启动 SW 和安全解除 CAD 暂停

新增 3 个 MCP 工具（总数 21 个），A 桌面增加“CAD 管理”窗口。

| 工具 | 行为 |
| --- | --- |
| `computer_b_cad_state()` | 无 COM 调用地读取暂停 ID、上次调用进程 PID、是否仍运行、可否恢复；CAD 暂停时仍可用 |
| `computer_b_start_solidworks()` | 显式启动/连接 B 当前登录会话的 SW；即使自动启动开关关闭也可请求，复用已有进程 |
| `computer_b_resume_cad(pause_id, acknowledge_state)` | 按刚读取的暂停 ID，确认旧调用进程已退出后恢复；保留审计记录，不重复失败任务 |

所有工具均返回任务 ID，需用 `computer_b_job` 查询真实结果。它们通过原 A/B Token 鉴权和同一 B worker 顺序执行，不增加端口或隧道。

## 恢复步骤

1. 读取原失败任务和可用截图，理解失败操作是否可能仍在执行。
2. 调用 `computer_b_cad_state` 并查询任务。如果 `helper_running=true`，等待或检查 B 的界面；不能强制解锁、不能提交同一脚本重试。
3. `can_resume=true` 仅表示旧进程退出，不代表模型已正确。结合用户当前授权和现场证据，使用本次 `pause_id`，明确传入 `acknowledge_state=true` 调用恢复工具。B 仍需启用原有的可信 A 脚本开关。
4. 查询恢复任务成功后，读取 `computer_b_sw_session`；SW 未运行时用显式启动工具。重新核对活动文档后再进行不同的修正操作。

不再要求每次去 B 本地停止代理并点击解除。A 已获授权时可以完成检查与恢复；不必为了同一恢复流程反复请求许可。若旧进程还活着、PID 缺失、进程检查失败、暂停 ID 已改变，恢复请求会拒绝。不要绕过这些检查删除锁文件。

## 启动行为

B 代理必须在线，离线时 A 无法通过未运行的代理启动服务。启动不关闭 SW、不丢弃文档、不强杀进程；已暂停时先走恢复流程。

SW COM 检查在独立进程进行。若 COM 阻塞或启动超时，父 worker 能回传错误并保留 CAD 暂停及调用 PID，而非无限卡在 COM 接口。后续仍可读取 `cad_state`。启动等待使用 B 的 `sw_start_timeout`（10–300 秒），额外预留 20 秒给进程收尾。

## 部署

更新 NAS 源码并运行 `scripts/install-debian12.sh`，`/health.capabilities` 应包含 `cad_control`。更新 A 的 MCP 仓库并重新加载连接，再替换 B EXE。旧 B/NAS 不支持这些新操作。

`/opt/remote-b-hub` 是部署目录，通常不是 Git 仓库；找不到源码目录时，root 可运行：

```bash
update_dir=$(mktemp -d /root/remote-b-hub-update.XXXXXX)
git clone --depth 1 https://github.com/zuiaishenzi/remote-b-hub.git "$update_dir" &&
bash "$update_dir/scripts/install-debian12.sh" &&
curl --fail http://127.0.0.1:18765/health
```

原 Token、模板、输出目录及可信脚本开关保持原配置。A GUI 的“CAD 管理”支持读取暂停 ID、启动 SW、确认并提交恢复，结果显示在主窗口。

测试覆盖鉴权、拒绝旧 ID、拒绝活进程/未知状态、审计保留、隔离启动超时、真实本地进程保护和 frozen 协议。B 实机恢复及启动验收须记录实际任务 ID；不能把这些测试说成冷启动或模型重建已验证。
