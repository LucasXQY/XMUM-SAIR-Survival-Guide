# 网站设计 | Website design

2026-11-04 · 适用于 https://github.com/xmum-sair/xmum-sair.github.io

本文是网站的设计说明，给实现网站的人读。仓库内容本身的规则见 [CONTRIBUTING.md](../CONTRIBUTING.md)。

This document describes the website for whoever builds it. Rules for the repo's content itself are in [CONTRIBUTING.md](../CONTRIBUTING.md).

## 1. 目的 | Intent

仓库已经有近五百份资料，但在 GitHub 上找东西要一层层点文件夹，不会用 GitHub 的同学直接放弃。网站要做的是三件事：

1. **查**：一个搜索框，输课程代码、课名或老师名就能找到资料，点开即预览或下载。
2. **问**：每门课下面能提问、回答，用 GitHub 账号实名发言，内容存在仓库自己的 Discussions 里。
3. **免责**：每一页都看得到"非官方、学生自发、版权归校方与老师、侵权即删"的声明。

网站不是第二个内容源。所有内容来自仓库里的文件和 markdown，仓库一变网站自动跟着变。

## 2. 目标 / 非目标 / 反目标 | Goals, non-goals, anti-goals

**目标 | Goals**
- 不会用 GitHub 的新生，在手机上也能 30 秒内找到一门课的试卷并下载。
- 维护者除了 push 仓库之外不需要做任何事；网站没有自己的数据库、账号或服务器。
- 零成本：GitHub Pages + GitHub Actions + GitHub Discussions。

**非目标 | Non-goals（这次不做）**
- 不复制文件到网站：预览和下载都指向 GitHub 上的原文件。
- 不做 PDF 正文全文搜索，只搜元数据和文件名。
- 不做中英文切换按钮：和仓库一样，中文一段英文一段同时显示。
- 不做自己的账号系统、匿名发言、点赞排行、私信。
- 不做访问统计、埋点、任何第三方脚本（giscus 除外）。
- 不做"最近更新"动态、RSS、自定义域名、AIT/ROBO 以外的学院。
- 不做上传功能（见第 11 节，第二阶段另议）。

**反目标 | Anti-goals（做成这样就算失败）**
- 网站上出现仓库里没有的内容，或者仓库改了网站没变。
- 任何形式的答案、评分标准、学生姓名学号、老师私人联系方式出现在页面或评论区提示里。
- 需要付费、需要维护者定期手动操作、或依赖某个会倒的小公司服务。
- 页面、提交信息、代码注释里出现任何 AI 工具的署名或"由 AI 生成"字样。

## 3. 约束 | Constraints

- 仓库 377 MB、385 份 PDF、79 docx、15 pptx、3 xlsx，会继续增长。GitHub 的 raw 链接以 `application/octet-stream` + `nosniff` 返回，浏览器只会下载不会内嵌显示，所以 PDF 预览直接用 GitHub 自己的文件页面（`/blob/`）。
- 访客不在中国大陆，GitHub Pages 和 giscus 都可直接访问。
- 已完成的仓库设置：Discussions 已开；Pages 已创建，来源为 GitHub Actions（`build_type: workflow`），地址 `https://xmum-sair.github.io/`；giscus App 已安装到本仓库。
- giscus 需要的 ID（分区以后在 GitHub 上改名不影响，ID 不变）：
  - `data-repo-id`: `R_kgDOQ_iF5g`
  - 课程页用分区 `Q&A`：`DIC_kwDOQ_iF5s4DKajf`
  - 综合问答页用分区 `General`：`DIC_kwDOQ_iF5s4DKaje`
- 网站部署在子路径 `/XMUM-SAIR-Survival-Guide/` 下，所有站内链接必须带这个前缀或使用相对路径。
- 仓库 markdown 文件保持原样，网站构建只读不写。
- 现有 `scripts/update_index.py` 的输出不能变。
- 文档与界面文字一律中英双语，格式沿用仓库的"中文 | English"；页脚保留 `Ciallo～ (∠・ < )⌒☆`。
- 提交信息、PR 描述、页面、代码里都不出现 AI 署名。

## 4. 架构 | Architecture（已定）

纯静态网站。一个 Python 脚本 `site/build.py` 扫描仓库，生成 HTML 和搜索索引到 `_site/`；GitHub Actions 在每次 push 到 `main` 时运行它并部署到 Pages。

