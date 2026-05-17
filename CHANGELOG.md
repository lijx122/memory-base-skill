# 变更记录

## v0.2.0 (2026-05-17)

### 新增
- 将单文件 [`vec.py`](vec.py) 重构为 CLI + [`common.py`](common.py) + [`semantic.py`](semantic.py) + [`bm25.py`](bm25.py) + [`entity.py`](entity.py) + [`fusion.py`](fusion.py)
- 新增 `init`、`entities`、`relate` 命令
- 新增 `contracts/module-interfaces.md`、`IMPLEMENTATION_PLAN.md`、`TECH_DEBT.md`
- 新增三类本地索引文件：`index/vectors.pkl`、`index/bm25.json`、`index/entities.json`
- 偏离原始模块命名说明：新增 common.py 作为公共工具模块，提供 entries遍历、frontmatter解析、store路径规则、terms管理等共享逻辑。三个信号模块通过调用 common 的接口获取这些能力，避免重复实现或反向依赖CLI入口。

### 修复
- 修复定向 `index-dir --store` 会覆盖其他子库索引的问题
- 修复 `remove` 依赖模糊搜索判断是否存在索引记录的问题
- 修复轻量命令路径下的延迟加载边界，`read` / `list` / `entities` 不触发重依赖
- 为缺失 `jieba` 的环境提供关键词分词降级路径，使全量重建仍可完成

### 已知问题
- 无

### 回滚方式
- 命令：`git checkout 47f9b42 -- vec.py common.py semantic.py bm25.py entity.py fusion.py IMPLEMENTATION_PLAN.md TECH_DEBT.md CHANGELOG.md contracts/module-interfaces.md`

## v0.2.0-planning (2026-05-17)

### 新增
- 新增重构实施计划 `IMPLEMENTATION_PLAN.md`
- 新增模块接口契约 `contracts/module-interfaces.md`
- 新增技术债跟踪文件 `TECH_DEBT.md`

### 修复
- 无

### 已知问题
- D1：目录布局与现有实现不一致，迁移时需要兼容处理
- D2：缺少自动化测试，当前仅能执行 CLI 级验证

### 回滚方式
- 命令：`git checkout 47f9b42 -- IMPLEMENTATION_PLAN.md TECH_DEBT.md CHANGELOG.md contracts/module-interfaces.md`
