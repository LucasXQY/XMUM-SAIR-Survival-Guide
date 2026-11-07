# 贡献指南 | Contributing

谢谢你愿意分享！每多一份资料，就有一位学弟学妹少走一点弯路。

Thanks for wanting to share! Every file you add saves a junior a bit of pain.

目录 | Contents

1. [欢迎上传 / What to upload](#欢迎上传--what-to-upload)
2. [请勿上传 / What NOT to upload](#请勿上传--what-not-to-upload)
3. [打码规则 / Redaction rules](#打码规则--redaction-rules)
4. [文件命名 / File naming](#文件命名--file-naming)
5. [放在哪里 / Where to put it](#放在哪里--where-to-put-it)
6. [需要一并修改的文件 / Files to update alongside](#需要一并修改的文件--files-to-update-alongside)
7. [如何提交 / How to submit](#如何提交--how-to-submit)
8. [上传前检查清单 / Pre-upload checklist](#上传前检查清单--pre-upload-checklist)
9. [署名 / Credit](#署名--credit)

## 欢迎上传 | What to upload

- 空白往年试卷（只有题目）：期末、期中、小测等
- 教学大纲（syllabus / teaching plan）、第一周的课程介绍
- 作业题目（assignment brief）、实验手册、习题（tutorial sheet）、评分表（rubric）、报告模板
- 自己的笔记、复习总结
- 实验经验、踩坑记录
- 科研、实习、全职、内推码、比赛等机会，以及经验分享（直接在网站的[机会页](https://xmum-sair.github.io/opportunities/)发帖，不用登录）
- 课程考核比例（作业、实验、期中、期末各占多少）

- Blank past papers (questions only): finals, midterms, quizzes, etc.
- Syllabus / teaching plan and week-1 course-intro slides
- Assignment briefs, lab manuals, tutorial sheets, rubrics, report templates
- Your own notes and revision summaries
- Lab tips and lessons learned
- Opportunities (research, internships, jobs, referral codes, competitions) and experience posts (post them on the site's [Opportunities page](https://xmum-sair.github.io/opportunities/), no login)
- Assessment weightings (assignments, labs, midterm, final)

## 请勿上传 | What NOT to upload

- 答案、评分标准（marking scheme）、参考解答，包括括号里填好答案的习题
- 写过的学生答卷、交过的作业、实验报告
- 学生姓名、学号、签名等个人信息
- 老师的私人联系方式（电话、私人邮箱等）
- Moodle 选课密码（enrolment key）、群二维码、会议链接和密码
- 整套课件 PPT（体积大、版权敏感；可以在课程 README 里放网盘链接）。写满自己笔记的课件例外，可作为 Notes 上传
- 教材、出版社的习题集、MIT OCW 等外部公开资源（直接给链接）
- 单个超过 100 MB 的文件（GitHub 不收）

- Answers, marking schemes, model solutions, including tutorial sheets with answers filled in brackets
- Filled-in student scripts, submitted assignments, lab reports
- Student names, IDs, signatures or any other personal data
- Lecturers' private contact details (phone numbers, personal emails, etc.)
- Moodle enrolment keys, group QR codes, meeting links and passcodes
- Full lecture-slide decks (large and copyright-sensitive; link to a cloud drive from the course README instead). Decks covered in your own notes are the exception: they can go in as Notes
- Textbooks, publisher problem sets, MIT OCW and other public resources (just link them)
- Any single file over 100 MB (GitHub rejects it)

原因很简单：避免学术诚信问题，同时保护每个人的个人信息。

Why: to stay clear of academic-integrity problems and to protect everyone's personal data.

## 打码规则 | Redaction rules

有些文件整体很有用，只是夹着几处敏感信息。这种情况不用放弃，打码后再上传。

Some files are useful as a whole but contain a few sensitive bits. Don't drop them: redact, then upload.

用上传表单提交时，机器人还会再查一遍：PDF 里漏掉的个人信息自动涂黑后才放进仓库，Word / PPT 里有个人信息的交给维护者处理。但拖进 GitHub 的原附件任何人都能下载，所以文件上的学号、名字最好先自己涂掉再传；不方便的话发邮件给我们。

With the upload form the bot checks again: personal data you missed in a PDF is blacked out before the file enters the repo, and a Word or PPT file with personal data goes to a maintainer. The attachment itself, though, can be downloaded by anyone on GitHub, so black out student IDs and names yourself before uploading, or email the file to us instead.

**必须打码 | Must be redacted**

- 老师、助教的手机号、微信号、私人邮箱（hotmail / gmail / qq 等）
- Moodle enrolment key、群二维码、Zoom / Teams 链接和密码
- 任何学生的姓名、学号、签名、照片
- 文件属性里的作者名（PDF / Word / PPT 的 metadata）

- Lecturers' and TAs' phone numbers, WeChat IDs, private emails (hotmail / gmail / qq etc.)
- Moodle enrolment keys, group QR codes, Zoom / Teams links and passcodes
- Any student's name, ID, signature or photo
- Author names in file properties (PDF / Word / PPT metadata)

**可以保留 | OK to keep**

- 老师的学校邮箱（`@xmu.edu.my`）和办公室号
- 老师姓名、课程代码、学期
- 学校、学院的公开信息

- Lecturers' university email (`@xmu.edu.my`) and office number
- Lecturer names, course codes, sessions
- Public university / school information

**怎么打码 | How to redact**

- PDF：用真正的"涂黑"（redact）功能，不要只画一个黑框盖上去，文字还在底下能复制出来。Acrobat 的 Redact、PDF-XChange、或者 Python 的 PyMuPDF（`page.add_redact_annot()` + `page.apply_redactions()`）都可以。
- Word / PPT：直接把文字改成 `[已打码 / redacted]`，再另存。
- 图片 / 扫描件：用画图工具涂实色块后另存，不要用半透明或马赛克。
- 清掉文件属性：Word / PPT 用"文件 → 信息 → 检查问题 → 检查文档"；PDF 用 PyMuPDF `doc.set_metadata({})`。
- 打码后自己再打开一遍，全文搜索一下手机号和邮箱，确认搜不到。

- PDF: use a real redaction tool, not a black rectangle drawn on top (the text underneath can still be copied). Acrobat Redact, PDF-XChange, or Python's PyMuPDF (`page.add_redact_annot()` + `page.apply_redactions()`) all work.
- Word / PPT: replace the text with `[已打码 / redacted]` and save a copy.
- Images / scans: paint a solid block in any image editor and save; no translucency or mosaic.
- Strip file properties: Word / PPT via File → Info → Check for Issues → Inspect Document; PDF via PyMuPDF `doc.set_metadata({})`.
- Reopen the file afterwards and search for phone numbers and emails to confirm they are gone.

## 文件命名 | File naming

往年试卷统一命名为：

Past papers follow this pattern:

```
<COURSECODE>_<YYYYMM>_<Assessment>[_SetA]_Question.<ext>
```

- `YYYYMM`：试卷上印的学期，例如 `202204` 表示 2022 年 4 月学期。
- `Assessment`：`Final`、`Midterm`、`Quiz1` 等。
- `_SetA`：有多套卷时才加。

- `YYYYMM`: the session printed on the paper, e.g. `202204` = April 2022 session.
- `Assessment`: `Final`, `Midterm`, `Quiz1`, etc.
- `_SetA`: only if there are multiple sets.

其他文件用同样的前缀，把 `Assessment` 换成内容标签：

Other files use the same prefix with a content label in place of `Assessment`:

```
<COURSECODE>_<YYYYMM>_<Label>.<ext>
```

例子 | Examples:

- `COM107_202204_Final_SetA_Question.pdf`
- `COM108_202109_Quiz1_Question.pdf`
- `COM106_202109_Syllabus.pdf`
- `COM103_202204_Assignment1.pdf`
- `COM103_202204_Lab2_Manual.pdf`
- `COM105_202204_Tutorial3.pdf`
- `EEE312_202209_Report_Template.docx`

常用标签：`Syllabus`、`Course_Intro`、`Assignment1`、`Lab1_Manual`、`Tutorial1`、`Rubric`、`Report_Template`、`Handbook`、`Notes`。不知道学期就写你修这门课的那一学期。

同一学期已经有同名文件时：先打开比较，内容一样就不要再传；不一样就加后缀区分，例如 `COM107_202204_Final_SetB_Question.pdf`、`COM103_202204_Lab2_Manual_v2.pdf`，并在课程 `README.md` 的备注里写一句区别。

Common labels: `Syllabus`, `Course_Intro`, `Assignment1`, `Lab1_Manual`, `Tutorial1`, `Rubric`, `Report_Template`, `Handbook`, `Notes`. If unsure of the session, use the one you took the course in.

If a file with the same name already exists for that session: open and compare first; identical content needn't be uploaded again. If it differs, add a suffix, e.g. `COM107_202204_Final_SetB_Question.pdf` or `COM103_202204_Lab2_Manual_v2.pdf`, and note the difference in the course `README.md`.

## 放在哪里 | Where to put it

路径格式：`<专业>/<COURSECODE>_<Course_Name>/<YYYY-MM>/<子文件夹>/`，例如：

Path format: `<Programme>/<COURSECODE>_<Course_Name>/<YYYY-MM>/<subfolder>/`, for example:

```
EEE/COM107_Circuits_and_Devices/2022-04/Past-Papers/COM107_202204_Final_SetA_Question.pdf
EEE/COM208_Engineering_Mathematics_IV/2021-09/Past-Papers/
EEE/COM208_Engineering_Mathematics_IV/2023-04/Syllabus/
```

- 专业：`EEE/`、`AIT/`、`ROBO/`。代码以 `G`（全校选修）或 `MPU`（马来西亚必修通识课）开头的课所有专业都修，放在 `GE/`；修课记录照样写进你自己专业的时间表，链接指向 `../GE/<课程文件夹>/`。
- 每门课一个文件夹，**所有年份、所有届的资料都放同一个课程文件夹**，不按届分目录。
- 课程文件夹里**按学期分子文件夹**，名字是 `YYYY-MM`（例如 `2022-04`），和文件名里的 `YYYYMM` 一致。学期指资料本身的学期：试卷就是卷子上印的学期，大纲、作业就是发布的那个学期。实在查不到就放 `unknown/`。
- 学期文件夹里再按类型分：`Past-Papers/`、`Syllabus/`、`Assignments/`、`Labs/`、`Tutorials/`、`Handbooks/`、`Notes/`、`Exam-Review/`、`Tips/`，有内容才建。
- 课程文件夹、学期文件夹已存在就直接用；没有才新建。课程名用英文，单词之间用下划线，和大纲上的写法一致。
- **一门课会有很多学期的资料**（不同年级的同学陆续上传），每个学期一个文件夹互不干扰；索引里的「资料学期」会给每个学期文件夹一个链接。
- 上传前先看看同一学期的同类文件是否已经有人传过：内容一样就不用重复传；是另一套（例如 Set B）或版本不同，就在文件名里加区分，见下面的命名规则。
- 课程改了代码（例如 COM204 → EEE220）就按新代码新建文件夹，并在两边的 `README.md` 里互相注明。

- Programme: `EEE/`, `AIT/`, `ROBO/`. Courses whose code starts with `G` (university electives) or `MPU` (Malaysia's compulsory subjects) are taken by every programme and live in `GE/`; your timeline row still goes in your own programme's README, linking to `../GE/<course folder>/`.
- One folder per course: **material from every year and every cohort goes in the same course folder**. No per-cohort folders.
- Inside the course folder, **one subfolder per session**, named `YYYY-MM` (e.g. `2022-04`), matching the `YYYYMM` in the file name. The session is the material's own: for a paper, the session printed on it; for a syllabus or assignment, the session it was issued in. If you really can't tell, use `unknown/`.
- Inside the session folder, split by type: `Past-Papers/`, `Syllabus/`, `Assignments/`, `Labs/`, `Tutorials/`, `Handbooks/`, `Notes/`, `Exam-Review/`, `Tips/`. Create only the ones you fill.
- Reuse the course and session folders if they exist; create them only if they don't. Course names in English, words joined by underscores, spelled as on the syllabus.
- **A course will accumulate material from many sessions** as students from different years upload; each session has its own folder so they never collide, and the index's "Sessions covered" column links to every session folder.
- Before uploading, check whether the same kind of file for that session is already there: identical content needn't be uploaded again; a different set (e.g. Set B) or version gets a distinguishing suffix, see the naming rules below.
- If a course got a new code (e.g. COM204 → EEE220), create a folder under the new code and cross-reference both in their `README.md`.

## 需要一并修改的文件 | Files to update alongside

放好文件只是第一步。为了让别人找得到，请顺手改下面这些文件。按你做的事对号入座，用不到的跳过。

Dropping files in is step one. So that others can find them, also update the files below. Pick the rows that match what you did and skip the rest.

| 你做了什么 / What you did | 改哪里 / Where to edit | 怎么改 / How |
|---|---|---|
| 加了或改了任何文件 / Added or changed any file | `<专业>/README.md` 的"课程索引"表 / the course index in `<Programme>/README.md` | 在仓库根目录运行 `python scripts/update_index.py EEE`，表格自动重生成（文件数、学期链接都会更新）；不想跑脚本就手动改那一行 / Run `python scripts/update_index.py EEE` from the repo root to regenerate the table (counts and session links update automatically), or edit that course's row by hand |
| 往已有课程加了另一个学期的资料 / Added another session's material to an existing course | 新建 `<课程>/<YYYY-MM>/<类型>/` + 你自己的修课时间表 + 课程文件夹里的 `README.md` / a new `<course>/<YYYY-MM>/<type>/` + your own timeline + the course folder's `README.md` | 新建学期文件夹放文件；时间表里加一行你修这门课的学期；课程 README 的学期表里加一行（学期、老师、考核、资料来自）；然后跑一次索引脚本 / Create the session folder for the files; add a row for your session to your timeline; add a row (session, lecturer, assessment, contributed by) to the course README's session table; then run the index script |
| 新建了一门课程 / Added a new course | `<专业>/README.md` 的"修课时间表" / the course-timeline tables in `<Programme>/README.md` | 在你自己的时间表里加一行 `\| 2024-09 \| [CODE](CODE_Name/) \| [Course Name](CODE_Name/) \|`，学期写你实际修读的 `YYYY-MM`；然后跑一次索引脚本，"修课学期"一栏会自动带上 / Add a row `\| 2024-09 \| [CODE](CODE_Name/) \| [Course Name](CODE_Name/) \|` to your own timeline with the session you actually took it in (`YYYY-MM`); then run the index script and the "Taken in" column picks it up |
| 还没有你的时间表 / You have no timeline yet | `<专业>/README.md` 的"修课时间表" | 照 LucasXQY 那张表的格式新加一节 `### <你的昵称>`，按修读学期列出你的课；只想加几门就写进"其他同学" / Add a `### <your nickname>` section in the same format as the LucasXQY table, listing your courses by session; for just a few courses, use "Other contributors" |
| AIT / ROBO 的第一份资料 / First files for AIT or ROBO | `AIT/README.md` 或 `ROBO/README.md` | 照 `EEE/README.md` 的格式加课程索引（带 `<!-- COURSE-INDEX -->` 标记）和修课时间表，然后 `python scripts/update_index.py AIT` / Add a course index (with the `<!-- COURSE-INDEX -->` markers) and a course timeline in the style of `EEE/README.md`, then run `python scripts/update_index.py AIT` |
| 课程换了代码 / A course got a new code | 新旧两个课程文件夹的 `README.md` | 各写一句"2021 入学时为 COM204 / 2025 入学起为 EEE220"互相链接，例子见 `EEE/EEE220_Engineering_Graphics/README.md` / One line in each README cross-linking the other; see `EEE/EEE220_Engineering_Graphics/README.md` |
| 有个机会想分享 / An opportunity to share | 网站[机会页](https://xmum-sair.github.io/opportunities/) / the site's Opportunities page | 点「发布机会」，不用登录；长期条目由维护者写进 [Research-Opportunities.md](Research-Opportunities.md) 的"维护者整理"表 / Press "Post an opportunity", no login; long-running entries go in the "Curated by maintainers" table of Research-Opportunities.md |
| 课程的老师、考核比例、小贴士 / Course lecturer, assessment weighting, tips | 课程文件夹里的 `README.md` / `README.md` inside the course folder | 没有就按下面的模板新建；**每个修读学期一行**，不同学期老师和考核可能不同，不要覆盖别人的行 / Create one from the template below if missing; **one row per session**, since lecturer and assessment can change between sessions; never overwrite someone else's row |
| 想署名 / Want to be credited | [CONTRIBUTORS.md](CONTRIBUTORS.md) | 在你那一届的表里加一行，昵称 / 真名 / 匿名都行，联系方式可留空 / Add a row under your cohort; nickname, name or anonymous, contact optional |
| 规则本身要改 / Changing the rules | 本文件 [CONTRIBUTING.md](CONTRIBUTING.md) 及 [DISCLAIMER.md](DISCLAIMER.md) | 中英文都改，先在 PR 里说明原因 / Change both languages and explain why in the PR |
| 改了总体介绍 / Changed the overview | 根目录 [README.md](README.md) | 目录树、子文件夹列表、链接要和实际一致 / Keep the tree, subfolder list and links in sync with reality |

课程 `README.md` 模板 | Course `README.md` template

```markdown
# <CODE> <Course Name>

每个修读学期一行；有新学期的资料就加一行。One row per session; add a row when you contribute material from a new session.

| 学期 / Session | 老师 / Lecturer | 考核 / Assessment | 资料来自 / Contributed by | 备注 / Notes |
|---|---|---|---|---|
| 2022-04 | [Name] | [e.g. 30% assignments, 20% midterm, 50% final] | [nickname / anonymous] | |
| 2024-09 | [Name] | | | [e.g. Set B paper differs from Set A in Q3] |

- 代码变更 / Code change：[如果这门课换过代码，链接到新旧文件夹 / link old and new folders if the code changed]
- 小贴士 / Tips：[怎么学、考试偏什么 / how to study, what exams lean towards]
```

几个小约定 | A few conventions

- 所有文档都是中文一段、英文一段，改的时候两边都改。
- 不要删别人的内容，补充就好；表格里的占位行 `[Name]` 留着给后来的人。
- 统计数字不用太精确，差一两份没关系，别人能看出"这里有东西"就行。
- 一次 PR 只做一件事（比如"加 COM107 试卷"），方便审核。

- Every document alternates Chinese and English paragraphs; edit both.
- Add, don't delete; leave the `[Name]` placeholder rows for the next person.
- Counts needn't be exact. Off by one or two is fine; the point is to show there is something there.
- One PR per change (e.g. "add COM107 papers") makes review easy.

## 如何提交 | How to submit

- 最简单：用[上传表单](https://github.com/xmum-sair/xmum-sair.github.io/issues/new?template=upload.yml)（需要 GitHub 账号）。选好专业，把文件拖进去就行：可以一次传很多份，可以打成 zip，不同课程、不同类型混在一起也没关系；课程代码、学期、类型是选填的提示。机器人借助 AI 逐个分拣、按上面的规则改名、归位、清元数据、登记到 README 和 CONTRIBUTORS；逐页检查答案和个人信息，PDF 里的个人信息自动涂黑；仓库里已有的同一份文件不重复收。最后以你的名义开一个 PR，拿不准的文件留给维护者看，维护者审核后合并。注意拖进去的原附件任何人都能下载，见上面的[打码规则](#打码规则--redaction-rules)。
- 会用 git：fork 本仓库，添加文件，然后提 Pull Request。PR 标题写清楚课程和内容，例如 `EEE: COM107 2022-04 past papers`。
- 不熟悉 git：直接把文件发到 `xieqiyi@ieee.org`，附上课程代码、学期、你的届，我们帮你上传，并按你的意愿署名。

- Easiest: the [upload form](https://github.com/xmum-sair/xmum-sair.github.io/issues/new?template=upload.yml) (needs a GitHub account). Pick your programme and drop the files in: many at once, zips, and different courses or types mixed together are all fine; course code, session and type are optional hints. The bot, with AI, sorts each file, renames it by the rules above, files it, clears its metadata and registers it in the READMEs and CONTRIBUTORS; it checks every page for answers and personal data, blacks out personal data in PDFs, and skips files the repo already has. It then opens a PR in your name; files it is unsure about are left to a maintainer, who reviews and merges. The attachments themselves can be downloaded by anyone; see [Redaction rules](#打码规则--redaction-rules) above.
- Comfortable with git: fork the repo, add your files, open a pull request. Name the PR after the course and content, e.g. `EEE: COM107 2022-04 past papers`.
- Not familiar with git: email the files to `xieqiyi@ieee.org` with the course code, session and your cohort. We'll upload them for you and credit you the way you prefer.

## 上传前检查清单 | Pre-upload checklist

- [ ] 没有答案、评分标准或参考解答 | No answers, marking schemes or model solutions
- [ ] 学生姓名、学号、签名已尽量涂掉（用上传表单的话，进仓库前机器人还会再查一遍）| Student names, IDs and signatures blacked out where you could (with the upload form, the bot checks again before anything enters the repo)
- [ ] 没有老师的电话或私人邮箱 | No lecturer phone numbers or private emails
- [ ] 没有 Moodle 密码、群二维码、会议链接 | No Moodle keys, group QR codes or meeting links
- [ ] 打码的是真涂黑，文字复制不出来 | Redactions are real: text can't be copied out
- [ ] 文件能正常打开 | The file opens correctly

用 git 自己提交时还要看下面几项；用上传表单的话机器人会做 | When you submit with git, also check these; with the upload form the bot does them:

- [ ] 文件属性里的作者已清空 | File metadata author cleared
- [ ] 放在了正确的课程 / 学期 / 类型文件夹 | It's in the correct course / session / type folder
- [ ] 文件名符合规范 | It follows the naming convention
- [ ] 改了对应的 README 索引 | The matching README index is updated
- [ ] 在 CONTRIBUTORS.md 里署名（可选）| Added yourself to CONTRIBUTORS.md (optional)

## 署名 | Credit

你可以选择匿名，也可以用昵称、真名或年级署名，随时可以修改。我们会记在 [CONTRIBUTORS.md](CONTRIBUTORS.md) 里。

You can stay anonymous or be credited by nickname, name or intake, and change it anytime. Credits live in [CONTRIBUTORS.md](CONTRIBUTORS.md).