```
site/
  DESIGN.md          本文
  build.py           生成器：扫描仓库 → _site/
  templates/         HTML 模板（纯文本，Python 字符串替换即可）
  static/
    style.css        唯一的样式表
    search.js        唯一的脚本（搜索）
.github/workflows/pages.yml   新建
.gitignore                    新建，忽略 _site/
```

- 语言：Python 3.12，标准库 + `markdown`（Python-Markdown，启用 `tables`、`fenced_code`）。不引入其他依赖，不用前端框架、打包器、Node。
- 本地可运行：仓库根目录 `python site/build.py` 生成 `_site/`，用任何静态服务器预览（如 `python -m http.server -d _site`，此时子路径前缀需能通过参数关掉或设为 `/`）。
- 工作流 `pages.yml`：`on: push: branches: [main]`、`pull_request`（只构建不部署，让 PR 里的内容问题在合并前就出现在日志里）、`workflow_dispatch`；步骤 checkout → setup-python → `pip install markdown` → `python site/build.py` → 仅在 `main` 上 `actions/upload-pages-artifact`（`_site`）→ `actions/deploy-pages`。权限 `pages: write`、`id-token: write`，`concurrency: pages`。

## 5. 页面与 URL | Pages and URLs（已定）

所有页面都是目录 + `index.html`，URL 以 `/` 结尾。课程页路径与仓库文件夹路径一致。

| URL | 内容 | 来源 |
|---|---|---|
| `/` | 首页：站名、Ciallo、两句简介、搜索框、三个专业卡片（有资料的课程数、文件数）、入口链接行 | 生成 |
| `/about/` | 仓库介绍 | 根目录 `README.md` 渲染 |
| `/EEE/` `/AIT/` `/ROBO/` | 专业页：课程表 + 修课时间表 + 命名规则 | 专业 `README.md` 渲染，其中 `<!-- COURSE-INDEX -->` 块替换为生成的课程表（见第 6 节） |
| `/EEE/COM107_Circuits_and_Devices/` | 课程页：课程 README、按学期/类型的文件列表、问答区 | 课程 `README.md` + 文件夹扫描 + giscus |
| `/qa/` | 综合问答：不属于某门课的问题（新生、选课、科研、实习） | 模板 + giscus |
| `/research/` | 研究机会 | `Research-Opportunities.md` |
| `/lecturers/` | 教师档案 | `Lecturers.md` |
| `/contributors/` | 贡献者 | `CONTRIBUTORS.md` |
| `/contributing/` | 如何贡献 | `CONTRIBUTING.md` |
| `/disclaimer/` | 免责声明 | `DISCLAIMER.md` |
| `/search.json` | 搜索索引 | 生成 |
| `/404.html` | 找不到页面，给首页和搜索的链接 | 模板 |

每页共有：
- 页头：站名（回首页）、导航 EEE / AIT / ROBO / 问答 / 研究机会 / 更多（教师、贡献者、如何贡献、关于）、GitHub 仓库链接。
- 页脚：一行免责声明（见第 8 节）、免责声明页链接、GitHub 仓库链接、联系邮箱 `xieqiyi@ieee.org`、`Ciallo～ (∠・ < )⌒☆`。
- `<title>` 为"页面名 · XMUM SAIR 生存指南"，`<meta name="description">`，`<meta name="viewport">`，`<html lang="zh-Hans">`。

## 6. 数据来源与解析 | Data model（已定）

扫描规则与 `scripts/update_index.py` 完全一致（可以把它的扫描部分抽成两边共用的模块，但它的输出必须保持不变）：

- 专业目录：`EEE/`、`AIT/`、`ROBO/`。
- 课程目录：专业目录下含 `_` 的子目录，`<CODE>_<Course_Name>`，课名里的 `_` 显示为空格。
- 学期目录：课程目录下匹配 `\d{4}-\d{2}` 或 `unknown` 的子目录；`unknown` 显示为"未知学期 | unknown"。
- 类型目录：固定九种 `Past-Papers, Syllabus, Assignments, Labs, Tutorials, Handbooks, Notes, Exam-Review, Tips`；只统计不以 `.` 开头的文件。
- "修课学期 / Taken in"：从专业 README 的时间表行 `| YYYY-MM | [CODE](…) | …` 读出，正则同 `update_index.py`。
- 老师：课程 README 第一张表的第二列（"老师 / Lecturer"），按行与学期对应；用于搜索索引和课程页展示。
- 每份文件记录：专业、课程代码、课名、学期、类型、文件名、大小、GitHub 预览链接、下载链接。

