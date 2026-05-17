---
name: memory-base
version: 2.0.0
description: 统一知识库，包含 bug 记录和通用知识两个子库。向量化检索 + 自动写入 + 去重检测 + 交叉检索 + 更新机制 + 矛盾检测。遇到报错、讨论技术原理、修复 bug、总结经验时触发。
---

# Memory Base — 统一知识库

## 说明

统一知识库，包含两个子库：
- **bug**：开发中遇到的具体故障及解决方案
- **knowledge**：技术原理、方法论、最佳实践、可复用经验

底层脚本：python ~/.claude/skills/memory-base/vec.py
文件目录：
- ~/.claude/skills/memory-base/bug/entries/
- ~/.claude/skills/memory-base/knowledge/entries/

---

## 写入边界（三方规则）

知识库与模块 agent 文件的经验记录存在交集，以下规则明确边界：

1. **模块 agent 文件**（优先级最高）：该模块专属的上下文，离开这个模块就没用的信息。agent 文件有记录的，知识库不重复记录。
2. **bug 子库**：可能在其他项目或模块也遇到的具体故障和解决方案。
3. **knowledge 子库**：脱离具体项目后仍成立的规律、方法论、最佳实践。

判断顺序：先判断是否模块专属 → 是则写 agent 文件，不写知识库；否则判断是具体故障还是通用规律 → 分别写 bug 或 knowledge。同一条经验不允许同时写入两个地方。

---

## 各子库记录标准

### bug 子库

记录的内容：
- 代码/系统运行的实际故障
- 触发条件、现象、解决方案三者齐全

不记录的内容：
- 规范性问题、方法论（→ knowledge）
- 模块专属的坑（→ agent 文件）

### knowledge 子库

记录的内容：
- 技术原理、方法论、最佳实践
- 行业规律、领域经验
- 工具使用技巧、框架特性
- 从经历中提炼的可复用经验

不记录的内容：
- 用户的个人决策（租房、考公、工作选择等）
- 事件性陈述（"今天做了什么"）
- 未经验证的临时想法

判断标准：这条内容对其他项目或其他人是否也有参考价值？

---

## 分类前缀

bug 子库：无前缀，直接用描述命名
knowledge 子库：
- tech-*.md         技术原理与方法论
- experience-*.md   可复用的经验总结
- tool-*.md         工具使用技巧

---

## 触发时机

以下情况主动触发检索：
- 遇到报错、异常、页面异常表现
- 准备修改某个历史上出过问题的模块
- 讨论技术原理、最佳实践
- 提到某个框架或工具的用法
- 用户提到"之前遇到过类似的"
- 用户总结了可复用的经验

---

## 检索流程

### 统一检索（默认行为）

同时检索两个子库，合并结果按相似度排序：

```
python ~/.claude/skills/memory-base/vec.py search "<关键词>" --top 5
```

返回：[相似度] [子库] title | summary | file_path

### 定向检索（明确知道查哪个子库时）

```
python ~/.claude/skills/memory-base/vec.py search "<关键词>" --store bug --top 3
python ~/.claude/skills/memory-base/vec.py search "<关键词>" --store knowledge --top 3
```

### 读取完整内容

根据 summary 判断相关后：

```
python ~/.claude/skills/memory-base/vec.py read <file_path>
```

---

## 写入流程（自动执行）

### 第 0 步：写入前自检

**归属判断**
- 模块专属上下文？→ 写 agent 文件，不写知识库
- 具体故障（有触发条件+现象+解决方案）？→ bug 子库
- 通用规律/方法论/最佳实践？→ knowledge 子库
- 个人决策/事件/情绪？→ 不写入

**粒度判断（knowledge 专用）**
- 过泛（如"先看再做"）：细化到具体场景再写入
- 过细（只在极小场景成立）：提炼出可复用的规律再写入
- 合适粒度：脱离当前对话后，在类似场景下能直接指导行动

任一不满足 → 不写入。

### 第 1 步：生成 title + summary

**核心原则：title 写规律不写事件，summary 写因果不写过程。**

向量检索只对 title+summary 生效。写得好不好直接决定这条记录未来能不能被找到。
要覆盖两类场景：①遇到同样问题时能命中（修复价值），②正在考虑类似操作时能命中（预防价值）。

#### bug 的 title + summary

**title**：写成通用规律/结论，不写成具体事件描述。

```
❌ Claude 商店版 LocalCache 迁移到 D 盘后导致应用内工具调用失败
   （太具体，只能匹配"Claude + D盘"这个精确场景）

✅ Windows Store 应用的 LocalCache 不能通过 Junction/符号链接迁移
   （通用规律，匹配所有 UWP 应用的类似场景）
```

```
❌ 项目 A 升级 Node 20 后 fs.watch 报错
   （绑定了具体项目名）

✅ Node 20 的 fs.watch 在 Windows 上递归监听大目录时抛 EPERM
   （通用条件，任何项目遇到都能命中）
```

**summary**：写因果链（做了什么 → 为什么失败 → 根本原因 → 适用范围），不写操作日志。
包含关键触发词，让"正在考虑做类似操作"的场景也能命中。

