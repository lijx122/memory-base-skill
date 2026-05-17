# 实施计划

## 项目概述
- 项目名：memory-base 三信号融合重构
- 需求文档：`memory-base-refactor-spec.md`
- 当前阶段：规划与接口冻结

## 接口定义

> 所有模块公共接口以 `contracts/module-interfaces.md` 为准。
> `vec.py` 保持现有 CLI 命令名与两步检索协议；保留 `dedup`；新增命令仅限 `init` / `entities` / `relate`。

### vec.py → signal modules
- 调用：`search(query, store, top)`
- 调用：`index_file(file_path, text)`
- 调用：`remove_file(file_path)`
- 调用：`rebuild(store)`
- 约束：`vec.py` 负责参数解析、命令路由、输出格式，不承载检索算法。

### vec.py → fusion.py
- 调用：`merge(results, weights, top)`
- 约束：仅接受三个独立候选集；融合层不做文件 IO。

### vec.py → common.py
- 调用：初始化、读写条目、枚举 entries、读取元数据、词表读写、陈旧索引清理。
- 约束：文件系统布局与 frontmatter 字段解释由 common 统一负责；新增 `common.py` 作为公共工具模块，提供 entries遍历、frontmatter解析、store路径规则、terms管理等共享逻辑。三个信号模块通过调用 common 的接口获取这些能力，避免重复实现或反向依赖CLI入口。

## 任务依赖关系
T1 接口冻结 → T2 common 基础层 → T3 semantic / T4 bm25 / T5 entity 并行 → T6 fusion → T7 vec.py 接线与命令迁移 → T8 索引迁移与兼容验证

## 任务列表

### [已完成] T1 冻结模块接口与仓库约束
- 依赖：无
- 产物：`IMPLEMENTATION_PLAN.md`，`contracts/module-interfaces.md`
- 验收标准：六模块职责、输入输出、错误处理、索引文件布局明确；禁止修改 `SKILL.md`、`bug/entries/`、`knowledge/entries/` 写入计划中显式记录
- 关联接口：全部
- 变更影响：为后续实现提供共享契约
- 锚点：已创建计划与契约文件

### [已完成] T2 实现 common.py 文件与索引目录层
- 依赖：T1
- 产物：`common.py`
- 验收标准：支持 `init`、frontmatter 读取、entries 枚举、词表读写、陈旧索引清理；不修改既有 `bug/entries/`、`knowledge/entries/` 内容
- 关联接口：Storage API
- 变更影响：替换 `vec.py` 中现有文件 IO 与元数据解析逻辑
- 锚点：`python vec.py init`、`python vec.py list`

### [已完成] T3 实现 semantic.py 语义信号
- 依赖：T1, T2
- 产物：`semantic.py`
- 验收标准：延迟加载 sentence-transformers；支持单文件索引、删除、全量重建、检索；索引写入 `index/vectors.pkl`
- 关联接口：Signal API
- 变更影响：替换 `vec.py` 当前向量检索核心
- 锚点：`python vec.py search "测试关键词" --top 3`

### [已完成] T4 实现 keyword.py 关键词信号
- 依赖：T1, T2
- 产物：`keyword.py`
- 验收标准：延迟加载 jieba；支持 BM25 倒排索引构建、删除、重建、检索；缓存目录使用 `index/jieba_cache/`
- 关联接口：Signal API
- 变更影响：新增关键词检索路径
- 锚点：`python vec.py index-dir`、`python vec.py search "SQLite WAL" --top 3`

### [已完成] T5 实现 entity.py 实体信号
- 依赖：T1, T2
- 产物：`entity.py`
- 验收标准：规则提取、三词表匹配、`# auto` 术语追加、`entities.json` 维护、`entities`/`relate` 所需查询能力齐备
- 关联接口：Signal API，Storage API
- 变更影响：新增实体检索与实体关联能力
- 锚点：`python vec.py entities`、`python vec.py relate <file>`

### [已完成] T6 实现 fusion.py 融合排序层
- 依赖：T3, T4, T5
- 产物：`fusion.py`
- 验收标准：三路分数归一化、加权合并、按 file_path 去重、降序返回 top N；默认权重 0.5/0.3/0.2
- 关联接口：Fusion API
- 变更影响：统一 search/check 的综合打分逻辑
- 锚点：融合 smoke test 通过

### [已完成] T7 改造 vec.py CLI 路由与兼容输出
- 依赖：T2, T3, T4, T5, T6
- 产物：`vec.py`
- 验收标准：保留 `search/read/index/index-dir/check/list/remove/dedup` 命令名；新增 `init/entities/relate`；保持两步检索输出协议与 Windows UTF-8 兼容
- 关联接口：全部
- 变更影响：从单文件实现迁移为六模块编排
- 锚点：`python vec.py --help`

### [已完成] T8 执行迁移验证与轻量回归
- 依赖：T7
- 产物：代码内最终兼容实现
- 验收标准：完成 spec 中初始化、全量重建、三信号检索、实体索引、去重、陈旧索引清理、read 轻载等核心检查；至少执行 `python -m py_compile vec.py`、`python vec.py --help`、`python vec.py list` 和受影响子命令验证
- 关联接口：全部
- 变更影响：验证重构未破坏现有 CLI 使用方式
- 锚点：第九节核心命令已验证