链接规则：
- 预览（仅 PDF）：`https://github.com/xmum-sair/xmum-sair.github.io/blob/main/<path>`
- 下载（所有文件）：`https://raw.githubusercontent.com/xmum-sair/xmum-sair.github.io/main/<path>`
- docx / pptx / xlsx 只有"下载"按钮。
- 每个课程页有"在 GitHub 上查看文件夹 | View folder on GitHub"链接（`/tree/main/<path>`）。
- 路径中的空格、`#`、`&` 等按 URL 规则转义（仓库里有 `MPU1.1_…` 这类带点的目录和含 `&` 的课名）。

生成的专业课程表列：代码、课程（链到课程页）、修课学期、资料学期、各类型文件数。没有资料的课程仍然有课程页，页面写"⬜ 征集中 / wanted"。

## 7. Markdown 渲染与链接改写 | Rendering repo markdown（已定）

仓库 markdown 里的相对链接要改写成网站或 GitHub 上能点的地址，否则到了网站上全是死链：

| 原链接指向 | 改写为 |
|---|---|
| 另一个有对应页面的 `.md`（如 `CONTRIBUTING.md`、`../EEE/README.md`、`COM110_…/README.md`） | 该页面的站内 URL |
| 课程目录（如 `COM107_Circuits_and_Devices/`） | 课程页 |
| 学期目录或类型目录（如 `2022-04/`、`2022-04/Tutorials/`） | 该课程页内对应学期的锚点 `…/#2022-04`（不论从哪个页面链来） |
| 仓库内的文件 | GitHub `/blob/main/<path>` |
| `http(s)://`、`mailto:`、`#锚点` | 不动 |

其他：
- 专业 README 的 `<!-- COURSE-INDEX -->…<!-- /COURSE-INDEX -->` 整块换成生成的课程表。
- 课程 README 中的占位行（如 `[Name]`、`[YYYY-MM]`）照原样渲染，不特殊处理。
- 表格在窄屏下横向滚动，不截断。

## 8. 免责声明 | Disclaimer（已定）

三处，缺一不可：
1. `/disclaimer/` 页：`DISCLAIMER.md` 全文。
2. 每页页脚一行：
   「本站由厦马学生自发维护，与 XMUM 无官方关联；试卷与课程材料版权归 XMUM 及授课老师，仅作非商业学习用途；如需删除请邮件 `xieqiyi@ieee.org`。| Student-run, not affiliated with XMUM. Copyright in papers and course material belongs to XMUM and the lecturers; shared for non-commercial study only. Takedown: `xieqiyi@ieee.org`.」
3. 每个评论区上方一段：
   「发言需登录 GitHub，用户名公开。请勿张贴答案、评分标准、他人个人信息或老师的私人联系方式。评论保存在本仓库的 GitHub Discussions 中，维护者可以删除。| Sign in with GitHub to post; your username is public. Do not post answers, marking schemes, other people's personal data or lecturers' private contact details. Comments live in this repo's GitHub Discussions and may be removed by the maintainers.」

## 9. 问答 | Q&A with giscus（已定）

- 课程页底部和 `/qa/` 页各嵌一个 giscus `<script>`，属性：`data-repo="xmum-sair/xmum-sair.github.io"`、`data-repo-id="R_kgDOQ_iF5g"`、`data-mapping="specific"`、`data-strict="1"`、`data-reactions-enabled="1"`、`data-emit-metadata="0"`、`data-input-position="top"`、`data-theme="preferred_color_scheme"`、`data-lang="zh-CN"`、`crossorigin="anonymous"`、`async`。
- 课程页：`data-category="Q&A"`、`data-category-id="DIC_kwDOQ_iF5s4DKajf"`、`data-term="<CODE> <Course Name>"`（例：`COM107 Circuits and Devices`）。首次有人评论时 giscus 自动在 Discussions 里建同名讨论。仓库里有多门课同名或只差一个罗马数字（COM108 / COM110 都叫 Engineering Mathematics I，COM204 / EEE220 都叫 Engineering Graphics），所以必须 `data-strict="1"`：giscus 按 term 的哈希精确匹配，不会把评论挂到相近课名的讨论下。代价是课程文件夹改名后旧讨论接不回来，页面会另起新讨论，旧的仍留在 Discussions 列表里；课程代码变更本来就是新建文件夹，不受影响。
- `/qa/` 页：`data-category="General"`、`data-category-id="DIC_kwDOQ_iF5s4DKaje"`、`data-term="综合问答 | General Q&A"`。
- 分区目前沿用 GitHub 默认名（Q&A、General、Announcements…）。维护者随时可在仓库 Settings → Discussions 里改成中文名，嵌入用的是 ID，不受影响。
- 页面上不加任何自己的评论、点赞或统计逻辑。

