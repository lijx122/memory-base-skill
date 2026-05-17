# Memory-Base 重构需求文档

## 一、项目概述

对 `~/.claude/skills/memory-base/` 进行架构升级。两个维度的变更：

**架构变更**：从单文件 vec.py 拆分为六模块架构，职责单一，依赖隔离。

**功能变更**：从单信号向量检索升级为三信号融合检索（语义+关键词+实体），新增实体链接机制，knowledge子库改为ADD-only写入模式，bug子库保留原地更新。

不引入任何外部服务依赖（无Qdrant、无Redis、无PostgreSQL、无LLM API调用）。纯本地Python + 文件系统。

### 分发形态

以 skill 形态通过 GitHub 仓库分发。用户将仓库链接提供给自己的 AI Agent，Agent 读取 README 完成安装和初始化。

仓库文件结构：
```
memory-base/
├── README.md          # 安装说明，AI Agent 可读即可安装
├── SKILL.md           # skill 规范文档
├── vec.py             # CLI入口，参数解析，命令路由，init/read/list等直接操作
├── semantic.py        # 语义信号（自包含：embedding + vectors.pkl读写）
├── keyword.py         # 关键词信号（自包含：jieba分词 + bm25.json读写）
├── entity.py          # 实体信号（自包含：正则提取 + 词表管理 + entities.json读写）
└── fusion.py          # 三路融合（纯计算，接收三路结果做归一化+加权）
```

安装流程（README中说明）：
1. 将仓库文件复制到 Agent 的 skills 目录
2. 执行 `python vec.py init` 创建目录结构和初始词表
3. 按提示安装依赖
4. 开始使用

## 1.1 模块职责与依赖关系

五个文件，四个模块 + 一个入口。三个信号模块互相零依赖，各自完全自包含。

### vec.py — CLI入口
- 参数解析（argparse），命令路由到对应模块
- 直接实现以下轻量操作（不值得单独建模块）：
  - init：创建目录结构、空索引文件、初始词表
  - read：读取并输出条目全文
  - list：遍历entries目录列出条目
  - check：调用fusion做去重判断
  - frontmatter解析：从markdown提取title/summary/env/stability
  - entries文件遍历
- search/index/remove/index-dir 命令路由到对应模块
- Windows UTF-8 输出兼容在此处设置
- 不直接import重型依赖（sentence-transformers、jieba）

### semantic.py — 语义信号（完全自包含）
- sentence-transformers 的 embedding 生成
- 向量索引（index/vectors.pkl）读写 — 自己管自己的索引IO
- 余弦相似度计算
- 陈旧索引清理（检查file_path是否存在）
- 唯一持有 sentence-transformers 依赖的模块
- 延迟import：被调用时才加载模型
- 对外API：search / index_file / remove_file / rebuild

### keyword.py — 关键词信号（完全自包含）
- jieba 分词
- BM25 倒排索引（index/bm25.json）构建、查询、读写 — 自己管自己的索引IO
- 陈旧索引清理
- 唯一持有 jieba 依赖的模块
- 延迟import：被调用时才加载jieba
- jieba缓存目录设为 index/jieba_cache/
- 对外API：search / index_file / remove_file / rebuild

### entity.py — 实体信号（完全自包含）
- 正则提取实体（强规则 + 弱规则）
- 多词表管理（加载、匹配、自动追加）— 自己管词表IO
- 实体索引（index/entities.json）读写 — 自己管自己的索引IO
- 实体类型分配（tech / project / people）
- 陈旧索引清理
- 纯标准库，无外部依赖
- 对外API：search / index_file / remove_file / rebuild / list_entities / relate

### fusion.py — 三信号融合（纯计算）
- 接收三个信号模块各自的候选集 List[(file_path, score)]
- 各信号分数归一化到 [0, 1]
- 加权合并：默认 semantic=0.5, bm25=0.3, entity=0.2
- 同一 file_path 只保留最高综合分
- 按综合分降序排序，返回 top N
- 纯计算，无IO，无外部依赖
- 对外API：merge

