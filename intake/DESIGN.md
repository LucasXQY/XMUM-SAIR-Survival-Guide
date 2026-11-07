# 上传通道设计 | Upload channel design

2026-11-05 · 适用于 https://github.com/xmum-sair/xmum-sair.github.io · 网站设计见 [site/DESIGN.md](../site/DESIGN.md)

给实现上传通道的人读。仓库内容规则见 [CONTRIBUTING.md](../CONTRIBUTING.md)。

For whoever builds the upload channel. Content rules live in [CONTRIBUTING.md](../CONTRIBUTING.md).

> **2026-11-07 起，文件怎么落地以 [AI-PIPELINE.md](AI-PIPELINE.md) 为准**：每个文件由 Claude 分拣（课程、学期、类型）、检查后各自归位；拿不准的进「需要你看」或 `_待整理/issue-<n>/`，这时 PR 是草稿、状态 `intake/待整理` 不通过；维护者用 `/place`、`/skip`、`/keep`、`/approve`、`/retry` 留言指令处理；AI 结果缓存在 `bot-state` 的 `intake-cache/issue-<n>.json`。表单的课程代码、课程名称、学期、资料类型改为选填。本文 §4–§6 里"一次上传只放一门课、一个学期、一种类型"的做法和末尾「Claude 预检」一节已被取代，其余（下载、解包、清元数据、登记、作者规则、分支即纯函数）照旧。
>
> **Since 2026-11-07, [AI-PIPELINE.md](AI-PIPELINE.md) governs where files go**: Claude sorts (course, session, type) and checks each file, which is then filed on its own; doubtful ones go under "Needs you" or into `_待整理/issue-<n>/`, and the PR is then a draft with a failing `intake/待整理` status; maintainers answer with `/place`, `/skip`, `/keep`, `/approve` and `/retry` comments; AI results are cached on `bot-state` in `intake-cache/issue-<n>.json`. The form's course code, name, session and type are optional. The one-course-one-session-one-type placement of §4–§6 and the closing "Claude pre-check" section are superseded; the rest (download, unpacking, metadata, registration, author rules, the branch as a pure function) stands.

## 1. 目的 | Intent

现在给仓库添资料只有两条路：会 git 的人开 PR，有 push 权限的人直接推。前者把大多数同学挡在门外，后者绕过了审核（2026-11-05 有协作者把 16 份文件直接推到了 main，放错了位置、没有改名、没有登记）。上传通道要做到：

1. **上传者**只需要一个 GitHub 账号：填一张表、把文件拖进去、点提交。不用懂 fork、分支、命名规则。
2. **机器人**把机械活全包了：下载、改名、归位、清元数据、登记到课程 README / 修课时间表 / CONTRIBUTORS、重跑索引、做合规检查，然后以**上传者的身份**开一个 PR。
3. **维护者**隔一阵看一眼 PR 列表：看检查报告，没问题就 merge；有问题就留言或关掉。merge 之后网站自动更新。

全部在 GitHub 内完成：Issue 表单 + GitHub Actions + PR。没有服务器，没有第三方服务。

## 2. 目标 / 非目标 / 反目标 | Goals, non-goals, anti-goals

**目标 | Goals**
- 一个从没用过 GitHub 的同学，注册账号后 5 分钟内能提交一份试卷。
- 维护者审一份上传平均不超过 2 分钟：PR 里有文件清单、检查报告、每份文件的在线预览链接。
- 上传者出现在仓库的 Contributors 里（PR 的提交作者是上传者本人）。
- 任何一份文件都不会被静默丢弃：收不了的文件会在 Issue 下列出原因。

**非目标 | Non-goals（这次不做）**
- 不做自己的网页表单或后端；不支持匿名或无 GitHub 账号上传。
- 不自动 merge；机器人只开 PR。
- 不做内容级的自动打码或 OCR；机器人只标记可疑之处，判断留给维护者。
- 不处理单个超过 25 MB 的文件（GitHub 附件上限）；表单上写明"大文件请拆分或发邮件"。
- 不收 Lecturers.md、Research-Opportunities.md 的内容更新（以后可另做表单）。
- 不做上传进度、通知邮件、排行榜。