```
❌ 将 LocalCache 迁移到 D 盘并保留 Junction 后，Claude 重启后工具调用失败；
   回滚后恢复。
   （操作日志，只匹配"已经出问题了"的场景）

✅ Claude 等 Store 应用的 LocalCache 通过 Junction 迁移到其他盘后，应用内工具调用
   （python/node）失败，原因是 UWP 沙箱权限不跟随链接。迁移 AppData 相关目录前
   需确认应用是否走 UWP 沙箱。
   （因果链 + "迁移 AppData"触发词覆盖预防场景）
```

#### knowledge 的 title + summary

**title**：通用性结论，不含"我"或当前项目特有的词。

```
❌ 我在虚拟炒股项目里发现串行比并行好
   （绑定了具体项目和个人）

✅ 低频 API 调用场景下串行请求优于并行：减少限流风险且代码更简单
   （通用结论 + 适用条件）
```

**summary**：核心观点 + 适用条件/因果依据，25-50 字。
包含该知识点可能被搜索的关键词。

```
❌ 向量检索很重要
   （太泛，什么都匹配 = 什么都不匹配）

✅ 向量检索只对 title+summary 生效时，summary 质量决定命中率，
   需含触发动作和关键词
   （具体机制 + 可操作指导）
```

### 第 2 步：去重 + 矛盾检查

```
python ~/.claude/skills/memory-base/vec.py check "<title + summary>" --threshold 0.9
```

返回判断：
- **score > 0.9**（完全重复）：跳过写入，告知用户已有记录
- **score 0.7~0.9**（相关但不重复）：读取已有条目内容，判断新旧观点是否矛盾
  - 矛盾：在两条记录里互相标注"此观点在XX场景下有不同结论，见[另一条的file_path]"
  - 不矛盾：正常写入，在相关条目中互相引用
- **score < 0.7**：直接进入第 3 步写入

### 第 3 步：写入文件

**文件名格式**：
- bug：`YYYYMMDD-简短英文描述.md`（如 20260423-uv-venv-exists.md）
- knowledge：`YYYYMMDD-分类前缀-简短英文描述.md`（如 20260423-experience-check-existing-format.md）

**内容写入**：按对应模板（见文件末尾）生成文件内容。

### 第 4 步：索引

```
python ~/.claude/skills/memory-base/vec.py index <file_path>
```

### 第 5 步：关联记录

执行 search（top 3），如果存在 score > 0.6 的条目，在新文件末尾追加：

```
## 相关条目
- [score] 其他条目 title (file_path)
```

### 第 6 步：告知用户

```
已记录[Bug/知识]：<title>
文件路径：<file_path>
关联条目：<N> 条（如有）
```

---

## 更新流程（旧记录失效时触发）

### 触发条件

检索命中某条记录并采用其方案后，发现该方案不适用或执行失败，且已用新方式成功解决了问题。

### 采用标记

检索命中并实际采用某条记录的方案时，Director 在当前上下文中标记"正在使用 [file_path] 的方案"。后续该方案失败时，能关联回去知道该更新哪条。

### 执行步骤

**第 1 步：读取原记录**

```
python ~/.claude/skills/memory-base/vec.py read <原记录file_path>
```

**第 2 步：原地更新文件内容**

- 更新解决方案/核心观点为当前正确的版本
- 如有必要更新 summary（确保后续检索能命中新方案）
- 如有必要更新 env 字段（版本/环境变了）
- 在文件末尾"更新记录"段追加：
  `- YYYY-MM-DD：原方案[旧方案摘要]，更新为[新方案摘要]，原因：[失败原因]`

**第 3 步：重建索引**

```
python ~/.claude/skills/memory-base/vec.py index <file_path>
```

（summary 变了，向量需要重新生成）

**第 4 步：稳定性标记**

如果同一条记录被更新了两次以上，在 frontmatter 中添加 `stability: low`。后续检索命中时 Director 带一句"此条目曾多次更新，建议先验证再采用"。

**第 5 步：告知用户**

```
已更新记录：<title>
变更：<一句话说明改了什么>
```

---

## multi-agent 模式下的职责分配

- 子 agent 遇到需要检索知识库的场景时，将关键信息返回给 Director
- Director 执行检索并将结果传回子 agent
- 知识库的写入同样由 Director 统一执行
- 子 agent 不直接调用 vec.py

---

## Bug 文件模板

```markdown
---
title: （通用规律/结论，不写具体事件。问"其他项目遇到类似问题能搜到吗？"）
summary: （因果链：做了什么→为什么失败→根本原因→适用范围。包含预防场景的触发词）
env: （可选。相关的版本/环境信息，如 Node 20.x / Python 3.12 / Claude Code v1.x）
stability: high
---

## 触发条件

## 现象

## 根本原因

## 解决方案

## 相关代码片段
尽量提供。如果代码较长，贴关键几行即可。

## 相关条目（可选，自动关联）

## 更新记录（仅更新时追加）
- YYYY-MM-DD：原方案 XXX，更新为 YYY，原因：ZZZ
```

## Knowledge 文件模板

```markdown
---
title: （通用性结论，不含"我"或具体项目名。问"换个项目/场景这个结论还成立吗？"）
summary: （核心观点 + 适用条件/因果依据，25-50 字。包含该知识可能被搜索的关键词）
env: （可选。如果知识和特定版本/环境相关，标注）
stability: high
---

## 背景

## 核心观点

## 依据或经历

## 适用场景

## 相关条目（可选，自动关联）

## 更新记录（仅更新时追加）
- YYYY-MM-DD：原观点 XXX，更新为 YYY，原因：ZZZ
```