## 1.2 模块间接口约定

### 三个信号模块统一接口

```python
# semantic.py / keyword.py / entity.py 各自实现以下接口
def search(query: str, store: str | None, top: int, base_dir: str) -> list[tuple[str, float]]:
    """返回 [(file_path, score), ...] 按分数降序
    base_dir: 项目根目录，用于定位索引文件"""

def index_file(file_path: str, text: str, base_dir: str) -> None:
    """为单个文件建索引，text = title + summary（语义）或 title + summary + content（关键词/实体）
    各模块自己决定用text的哪些部分"""

def remove_file(file_path: str, base_dir: str) -> None:
    """从本模块的索引中移除单个文件"""

def rebuild(store: str | None, entries: list[dict], base_dir: str) -> dict:
    """重建索引。entries = [{"file_path": ..., "text": ...}, ...]
    先清理陈旧索引，再重建。返回统计信息 {"count": N, "cleaned": M}"""
```

### entity.py 额外接口

```python
def list_entities(base_dir: str, filter_term: str | None = None) -> dict:
    """返回实体索引内容。filter_term不为None时只返回该实体的关联条目"""

def relate(file_path: str, base_dir: str) -> list[tuple[str, str, str]]:
    """通过共享实体找关联条目。返回 [(entity_type, entity_name, related_file_path), ...]"""
```

### fusion 模块接口

```python
def merge(
    results: list[list[tuple[str, float]]],  # 三路候选集
    weights: list[float],                     # 三路权重
    top: int                                  # 返回数量
) -> list[tuple[str, float]]:
    """归一化+加权+去重+排序，返回 [(file_path, final_score), ...]"""
```

### vec.py 内部函数（不是独立模块，不需要接口契约）

```python
def parse_frontmatter(file_path: str) -> dict:
    """从markdown提取 title/summary/env/stability"""

def read_full(file_path: str) -> str:
    """读取并返回完整文件内容"""

def list_entries(store: str | None, base_dir: str) -> list[str]:
    """遍历entries目录返回文件路径列表"""

def init(base_dir: str) -> None:
    """创建目录结构、空索引、初始词表"""
```

## 1.3 数据流

### search 命令
```
vec.py search "SQLite WAL" --top 5
    │
    vec.py（解析参数，确定base_dir）
    │
    ├→ semantic.search("SQLite WAL", store, 20, base_dir) → [(file, score), ...]
    ├→ keyword.search("SQLite WAL", store, 20, base_dir)  → [(file, score), ...]
    ├→ entity.search("SQLite WAL", store, 20, base_dir)   → [(file, score), ...]
    │
    └→ fusion.merge(三路结果, weights=[0.5,0.3,0.2], top=5)
         │
         └→ vec.py: parse_frontmatter(file_paths) → 拼接 [score] [store] title | summary | path
```

### index 命令
```
vec.py index <file_path>
    │
    vec.py（解析参数，parse_frontmatter拿到title+summary，read_full拿到content）
    │
    ├→ semantic.index_file(file_path, title+summary, base_dir)
    ├→ keyword.index_file(file_path, title+summary+content, base_dir)
    └→ entity.index_file(file_path, title+summary+content, base_dir)
```

### init 命令
```
vec.py init
    │
    vec.py（直接执行）
    │
    ├→ 创建 index/, bug/entries/, knowledge/entries/ 目录
    ├→ 创建空的 vectors.pkl, bm25.json, entities.json
    └→ 创建 terms_tech.txt（预置）, terms_project.txt（空）, terms_people.txt（空）
```

### read / list / entities / relate 命令
```
vec.py read <file_path>     →  vec.py: read_full(file_path) → 输出
vec.py list                 →  vec.py: list_entries(store) → 输出
vec.py entities             →  entity.list_entities(base_dir) → 输出
vec.py entities "SQLite"    →  entity.list_entities(base_dir, "SQLite") → 输出
vec.py relate <file_path>   →  entity.relate(file_path, base_dir) → 输出
```