**反目标 | Anti-goals（做成这样就算失败）**
- 机器人自己把东西合进 main，或者绕过分支保护。
- PR 的提交作者是机器人而不是上传者。
- 文件被下载到仓库和 Actions 运行器之外的任何地方。
- Issue 正文（不可信输入）被拼进 shell 命令；附件里的路径名能写到目标目录之外。
- 提交信息、PR 正文、代码里出现任何 AI 工具的署名。

## 3. 约束与已验证的事实 | Constraints and verified facts

- **分支保护**（2026-11-05 已开）：main 必须经 PR 修改，管理员也一样，禁止 force push 和删除分支。本通道自身的代码也要走 PR。
- **GitHub 附件**：单文件 25 MB（图片 10 MB）；允许 pdf、docx、pptx、xlsx、zip、txt、md、csv、png、jpg 等。公开仓库的附件链接（`https://github.com/user-attachments/files/<id>/<name>`）无需登录，302 跳转到带签名的下载地址（2026-11-05 用 curl 验证）。
- **Actions 的触发限制**：用 `GITHUB_TOKEN` 创建的 PR 不会触发其他工作流（`pages.yml` 的 PR 构建不会跑）。所以合规检查和 `python site/build.py` 必须在本通道自己的工作流里跑，并把结果写进 PR 正文。
- **仓库设置**：Actions 需要 "Read and write permissions" 且勾选 "Allow GitHub Actions to create and approve pull requests"（Settings → Actions → General → Workflow permissions），否则 `gh pr create` 会被拒绝。这是维护者要确认的设置。
- Python 3.12；依赖只有 `pymupdf`（PDF 元数据与文本）和 `markdown`（跑 `site/build.py` 用）；Office 文件的元数据用标准库 `zipfile` 处理。
- 命名、目录、README 行格式沿用 CONTRIBUTING；双语文案"中文 | English"；不出现 AI 署名。
- Issue 表单的正文由 GitHub 渲染成 `### 字段标题` + 空行 + 值 的段落序列，机器人按标题解析；表单字段标题一旦上线就不要改（改了解析就对不上）。

## 4. 上传者看到的 | What the uploader sees（已定）

入口三处：网站页头"上传 | Upload"按钮、网站"如何贡献"页顶部、仓库 README 和 CONTRIBUTING 的"如何提交"一节。都指向 `https://github.com/xmum-sair/xmum-sair.github.io/issues/new?template=upload.yml`。

表单 `.github/ISSUE_TEMPLATE/upload.yml`，标题前缀 `[上传 | Upload] `，自动打标签 `upload`。字段（标题即解析键，括号内为类型，★ 必填）：

| 字段标题 | 类型 | 说明 |
|---|---|---|
| ★ 专业 \| Programme | dropdown | EEE / AIT / ROBO |
| ★ 课程代码 \| Course code | input | 如 COM107、EEE212、MPU1.1、G0191 |
| ★ 课程名称 \| Course name | input | 试卷或大纲上的英文名，如 Circuits and Devices |
| ★ 学期 \| Session | input | 资料上印的学期，`YYYY-MM`，如 2022-04 |
| ★ 资料类型 \| Type | dropdown | Past-Papers / Syllabus / Assignments / Labs / Tutorials / Handbooks / Notes / Exam-Review / Tips，一次提交只选一种，不同类型分开提交 |
| ★ 文件 \| Files | textarea | 把文件拖进这个框；多份文件可以打成一个 zip。只收 pdf / docx / pptx / xlsx / doc / ppt / xls / txt / md / csv；照片请先合成 PDF |
| 考核名称 \| Assessment（试卷用） | input | 只在类型是 Past-Papers 时填：Final、Midterm、Test 1、Quiz 2… |
| 老师 \| Lecturer | input | 不确定可留空 |
| 考核比例 \| Assessment weighting | input | 如 作业 20%、期中 30%、期末 50% |
| 你修这门课的学期 \| Session you took it | input | `YYYY-MM`；留空表示和资料学期相同。用于专业页的「修课时间表」 |
| ★ 署名方式 \| Credit | dropdown | ① 用我的 GitHub 用户名 / ② 用下面填的昵称 / ③ 匿名。选匿名时课程 README、时间表、CONTRIBUTORS 都写"匿名 / anonymous"，提交作者记为机器人；但 GitHub 上的 Issue 和 PR 仍会显示你的用户名，表单上写明这一点 |
| 昵称 \| Nickname | input | 选②时填 |
| 入学年份 \| Intake year | dropdown | 2019 … 2026，可不选 |
| 备注 / 小贴士 \| Notes | textarea | 写进课程 README 的备注列 |
| ★ 确认 \| Checklist | checkboxes（每项必勾） | ① 没有答案、评分标准、参考解答；② 没有学生姓名、学号、签名，没有老师私人联系方式和 Moodle 密钥；③ 这门课是我自己修的，或我有权分享这些文件；④ 我已读 DISCLAIMER，同意这些文件免费公开、非商业使用 |

