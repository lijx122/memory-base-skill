---
name: memory-base
version: 3.0.0
description: 本地AI Agent知识记忆系统。三信号融合检索（语义+BM25+实体），双子库（bug/knowledge），多词表实体链接，纯文件系统，零API成本。遇到报错、讨论技术原理、修复bug、总结经验时触发。
---
# Memory Base — AI Agent 知识记忆系统
## 说明
本地优先的知识记忆系统，包含两个子库：
- **bug**：开发中遇到的具体故障及解决方案
- **knowledge**：技术原理、方法论、最佳实践、可复用经验
CLI入口：`python ~/.claude/skills/memory-base/vec.py`
### 架构
六个文件，各自职责清晰：
| 文件 | 职责 | 外部依赖 |
|------|------|----------|
| vec.py | CLI入口 + init/read/list等轻量操作 | 无 |
| semantic.py | 语义信号（embedding + 向量索引） | sentence-transformers |
| bm25.py | 关键词信号（分词 + 倒排索引） | jieba |
| entity.py | 实体信号（规则提取 + 多词表 + 实体索引） | 无 |
| fusion.py | 三路融合（归一化 + 加权合并） | 无 |
| common.py | 公共工具（frontmatter解析、entries遍历、词表管理） | 无 |
三个信号模块互相零依赖，各自管自己的索引IO。common.py提供共享基础设施。
### 三信号融合检索
每次检索同时走三条路径，加权合并：
- **语义信号**（权重0.5）：sentence-transformers embedding + 余弦相似度
- **关键词信号**（权重0.3）：jieba分词 + BM25算法
- **实体信号**（权重0.2）：正则提取实体 + 多词表匹配 + 实体索引
三路结果归一化到[0,1]后加权融合，返回综合分排序的结果。
### 两步检索协议
search命令**只返回title + summary + score + 子库标签**，不返回全文。Director判断相关后手动执行read拉全文。这是上下文成本控制的核心。
### 多词表实体系统
三个词表，按类型分配实体：
- **terms_tech.txt**：技术名词、框架、库、语言、工具
- **terms_project.txt**：项目名、模块名（随项目推进自动增长）
- **terms_people.txt**：人物名
词表只用于实体提取时的字符串匹配，不加载进LLM上下文。
### 写入策略分化
- **knowledge子库：ADD-only** — 新事实新建文件，不修改旧条目。同一主题的多条记忆通过实体链接关联，检索时按时间倒序排列。
- **bug子库：原地更新** — 旧方案失效时原地修改文件 + 末尾追加更新记录。避免过时方案被采用导致二次故障。
---
## 写入边界（三方规则）
知识库与模块agent文件的经验记录存在交集，以下规则明确边界：
1. **模块agent文件**（优先级最高）：该模块专属的上下文，离开这个模块就没用的信息。agent文件有记录的，知识库不重复记录。
2. **bug子库**：可能在其他项目或模块也遇到的具体故障和解决方案。
3. **knowledge子库**：脱离具体项目后仍成立的规律、方法论、最佳实践。
判断顺序：先判断是否模块专属 → 是则写agent文件，不写知识库；否则判断是具体故障还是通用规律 → 分别写bug或knowledge。同一条经验不允许同时写入两个地方。
---
## 各子库记录标准
### bug子库
记录的内容：
- 代码/系统运行的实际故障
- 触发条件、现象、解决方案三者齐全
不记录的内容：
- 规范性问题、方法论（→ knowledge）
- 模块专属的坑（→ agent文件）
### knowledge子库
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
bug子库：无前缀，直接用描述命名
knowledge子库：
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
三信号融合，同时检索两个子库：
```
python ~/.claude/skills/memory-base/vec.py search "<关键词>" --top 5
```
返回：[综合分] [子库] title | summary | file_path
### 定向检索（明确知道查哪个子库时）
```
python ~/.claude/skills/memory-base/vec.py search "<关键词>" --store bug --top 3
python ~/.claude/skills/memory-base/vec.py search "<关键词>" --store knowledge --top 3
```
### 读取完整内容
根据summary判断相关后：
```
python ~/.claude/skills/memory-base/vec.py read <file_path>
```
### 实体关联查找
通过共享实体找到逻辑相关但语义不相似的条目：
```
python ~/.claude/skills/memory-base/vec.py relate <file_path>
```
### 查看实体索引
```
python ~/.claude/skills/memory-base/vec.py entities
python ~/.claude/skills/memory-base/vec.py entities "SQLite"
```
---
## 写入流程（自动执行）
### 第0步：写入前自检
**归属判断**
- 模块专属上下文？→ 写agent文件，不写知识库
- 具体故障（有触发条件+现象+解决方案）？→ bug子库
- 通用规律/方法论/最佳实践？→ knowledge子库
- 个人决策/事件/情绪？→ 不写入
**粒度判断（knowledge专用）**
- 过泛（如"先看再做"）：细化到具体场景再写入
- 过细（只在极小场景成立）：提炼出可复用的规律再写入
- 合适粒度：脱离当前对话后，在类似场景下能直接指导行动
任一不满足 → 不写入。
### 第1步：生成title + summary
**核心原则：title写规律不写事件，summary写因果不写过程。**
三信号检索中，语义信号和关键词信号都作用于title+summary。写得好不好直接决定这条记录未来能不能被找到。
要覆盖两类场景：①遇到同样问题时能命中（修复价值），②正在考虑类似操作时能命中（预防价值）。
#### bug的title + summary
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
#### knowledge的title + summary
**title**：通用性结论，不含"我"或当前项目特有的词。
```
❌ 我在虚拟炒股项目里发现串行比并行好
   （绑定了具体项目和个人）
✅ 低频 API 调用场景下串行请求优于并行：减少限流风险且代码更简单
   （通用结论 + 适用条件）
```
**summary**：核心观点 + 适用条件/因果依据，25-50字。
包含该知识点可能被搜索的关键词。
```
❌ 向量检索很重要
   （太泛，什么都匹配 = 什么都不匹配）
✅ 向量检索只对 title+summary 生效时，summary 质量决定命中率，
   需含触发动作和关键词
   （具体机制 + 可操作指导）
```
### 第2步：去重 + 矛盾检查
```
python ~/.claude/skills/memory-base/vec.py check "<title + summary>" --threshold 0.9
```
返回判断（使用三信号综合分）：
- **score > 0.9**（完全重复）：跳过写入，告知用户已有记录
- **score 0.7~0.9**（相关但不重复）：读取已有条目内容，判断新旧观点是否矛盾
  - 矛盾：在两条记录里互相标注"此观点在XX场景下有不同结论，见[另一条的file_path]"
  - 不矛盾：正常写入，在相关条目中互相引用