## 二、运行时目录结构（init后）

```
~/.claude/skills/memory-base/
├── SKILL.md                      # 仓库提供
├── README.md                     # 仓库提供
├── vec.py                        # 仓库提供 - CLI入口 + init/read/list
├── semantic.py                   # 仓库提供 - 语义信号（自包含）
├── keyword.py                    # 仓库提供 - 关键词信号（自包含）
├── entity.py                     # 仓库提供 - 实体信号（自包含）
├── fusion.py                     # 仓库提供 - 三路融合（纯计算）
├── .gitignore                    # 仓库提供
├── index/                        # init 生成
│   ├── vectors.pkl               # 向量索引（语义信号）
│   ├── bm25.json                 # 倒排索引（关键词信号）
│   ├── entities.json             # 实体→条目映射（带类型）
│   ├── terms_tech.txt            # 技术词表（init预置）
│   ├── terms_project.txt         # 项目词表（init创建空文件）
│   └── terms_people.txt          # 人物词表（init创建空文件）
├── bug/                          # init 生成
│   └── entries/
└── knowledge/                    # init 生成
    └── entries/
```

仓库只包含 .py文件 + SKILL.md + README.md + .gitignore（共7个文件）。index/、bug/、knowledge/ 由 init 生成，.gitignore排除。

### 新用户

执行 `python vec.py init` 即可，零配置开始使用。

### 现有用户（小电）

- 现有 bug/entries/ 和 knowledge/entries/ 下的文件不动不删
- 现有的向量索引文件迁移到 index/vectors.pkl（或就地重建）
- 新增 index/bm25.json 和 index/entities.json，从现有entries重建
- init 检测到已有 entries 目录时，跳过创建、直接进入索引重建

## 三、核心架构变更

### 3.1 三信号检索（最高优先级）

#### 信号1：语义检索（保留现有能力）

- 使用现有的 sentence-transformers 做 embedding
- 对 title + summary 做向量化（和现在一致）
- 余弦相似度打分

#### 信号2：关键词检索（新增）

- 使用 jieba 分词（需安装：`pip install jieba`）
- 对 title + summary 做分词，构建倒排索引存入 bm25.json
- 检索时对查询分词，BM25 算法打分
- bm25.json 结构示例：
```json
{
  "doc_count": 42,
  "avg_doc_len": 15.3,
  "inverted_index": {
    "SQLite": [
      {"file": "bug/entries/20260423-sqlite-wal-lock.md", "tf": 2, "doc_len": 12},
      {"file": "knowledge/entries/20260420-tech-sqlite-concurrency.md", "tf": 1, "doc_len": 18}
    ]
  }
}
```

#### 信号3：实体检索（新增）

- 写入时从 title + summary + 正文中提取实体
- 实体类型：技术名词、框架/库名、模块名、文件路径、工具名、编程语言名
- 提取方式：正则 + 简单规则（不调LLM）
  - 大写开头的连续词（如 Claude Code, Node.js, SQLite）
  - 反引号包裹的内容（如 `src/auth/`）
  - 已知技术词表匹配（维护一个基础词表，写入时自动扩充）
- 存入 entities.json，结构带实体类型：
```json
{
  "SQLite": {
    "type": "tech",
    "entries": ["bug/entries/20260423-sqlite-wal-lock.md", "knowledge/entries/20260420-tech-sqlite-concurrency.md"]
  },
  "AI Workbench": {
    "type": "project",
    "entries": ["knowledge/entries/20260415-experience-workbench-arch.md"]
  },
  "老王": {
    "type": "people",
    "entries": ["knowledge/entries/20260501-experience-taobao-collaboration.md"]
  }
}
```

#### 三路融合

检索时三个信号各自产出候选集和分数，然后加权融合：

```
final_score = w_semantic * semantic_score + w_bm25 * bm25_score + w_entity * entity_score
```