表单顶部一段说明：单文件 25 MB 上限；提交后几分钟内机器人会在这个 Issue 下回复一个 PR 链接或者需要补充的信息；维护者审核后合并，网站随即更新。

## 5. 机器人做的 | What the bot does（已定）

**核心原则：PR 分支是 (Issue 内容, 当前 main) 的纯函数。** 同一个 Issue 任何时候重跑，都从当前 main 重新生成整条分支并强制推送。于是：上传者改了表单 → PR 自动跟着变；别的 PR 先合并了 → 所有还开着的上传 PR 自动在新 main 上重建，永远不会出现合并冲突。代价：维护者直接在 PR 分支上手改的内容会在下一次重建时被覆盖，所以要改名、挪位置应让上传者改表单，或者合并后再改。

工作流 `.github/workflows/intake.yml`，三个入口都调用同一个"重建"过程：
- `issues: [opened, edited]`，仅当 Issue 带 `upload` 标签 → 重建该 Issue 的分支和 PR。
- `push: branches: [main]` → 列出所有打开的、分支名以 `upload/issue-` 开头的 PR，逐个重建。
- `workflow_dispatch`，输入 `issue` 编号 → 重建该 Issue（维护者手动兜底）。
`concurrency` 按 Issue 分组（`intake-<n>`；push 触发用 `intake-all`），同一 Issue 只保留最新一次排队。GitHub 每个组只留一个排队位，被挤掉的任务会被静默取消，所以 push 到 main 的那次重建还会扫一遍带 `upload` 标签、既没有 PR 也没有 `needs-info` 的 Issue，补上漏掉的。权限 `contents: write`、`pull-requests: write`、`issues: write`。步骤：checkout（取 main）→ setup-python → `pip install pymupdf markdown` → `python intake/intake.py --event "$GITHUB_EVENT_PATH"`（或 `--issue N` / `--all-open`）→ 把缩略图目录上传为 workflow artifact。

脚本 `intake/intake.py` 对每个 Issue 按顺序：

1. **解析表单**：从 Issue 正文取各字段；`Files` 段里用正则取出所有附件链接（`github.com/user-attachments/files/…`，以及旧格式 `github.com/<owner>/<repo>/files/…`、`user-images.githubusercontent.com/…`）。
2. **校验**：课程代码 `^[A-Z]{1,4}(\d{3,4}|\d\.\d)$`（大写后匹配；通识课 MPU3.1 这类也算）；学期 `^\d{4}-\d{2}$`；类型在九种之内；至少一个附件（只认 `github.com/user-attachments/files/<id>/<name>` 和旧格式 `github.com/<owner>/<repo>/files/<id>/<name>`；图片格式的 `user-attachments/assets/<uuid>` 不认，表单里说明照片请合成 PDF）；署名方式选②时昵称不能为空；四项确认全勾。不通过 → 在 Issue 下用双语列出问题、打标签 `needs-info`、退出 0，不开 PR；若该 Issue 已有 PR，则同时在 PR 下评论并保留旧分支不动。校验通过且带 `needs-info` 标签 → 摘掉标签。
3. **重建而非拒绝**：分支 `upload/issue-<n>` 已存在也照常进行，最后强制推送覆盖；已有 PR 则更新其标题和正文，不新开。
4. **下载**：每个附件下到临时目录，跟随 302，失败重试一次；记录大小。zip 解包：只取文件（忽略目录、`__MACOSX/`、以 `.` 开头的文件），只保留文件名部分（丢弃路径，拒绝含 `..` 的条目），解包后总大小超过 300 MB 或文件数超过 60 即中止并报告。允许的扩展名：pdf、docx、pptx、xlsx、doc、ppt、xls、txt、md、csv；其他文件（含图片）记入"未收录"清单，不放进仓库。
5. **改名**：`<CODE>_<YYYYMM>_<Label>.<ext>`。
   - 一般文件：`Label` = 原文件名去扩展名，非 `[A-Za-z0-9._-]` 的字符换成 `_`，连续 `_` 合并，首尾 `_` 去掉；若原名已以 `<CODE>_<YYYYMM>` 开头则不重复加。
   - 类型为 Past-Papers 且填了考核名称：单个文件 → `<CODE>_<YYYYMM>_<Assessment>_Question.<ext>`；多个文件 → `<CODE>_<YYYYMM>_<Assessment>_<Label>_Question.<ext>`。考核名称同样经过字符清洗（`Test 1` → `Test1`）。
   - 目标路径已存在同名文件 → 在 Label 后加 `_2`、`_3`。