- **score < 0.7**：直接进入第3步写入
### 第3步：写入文件
**文件名格式**：
- bug：`YYYYMMDD-简短英文描述.md`（如 20260423-uv-venv-exists.md）
- knowledge：`YYYYMMDD-分类前缀-简短英文描述.md`（如 20260423-experience-check-existing-format.md）
**内容写入**：按对应模板（见文件末尾）生成文件内容。
### 第4步：索引
```
python ~/.claude/skills/memory-base/vec.py index <file_path>
```
同时更新三个索引（向量+倒排+实体）。写入时自动提取实体并更新词表和实体索引。
### 第5步：自动实体关联
index命令执行后，自动通过实体索引找到共享实体的相关条目，在新文件末尾追加：
```
## 相关条目
- [tech:SQLite] bug/entries/20260423-sqlite-wal-lock.md
- [tech:并发] knowledge/entries/20260420-tech-sqlite-concurrency.md
```
这替代了原来基于纯向量相似度的关联——通过共享实体关联，能找到语义不相似但逻辑相关的条目。
### 第6步：告知用户
```
已记录[Bug/知识]：<title>
文件路径：<file_path>
关联条目：<N> 条（如有）
```
---
## 更新流程
### bug子库：原地更新（旧记录失效时触发）
**触发条件**：检索命中某条bug记录并采用其方案后，发现该方案不适用或执行失败，且已用新方式成功解决。
**采用标记**：检索命中并实际采用某条记录的方案时，Director在当前上下文中标记"正在使用[file_path]的方案"。后续该方案失败时，能关联回去知道该更新哪条。
**执行步骤**：
1. 读取原记录：`python vec.py read <原记录file_path>`
2. 原地更新文件内容：
   - 更新解决方案为当前正确的版本
   - 如有必要更新summary（确保后续检索能命中新方案）
   - 如有必要更新env字段
   - 末尾"更新记录"段追加：`- YYYY-MM-DD：原方案[旧方案摘要]，更新为[新方案摘要]，原因：[失败原因]`
3. 重建索引：`python vec.py index <file_path>`
4. 稳定性标记：更新两次以上的条目在frontmatter中设`stability: low`，检索命中时提醒"此条目曾多次更新，建议先验证再采用"
5. 告知用户
### knowledge子库：ADD-only
knowledge不做原地更新。观点演变时新建一条记忆，通过实体链接与旧记忆关联。检索时同一主题的多条记忆按时间倒序排列，最新的排最前。
---
## multi-agent模式下的职责分配
- 子agent遇到需要检索知识库的场景时，将关键信息返回给Director
- Director执行检索并将结果传回子agent
- 知识库的写入同样由Director统一执行
- 子agent不直接调用vec.py
---
## 命令参考
| 命令 | 用途 | 重型依赖 |
|------|------|----------|
| `search "<关键词>" --top N [--store bug/knowledge]` | 三信号融合检索，返回title+summary | 是 |
| `read <file_path>` | 读取条目全文 | 否 |
| `index <file_path>` | 为单个文件建三路索引 | 是 |
| `index-dir [--store bug/knowledge]` | 全量重建索引（含陈旧清理） | 是 |
| `remove <file_path>` | 从三路索引中移除 | 否 |
| `list [--store bug/knowledge]` | 列出所有条目 | 否 |
| `check "<text>" --threshold N` | 去重检查（三信号综合分） | 是 |
| `entities [实体名]` | 查看实体索引 | 否 |
| `relate <file_path>` | 通过共享实体找关联条目 | 否 |
| `dedup --min N --threshold N` | 批量去重 | 是 |
| `init` | 初始化目录结构和词表 | 否 |
---
## Bug文件模板
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
## 相关条目（自动生成，通过实体关联）
## 更新记录（仅更新时追加）
- YYYY-MM-DD：原方案 XXX，更新为 YYY，原因：ZZZ
```
## Knowledge文件模板
```markdown
---
title: （通用性结论，不含"我"或具体项目名。问"换个项目/场景这个结论还成立吗？"）
summary: （核心观点 + 适用条件/因果依据，25-50字。包含该知识可能被搜索的关键词）
env: （可选。如果知识和特定版本/环境相关，标注）
stability: high
---
## 背景
## 核心观点
## 依据或经历
## 适用场景
## 相关条目（自动生成，通过实体关联）
## 更新记录（仅knowledge ADD-only模式下，此段不使用。观点演变时新建条目）
```