## 10. 搜索 | Search（已定）

- `search.json`：`{"courses":[{prog, code, name, url, lecturers:[…], sessions:[…], files:n}], "files":[{prog, code, course, session, type, name, path, preview, download}]}`。预计 500 条文件记录，约 100 KB。
- `search.js`：首页搜索框边打边筛，不区分大小写的子串匹配。课程匹配字段：代码、课名、老师；文件匹配字段：代码、课名、学期、类型、文件名。结果先列课程（最多 20 条，显示代码、课名、老师、文件数，点击进课程页），再列文件（最多 50 条，显示课程代码、学期、类型、文件名，带预览/下载按钮）。
- 支持 `/?q=COM107` 这样的链接直接带出结果；专业页和课程页页头放一个小搜索框，提交后跳到 `/?q=…`。
- 不依赖任何库；搜索索引在首次输入时才加载。

## 11. 样式 | Look and feel（已定原则，细节留给实现）

- 一张 `style.css`，系统字体栈，正文宽度上限约 960px，手机优先，`prefers-color-scheme` 自动深浅色。
- 不用 CSS 框架、图标库、网页字体。
- 可访问性基线：语义化标签、表单有 `<label>`、链接文字可读、颜色对比够、键盘可操作。
- 页面风格与仓库一致：朴素、文字为主、双语并排。

## 12. 自检 | Self-check（已定）

`build.py` 跑完必须断言，失败即构建失败：
- 生成的课程页数 = 三个专业下课程目录数。
- `search.json` 中文件条数 = 扫描到的文件总数，且每条的 `path` 在工作树里真实存在。
- 生成的所有 HTML 里，站内链接指向的 `_site/` 文件都存在（相对链接解析后检查）。
- 生成的 HTML 中不含 `Co-Authored`、`Claude`、`Anthropic` 字样。

不写测试框架、不写 fixture；以上断言放在 `build.py` 末尾或 `--check` 参数下即可。

**对不合规内容的处理 | Imperfect content**：网站不能因为一个贡献者的 PR 不完美就停更。构建只在生成器自身出错时失败（上面的断言）；遇到内容问题则降级，并在 Actions 日志里打 `WARNING`：
- markdown 相对链接指向仓库里不存在的页面或路径 → 改写为对应的 GitHub 链接。
- 不符合 `<课程>/<YYYY-MM>/<类型>/` 结构的文件（学期写成 `2024-9`、多出一层目录、第十种类型文件夹）→ 不进索引（与 `update_index.py` 一致）；构建结束时用 `git ls-files` 对比专业目录下的全部文件，把漏掉的逐个 WARNING 列出。
- 课程 README 缺失或第一张表不是约定格式 → 课程页仍生成，老师一栏留空。

## 13. 留给实现者决定 | Left to the builder

- 模板机制（`string.Template`、f-string 或极简自写替换）、文件如何组织。
- 页头导航在手机上的折叠方式；首页卡片和链接行的排版。
- 文件列表内学期的排序（建议新学期在前）、类型的排序（建议按第 6 节的固定顺序）、文件大小显示格式。
- 是否把 `scripts/update_index.py` 的扫描逻辑抽成共用模块。
- `404.html` 文案；`<meta name="description">` 内容。
- Actions 各 action 的版本、Python 小版本。
- Python-Markdown 渲染时 README 中代码块、表格以外的边角情况。

## 14. 第二阶段（本次不做）| Phase 2, not in this build