6. **清元数据**：PDF 用 PyMuPDF `set_metadata({})` 后 `save(garbage=3, deflate=True)`；docx/pptx/xlsx 重写 zip，把 `docProps/core.xml` 的 creator、lastModifiedBy、title、subject、keywords、description 和 `docProps/app.xml` 的 Company、Manager 置空，其他条目原样复制。doc/ppt/xls（旧格式）不处理，报告里注明"请维护者手动检查"。
7. **归位**：`<PROG>/<CODE>_<Course_Name>/<session>/<Type>/`。课程目录按 `<CODE>_` 前缀在**三个专业目录和 `GE/` 里**匹配：已有就用已有的，哪怕它在别的专业下（AIT 同学选了 AIT 也归到现有目录，PR 正文说明）；代码以 G 或 MPU 开头的全校公共课一律放 `GE/`（2026-11-06 起），修课时间表那一行写进上传者所选专业的 README，链接 `../GE/<课程文件夹>/`；表单里的课名与目录名不同时在 PR 正文提示。都没有则在所选专业下新建，并按 CONTRIBUTING 的模板生成课程 `README.md`（标题 `# <CODE> <Course Name>`、表头、空的小贴士）。课名转目录名：空格→`_`，去掉 `[^A-Za-z0-9_-]`。
8. **登记**：
   - 课程 README 第一张表：该学期已有行 → 在"资料来自"后追加 ` · <署名>`（已有则不重复），在"备注"后追加 ` · [<Type>](<session>/<Type>/)`（已有则不重复），表单给的老师/考核比例只在原格为空时填入；没有该学期 → 新增一行，按学期顺序插入。表单的"备注"文字追加到备注列。
   - 专业 README 的「其他同学 | Other contributors」表：追加 `| <修读学期> | [<CODE>](<dir>/) | [<Course Name>](<dir>/) | <署名> |`，修读学期取表单"你修这门课的学期"，留空则用资料学期（同一行已存在则跳过）。AIT / ROBO 的 README 目前没有这张表：没有就先按 EEE 的格式创建。
   - CONTRIBUTORS.md：署名在文件里出现过 → 不动（份数由维护者按需更新）；没出现过 → 在对应入学年份小节的占位行上方插入 `| <署名> | <入学年> 入学（<入学年+4> 届）| <n> 份 <CODE> <session> <Type> / <n> <Type> files for <CODE> <session> | |`，没选入学年则放进「其他入学年份」。署名若是 GitHub 用户名则写成 `[login](https://github.com/login)`。
   - 署名方式为匿名：以上三处都写 `匿名 / anonymous`，CONTRIBUTORS 不加行；提交作者用 `github-actions[bot]`，PR 正文和 Issue 评论里不重复提上传者的用户名（GitHub 本身仍会显示 Issue 作者，表单已说明）。
   - 署名、备注等用户文本写进表格前把 `|` 换成 `\|`、去掉换行。
   - 运行 `python scripts/update_index.py <PROG>`。