默认权重：w_semantic = 0.5, w_bm25 = 0.3, w_entity = 0.2

- 各信号的分数先归一化到 [0, 1] 区间再加权
- 三路结果合并去重（同一个file_path只保留最高综合分）
- 按综合分降序返回

### 3.2 两步检索协议（关键设计）

search 命令**只返回 title + summary + score + 子库标签**，不返回全文。

```
[0.87] [bug] SQLite WAL 锁超时 | 并发写入时WAL模式仍有锁超时，需设置busy_timeout | bug/entries/20260423-sqlite-wal-lock.md
```

Director 判断相关后手动执行 read 拉全文。这是上下文成本控制的核心，不可改变。

### 3.3 写入策略分化

#### knowledge 子库：ADD-only

- 新事实直接新建文件，不修改已有文件
- 观点演变时，新建一条新记忆，通过实体链接和相关条目字段与旧记忆关联
- 检索返回时，同一主题的多条记忆按时间倒序排列，最新的排最前
- 旧条目不删除、不修改（除非手动要求清理）

#### bug 子库：原地更新

- 保持现有的更新机制：原地修改文件内容 + 末尾追加更新记录
- 原因：旧的bug解决方案如果被采用会导致二次故障
- 更新后重建该条目的三个索引

### 3.4 实体链接（自动关联）

写入时自动完成：

1. 提取新条目的实体列表
2. 每个实体在 entities.json 中查找关联的其他条目
3. 如果关联条目数 > 0，在新条目末尾自动写入：
```markdown
## 相关条目
- [tech:SQLite] bug/entries/20260423-sqlite-wal-lock.md
- [tech:并发] knowledge/entries/20260420-tech-sqlite-concurrency.md
```
4. 将新条目的 file_path 追加到 entities.json 中对应实体的列表里

这替代了原来基于向量相似度的关联记录（原来只看语义相似，现在通过共享实体关联，能找到语义不相似但逻辑相关的条目）。

## 四、vec.py 命令接口

### 4.1 保留的命令（接口不变，内部实现升级）

#### search

```
# 统一检索（默认：三信号融合，两个子库都搜）
python vec.py search "关键词" --top 5

# 定向检索
python vec.py search "关键词" --store bug --top 3
python vec.py search "关键词" --store knowledge --top 3
```

输出格式（不变）：
```
[0.87] [bug] title | summary | file_path
[0.73] [knowledge] title | summary | file_path
```

内部变更：从单信号向量检索改为三信号融合。

#### read

```
python vec.py read <file_path>
```

不变。读取并输出完整文件内容。不依赖 sentence-transformers（延迟import）。

#### check（去重检查）

```
python vec.py check "title + summary" --threshold 0.9
```

内部变更：去重检查也使用三信号综合分数，不只看向量。
- score > 0.9：DUPLICATE
- score 0.7~0.9：RELATED（提示可能矛盾，需人工判断）
- score < 0.7：NEW

#### index（单文件索引）

```
python vec.py index <file_path>
```

内部变更：同时更新三个索引（向量 + 倒排 + 实体）。

#### index-dir（全量重建）

```
python vec.py index-dir
python vec.py index-dir --store bug
python vec.py index-dir --store knowledge
```

内部变更：
1. 先清理陈旧索引（检查文件是否存在，不存在的删掉）
2. 重建三个索引
3. 输出统计信息

#### remove（删除索引）

```
python vec.py remove <file_path>
```

内部变更：同时从三个索引中移除。

#### list（列出所有索引条目）

```
python vec.py list
python vec.py list --store bug
```

不变。

### 4.2 新增命令

#### init（初始化）

```
python vec.py init
```

首次安装时执行，创建完整目录结构和空词表：

1. 创建 `index/`、`bug/entries/`、`knowledge/entries/` 目录
2. 创建空的索引文件：`index/vectors.pkl`、`index/bm25.json`、`index/entities.json`
3. 创建初始词表文件：
   - `index/terms_tech.txt`：预置基础技术词表（Python、Node.js、Docker、Git、SQLite、React、TypeScript、Claude Code、API、LLM、MCP、RAG 等约50个常见技术名词）
   - `index/terms_project.txt`：空文件，用户自行维护
   - `index/terms_people.txt`：空文件，用户自行维护