上传通道的设想，供以后另写设计：用 GitHub Issue 表单做"我要上传资料"。表单必填昵称/入学年、课程代码、学期、老师、资料类型，勾选确认（无答案、无姓名学号、已清元数据、同意免责声明），文件直接拖进 Issue。维护者定期查看，确认后由脚本把文件按命名规则放入仓库、更新课程 README / 时间表 / CONTRIBUTORS、以贡献者的 GitHub 账号作为提交作者开 PR，维护者审核后 merge。全程不需要服务器。网站的"如何贡献"页到时加一个入口即可。

## 15. 第三阶段（2026-11-05 定）| Phase 3

维护者 2026-11-05 的决定与我的实现选择：

- **页头**：一排块（图标 + 中文/英文两行），按重要性排序：三个专业、问答、上传、如何贡献、教师、研究机会、贡献者、关于、GitHub。悬停上浮、当前页高亮、加载淡入；`prefers-reduced-motion` 时全关。右上角一个深浅色切换按钮，选择存 `localStorage`（`theme` = `light` / `dark`），`<head>` 里一段内联脚本在首次绘制前把 `data-theme` 写到 `<html>` 上避免闪烁；不选则跟随系统。切换时同步通知页面里的 giscus iframe（`postMessage setConfig.theme`）。
- **教师页**：`/lecturers/` 先渲染 Lecturers.md（写作规则 + 模板），再列出从各课程 README 学期表里读到的全部老师（逗号分隔的多位老师拆开）。每位老师一页 `/lecturers/<slug>/`：教过的课程与学期（链到课程页锚点），下面是一个 giscus 讨论串（General 分类，term `教师 | Lecturer: <姓名>`），登录即写、立刻可见，由审核机器人按关键词事后折叠（见 moderation/DESIGN.md）。课程页学期标题里的老师名链到老师页。以后课程评价的分数也放这一页。
- **最近上传与订阅**：从 `git log --diff-filter=A` 取每个文件首次入库的日期（pages.yml 用 `fetch-depth: 0`），按（日期、课程、学期、类型）归组。首页显示最近 8 组，`/recent/` 显示最近 100 组，`feed.xml` 是 Atom 订阅；没有 git 历史的树（干跑、临时副本）只给一个告警、列表为空。"来自"取课程 README 该学期的"资料来自"列。
- **征集榜** `/wanted/`：按专业列出还没有任何资料的课程，首页给入口。
- **站点地图**：`sitemap.xml`、`robots.txt`，每页 `<link rel="canonical">`，站点地址常量 `SITE_URL`（迁到组织后改一处）。
- **按学期打包下载**：工作流 `downloads.yml` 在 main 的资料变动后，把每个 `<课程>/<学期>/` 打成 `<CODE>_<学期>.zip`，上传到名为 `downloads` 的 Release（同名覆盖）；课程页每个学期标题旁一个"打包下载"按钮指向 `releases/download/downloads/<CODE>_<学期>.zip`。
- **不做**：离线 PWA（收益小、缓存失效容易出错）；访问统计需要维护者自己注册 GoatCounter 之类的账号后再加一行脚本。
- **仓库迁移**（等维护者建好组织 `xmum-sair`）：转移仓库并改名 `xmum-sair.github.io`，网址变为根路径 `https://xmum-sair.github.io/`；需要改 `REPO`、`SITE_URL`、默认 `--prefix`、giscus 的 `data-repo`、README / CONTRIBUTING / 表单里的链接；仓库 id 与 Discussions 分类 id 不变。旧的 Pages 地址不会自动跳转，旧的仓库地址会。
- **课程评价**（路线 A，待做）：Issue 表单打分（Course / Instructor / Difficulty / Work 四个主维度 + 学到多少 / 沟通 / 找得到老师 / 是否推荐四个细分，各 1–5，不收文字）。机器人读取后把原始投票写进维护者的**私有仓库**（只有维护者可见），按"用户 + 课程 + 老师"去重（后提交覆盖先提交），随后关闭并锁定该 Issue（维护者 2026-11-05 决定不让机器人删除，自己定期手动删；token 只需对私有数据仓库有读写），把汇总（人数、各维度平均；少于 3 人只显示人数）推到公开仓库的 `data` 分支，网站客户端读取 `ratings.json` 渲染在课程页、老师页和 `/reviews/` 总表。Issue 在被维护者删除前是公开的，这是路线 A 的已知边界。