9. **检查**（结果写进 PR 正文，不阻断）：每份文件一行：大小、页数（PDF）、清理后的元数据是否为空、可疑文本命中（学号 `[A-Z]{3}\d{7,10}`、`Student ID`、非 `@xmu.edu.my` 邮箱、电话号码、enrolment key / passcode / password / zoom / meeting id / wechat / whatsapp）、答案关键词（marking scheme / answer scheme / model answer / suggested answer / solution / answer key / 答案 / 评分标准 / 参考解答）、低文字量（可能是扫描件，提醒肉眼看）。PDF 首页和第二页渲染成缩略图拼成一张图，作为 workflow artifact 上传，PR 正文给出本次运行的链接。最后运行 `python site/build.py --out /tmp/site`，把 `WARNING` 行和是否成功写进报告。
10. **提交与开 PR**：从当前 main 新建（或重置）分支 `upload/issue-<n>`；一次提交，`--author "<login> <<id>+<login>@users.noreply.github.com>"`（Issue 作者的 login 与数字 id 通过 API 取得；匿名时作者为 `github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>`），提交信息 `content: add <CODE> <session> <Type> from #<n>`；`git push --force`；没有 PR 则 `gh pr create`，有则 `gh pr edit` 更新标题正文。标题 `[上传 | Upload] <CODE> <session> <Type>（#<n>）`，正文含：文件清单（原名 → 新路径，每个新路径链到 PR 分支上的文件页，GitHub 可直接预览 PDF）、未收录清单及原因、登记了哪些 README/时间表/CONTRIBUTORS 行、检查报告、维护者勾选清单（看过缩略图 / 没有答案 / 没有个人信息）、重建时间与所基于的 main 提交、`Closes #<n>`。首次开 PR 时在 Issue 下评论 PR 链接并打 `pr-opened`；重建时不另外评论，PR 正文脚注写明重建时间和所基于的 main 提交。
11. **部分失败**：有文件收不了但至少一份成功 → 仍然开 PR，失败的在 PR 正文和 Issue 评论里列明；一份都没成功 → 只评论，不开 PR。脚本任何未预料的异常 → 在 Issue 下评论"机器人出错了，维护者会手动处理"并让工作流失败（红叉能让维护者注意到）。

## 6. 维护者做的 | What the maintainer does（已定）

- 看 PR：清单、报告、缩略图、必要时点开文件预览。
- 需要改名、改学期、改类型：在 Issue 下留言让上传者改表单，机器人会自动重建 PR；或者合并后自己再改。不要直接在 PR 分支上改（下一次重建会覆盖）。
- 合并方式用 **Create a merge commit**（保留上传者为提交作者；squash 会把作者换成合并者）。合并后其余打开的上传 PR 会自动重建，不会冲突。
- 不合规：关闭 PR 并在 Issue 里说明；分支随 PR 自动删除（需开仓库设置，见第 11 节）。
- 要重跑：手动触发 `intake.yml` 并填 Issue 编号即可，不用先关 PR。

## 7. 安全 | Security（已定）

- Issue 正文和附件名都是不可信输入：只经 Python 处理，不拼 shell；文件名只取 basename，拒绝 `..`；zip 条目同样处理；扩展名白名单。
- 总量限制：单次最多 60 份文件、解包后 300 MB；超过即中止并报告。
- 附件只落在运行器的临时目录和仓库分支里；不上传到任何外部服务。
- 工作流只在带 `upload` 标签的 Issue 上运行；Issue 表单自动打该标签，手写的 Issue 不会触发。
- 提交信息、PR 正文、评论里只出现上传者的 GitHub 用户名和他自己填的署名。
- 风险姿态（已定）：解析不可信 PDF / zip 的代码与持有写权限令牌的步骤在同一个 job 里。最坏情况是令牌被用来开垃圾分支、PR 和评论；main 有分支保护，网站只从 main 构建，所以影响可逆。暂不拆成"无权限处理 + 有权限提交"两个 job；如果将来出现滥用，升级路径是把下载、改名、清理、检查放进无权限 job 并以 artifact 交给第二个只负责提交的 job。

## 8. 网站与文档改动 | Site and docs（已定）

- `site/build.py`：页头导航加"上传 | Upload"按钮（指向表单链接），首页"更多"列表和 `/contributing/` 页顶部各加一个入口。
- `CONTRIBUTING.md`「如何提交 | How to submit」：第一条改为"最简单：用上传表单（链接）"，原来的 PR / 邮件方式保留在后面。
- `README.md`「如何贡献」：加一行表单链接。
- `.github/ISSUE_TEMPLATE/config.yml`：`blank_issues_enabled: true`（保留普通 Issue 给删除请求等用途）。