4. 检查依赖是否已安装（sentence-transformers、jieba），未安装则输出安装命令提示
5. 输出初始化完成信息和后续使用提示

如果目录已存在（非首次），提示用户已初始化，询问是否要重置（仅重置索引，不删entries）。

#### entities（查看实体索引）

```
# 列出所有实体及其关联条目数
python vec.py entities

# 查看某个实体关联的所有条目
python vec.py entities "SQLite"
```

输出格式：
```
[tech] SQLite (3条关联)
  - bug/entries/20260423-sqlite-wal-lock.md
  - knowledge/entries/20260420-tech-sqlite-concurrency.md
  - knowledge/entries/20260501-tech-sqlite-journal-modes.md

[project] AI Workbench (1条关联)
  - knowledge/entries/20260415-experience-workbench-arch.md
```

#### relate（通过实体查找关联条目）

```
# 给定一个条目，通过实体索引找到所有关联条目
python vec.py relate <file_path>
```

逻辑：读取该条目 → 提取实体 → 在 entities.json 中找到每个实体关联的其他条目 → 去重合并输出

输出格式：
```
关联条目（通过共享实体）：
  [tech:SQLite] knowledge/entries/20260420-tech-sqlite-concurrency.md
  [tech:WAL] knowledge/entries/20260501-tech-sqlite-journal-modes.md
```

## 五、实体提取规则

实体提取是纯规则的，不调LLM。

### 5.1 多词表体系

维护三个词表文件，每行一个词：

**index/terms_tech.txt** — 技术名词、框架、库、语言、工具
```
SQLite
Node.js
Python
TypeScript
Claude Code
Docker
WSL
Git
React
sentence-transformers
jieba
BM25
WAL
API
MCP
LLM
RAG
GraphRAG
...
```

**index/terms_project.txt** — 项目名、模块名（随项目推进自动增长）
```
AI Workbench
虚拟炒股
tennis mini-program
memory-base
multi-agent-mode
xiaodian-workflow
...
```

**index/terms_people.txt** — 人物名（中文名、昵称、代号均可）
```
小电
...
```

词表只用于实体提取时的字符串匹配，不加载进LLM上下文。

### 5.2 提取规则（按优先级）

#### 强规则（高置信度，直接提取，类型自动判定）

- **反引号内容**：`` `src/auth/` `` → type=tech
- **代码标识符模式**：`xxx.py`、`xxx.js`、`xxx.md`、`xxx.ts` → type=tech
- **路径模式**：包含 `/` 或 `\` 的字符串 → type=tech
- **版本号模式**：`Node 20`、`Python 3.12`、`v1.2.3` → type=tech

#### 词表匹配（按词表分配类型）

从 title + summary + 正文中匹配三个词表：
- 命中 terms_tech.txt → type=tech
- 命中 terms_project.txt → type=project
- 命中 terms_people.txt → type=people

同一个词如果出现在多个词表中，取第一个命中的类型（优先级：people > project > tech）。

#### 弱规则（补充提取，类型默认tech）

- **连续大写开头词组**：`Claude Code`、`VS Code` → 可能是技术实体
- **英文缩写（2-6个大写字母）**：`WAL`、`BM25`、`API` → 可能是技术实体

弱规则提取的实体如果不在任何词表中，自动追加到 terms_tech.txt 并标记注释 `# auto`：
```
WAL # auto
```

后续可人工清理或移动到正确的词表。

### 5.3 词表维护规则

- Director 开始新项目时，自动将项目名和模块名追加到 terms_project.txt
- Director 遇到新的人物名时，追加到 terms_people.txt
- 弱规则自动追加的词进 terms_tech.txt，带 `# auto` 标记
- 词表不自动删除条目，只增不减（人工清理除外）

