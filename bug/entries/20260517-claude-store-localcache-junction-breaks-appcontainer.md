---
title: Windows Store 应用的 LocalCache 不能通过 Junction/符号链接迁移
summary: Claude 等 Store 应用的 LocalCache 通过 Junction 迁移到其他盘后，应用内的工具调用（python/node）会失败，原因是 UWP 沙箱权限不跟随链接。回滚到原生路径后恢复。迁移 AppData 相关目录前需确认应用是否走 UWP 沙箱。
env: Windows 11 / Claude Store App 1.6608.2.0 / Claude Code 2.1.128 / Python 3.12.10
stability: high
---

## 触发条件

- 为释放 C 盘空间，迁移多个 AppData 目录到 D 盘，并在原路径保留 Windows Junction。
- 其中包含 `C:\Users\l\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache -> D:\AppDataMoved\Packages\Claude_pzs8sxrjxfjjc\LocalCache`。
- 迁移后重启 Claude Desktop，再在 Claude / Claude Code 内部执行 Python 或工具命令。

## 现象

- 系统终端里的 `python`、`fnm`、`node`、`winget` 可以正常运行。
- Claude / Claude Code 内部调用本机 Windows Python 失败，表现为 PowerShell 中执行 `C:\Users\l\AppData\Local\Programs\Python\Python312\python.exe` 报 `CommandNotFoundException`。
- 重启应用、新开对话后问题仍存在。

## 根本原因

- Claude 是 Microsoft Store 包应用，其 `LocalCache` 目录依赖包目录下的 AppContainer 权限。
- 原路径 Junction 可见，但 D 盘真实目标目录没有继承 Store 包对应的 AppContainer SID 权限。
- 结果是商店版 Claude 对迁移后的 `LocalCache` 访问异常，进一步影响内部工具和会话环境初始化。
- 侧面证据包括：
  - `Packages\...\LocalCache\Roaming\Claude\logs` 在迁移后不再继续更新。
  - Windows 事件中出现 `Claude_1.6608.2.0_x64__pzs8sxrjxfjjc` 的 `MoAppHang`。

## 解决方案

- 只回滚这一处迁移，不回滚其他缓存目录。
- 删除 `C:\Users\l\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache` 的 Junction。
- 将 `D:\AppDataMoved\Packages\Claude_pzs8sxrjxfjjc\LocalCache` 搬回原路径，恢复为 C 盘上的真实目录。
- 回滚后验证：
  - `LocalCache` 不再是 ReparsePoint。
  - 包目录 AppContainer SID 权限重新存在。
  - Claude 重新启动后再验证内部调用。

## 相关代码片段

- 迁移前后关键目录：
  - `C:\Users\l\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache`
  - `D:\AppDataMoved\Packages\Claude_pzs8sxrjxfjjc\LocalCache`

## 更新记录

- 2026-05-17：最初记录为“Claude 商店版 LocalCache 迁移到 D 盘后导致应用内工具调用失败”，后按新版知识库规则更新为通用规律型标题和因果型摘要，原因：原写法过于事件化，不利于跨项目检索和预防性命中。