## 9. 自检 | Tests（已定原则）

`intake/test_intake.py`，纯 `assert`，不联网：
- 表单解析：给定一段真实格式的 Issue 正文，字段齐全；缺勾选项时校验报错并给出双语原因。
- 改名：含空格、中文、括号、`’` 的原名；已有前缀的原名；Past-Papers 单文件与多文件；重名加 `_2`。
- zip 解包：忽略目录和 `__MACOSX`，拒绝 `../x.pdf`，超限中止。
- 元数据：对临时生成的 PDF（PyMuPDF 造）和 docx（zipfile 造）清理后读回为空。
- 登记：对 COM107 README 的副本追加同学期行与新学期行；时间表与 CONTRIBUTORS 的插入与去重。
- 端到端干跑：`intake.py --dry-run --form sample.md --files a.pdf b.docx --repo <临时副本>`，不下载、不提交，生成目标目录树与 PR 正文，断言路径、README 行、报告段落存在；之后 `python site/build.py --out <tmp>` 对该副本成功。

## 10. 留给实现者 | Left to the builder

- 各正则的精确写法；PR 正文与 Issue 评论的具体措辞（双语）；标签名的颜色与描述。
- 缩略图拼图的尺寸与每张上限。
- 失败重试策略（下载 302 失败重试一次即可）。
- `intake.py` 的内部结构（建议纯函数 + 一个 `main`，便于测试）。

## 11. 需要维护者操作的设置 | Settings the maintainer must confirm

1. Settings → Actions → General → Workflow permissions：选 "Read and write permissions"，勾 "Allow GitHub Actions to create and approve pull requests"。
2. Settings → General → Pull Requests：勾 "Automatically delete head branches"（只对合并的 PR 生效）；未合并就关闭的上传 PR，由工作流的 `pull_request_target: closed` 任务删掉 `upload/issue-<n>` 分支，被拒的文件不会一直留在公开分支上。
3. 标签 `upload` 必须在上线前手动建好（表单要打这个标签，工作流只认这个标签，脚本自己没机会创建它）；`needs-info`、`pr-opened` 脚本缺失时自动创建。
4. 分支保护已开；本通道的代码将以 PR 方式提交。

## Claude 预检 | Claude pre-check（2026-11-06）

每个上传文件交给 Claude 读一遍（PDF 原样发送，最多前 40 页；其他格式发文字，最多 6 万字符；doc/ppt/xls 旧格式不发），判断有没有答案或学生作答、个人信息（姓名、学号、签名、私人联系方式、Moodle 密钥、二维码）、评分标准，再加一句内容概述。（2026-11-07 起它决定去向，见 [AI-PIPELINE.md](AI-PIPELINE.md) §6：只检查分拣说要收的文件；有个人信息或拿不准、没检查成、只检查了一部分的文件不提交，列在 PR 的「需要你看」里。）

- 结果按上传文件字节的 sha256 缓存在 `bot-state` 分支的 `intake-cache/issue-<n>.json`（PR 关闭后删除）；main 每次更新都会重建所有上传 PR，缓存保证同一个文件只付一次钱。
- 按美元限额，不按文件个数：每个文件先预留 0.04 美元加每页 0.025 美元（PDF 最多按 40 页算），查完按实际花费结算。上传池每天 15、每月 60、每次运行 8 美元（仓库变量 `CLAUDE_USD_DAY_UPLOAD`、`CLAUDE_USD_MONTH_UPLOAD`、`CLAUDE_USD_RUN_UPLOAD` 可改，留空用默认值），记账在 `bot-state` 分支的 `claude-usage.json`；设计细节见 [AI-PIPELINE.md](AI-PIPELINE.md)。额度用完、没有 `ANTHROPIC_API_KEY`、调用失败时，文件不提交，「需要你看」里写明原因，之后的重建或 `/retry` 再试。
- 模型默认 Claude Opus 5.5，仓库变量 `CLAUDE_MODEL_UPLOAD` 可改。Claude 不复述个人信息，只说在哪一页。文件内容视为不可信输入。
- 代码：`intake.py` 的 `precheck_input`、`precheck`、`make_prechecker`；调用与计数在 `llm/claude_check.py`。