## 六、Windows 兼容性

保留现有的 UTF-8 输出兼容（已在上一轮修复中实现）：

```python
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
```

jieba 的缓存目录设为 `index/jieba_cache/`，避免写入系统临时目录权限问题。

## 七、依赖管理

### 现有依赖（不变）

- sentence-transformers（语义向量化）

### 新增依赖

- jieba（中文分词，用于BM25）

安装命令：
```
pip install jieba --break-system-packages
```

### 延迟import策略

- sentence-transformers：仅在 search、check、index 时 import
- jieba：仅在 search、check、index 时 import
- read、remove、list、entities 命令不触发任何重型依赖加载

## 八、性能要求

- read 命令：< 100ms（纯文件读取，无依赖加载）
- search 命令：< 5s（含模型加载首次会更慢，后续调用 < 2s）
- index 单文件：< 3s
- index-dir 全量重建（100条以内）：< 30s
- entities 命令：< 200ms（纯JSON读取）

## 九、测试验证

重构完成后，按以下顺序验证：

### 测试0：初始化

在一个空的临时目录下执行：
```
python vec.py init
```

预期：
1. 创建 index/、bug/entries/、knowledge/entries/ 目录
2. 创建三个空索引文件和三个词表文件
3. terms_tech.txt 包含约50个预置技术名词
4. terms_project.txt 和 terms_people.txt 为空
5. 输出初始化完成信息

### 测试1：全量重建索引

```
python vec.py index-dir
```

预期：输出三个索引的构建统计（向量N条、倒排M个词、实体K个）。

### 测试2：三信号检索对比

对同一个查询，分别查看三个信号的命中情况。
选一个已有条目，用它的技术关键词搜索，确认三个信号都能命中。

### 测试3：实体索引

```
python vec.py entities
```

预期：输出实体列表及关联条目数。

### 测试4：实体关联查找

```
python vec.py relate <某个已有条目>
```

预期：通过共享实体找到关联条目。

### 测试5：写入 + 自动实体链接

创建一个测试条目，写入后检查：
1. 三个索引都已更新
2. 条目末尾自动生成了相关条目链接
3. entities.json 中新增了该条目的实体记录

### 测试6：去重检查（三信号）

用已有条目的 title+summary 执行 check，确认用综合分判断而非仅向量。

### 测试7：陈旧索引清理

创建测试文件 → index → 删除文件 → index-dir → 确认三个索引都已清理。

### 测试8：read 不加载重型依赖

```
python vec.py read <任意条目>
```

预期：秒级返回，不触发 sentence-transformers 或 jieba 加载。

### 测试9：Windows兼容性

无需设置 PYTHONIOENCODING，直接执行 search，确认中文输出正常。

### 测试10：清理

删除所有测试文件，重建索引，确认索引干净。

## 十、仓库文件

### .gitignore

```
index/
bug/
knowledge/
__pycache__/
*.pyc
```

### README.md

需要包含以下内容（CC自行编写措辞）：

1. 一句话介绍：本地优先的AI Agent知识记忆系统，三信号融合检索（语义+关键词+实体），纯文件系统，零API成本
2. 安装步骤（三步：复制文件→执行init→安装依赖）
3. 依赖说明（sentence-transformers、jieba）
4. 快速开始（init→写入一条→检索→读取）
5. 命令参考（所有命令的一行说明）
6. 词表自定义说明（三个词表的用途和维护方式）
7. 与SKILL.md的关系说明：SKILL.md定义AI Agent如何使用本工具的规范，README定义人类如何安装和维护

README的目标读者是AI Agent（用户把链接甩给Agent让它装），所以步骤要精确到命令级别，不要模糊描述。

## 十一、不在本次范围内

- SKILL.md 的更新（单独处理）
- CLAUDE.md 规则变更（单独处理）
- 扩散激活（二期特性，当前不做）
- LLM事实提取（不做，保持手动/Director写入）
- 外部服务依赖（不引入）