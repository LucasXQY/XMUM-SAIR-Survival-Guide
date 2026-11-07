# XMUM-SAIR-Survival-Guide

Ciallo～ (∠・ < )⌒☆

网页版（搜索、预览、问答）| Website (search, preview, Q&A): https://xmum-sair.github.io/

欢迎来到厦马 SAIR 生存指南！本仓库面向厦门大学马来西亚分校人工智能与机器人学院（School of Artificial Intelligence and Robotics, SAIR）的三个本科专业：电子信息工程（EEE）、人工智能（AIT）、机器人与自动化工程（ROBO）。这些专业课程强度较大、考试较为频繁、学习资源相对有限，本仓库旨在为大家建立一个开放的学习资料共享平台。通过汇集同学们的学习笔记、实验经验、考试复习资料与重点总结，并整理学习建议，实现资源互助与经验传承，帮助更多同学高效学习、顺利备考，取得好成绩，并为未来申请实习与心仪 offer 打下坚实基础。

Welcome to the XMUM SAIR Survival Guide! This repo serves the three undergraduate programmes of XMUM's School of Artificial Intelligence and Robotics (SAIR): Electrical & Electronic Engineering (EEE), Artificial Intelligence (AIT) and Robotics & Automation Engineering (ROBO). They are among the heaviest programmes on campus: lots of courses, frequent exams, and not many shared resources. This repo is an open, student-run place to pool notes, lab experience, revision material and exam-prep summaries, plus study advice. The goal: help each other study smarter, get through exams with good grades, and build a solid base for internships and that dream offer.

## 初衷 | Why this exists

- 在厦马，往年试卷和笔记一直在私下小圈子里流传，甚至被拿来倒卖。
- 能拿到的同学复习有方向，没花钱、没门路的同学只能硬扛——同一门课，起跑线却不一样。
- 我们觉得学习资料不该是付费特权。这里的一切都免费、公开，任何人都能看、都能用。
- 教育公平，从一份公开的空白试卷开始。

- At XMUM, past papers and notes have long circulated in private circles, and some have even been sold between students.
- Students who have them know what to expect; students who did not (or could not) pay are left guessing. Same course, unequal starting line.
- We believe study material should not be a paid privilege. Everything here is free and open to everyone.
- Educational equity can start with something as simple as a public blank past paper.

## 仓库结构 | Repository layout

按专业 → 课程 → 学期组织：每门课一个文件夹，里面按学期（`YYYY-MM`）分子文件夹，所有年份的资料都在同一门课下面；每位贡献者在哪个学期修了哪门课，记在专业 README 的「修课时间表」里。目前资料以 EEE 为主，AIT 和 ROBO 的位置已预留，等同学们加入。代码以 G 或 MPU 开头的全校公共课（选修和马来西亚必修通识课）各专业通用，放在 `GE/`。

Organised by programme → course → session: one folder per course, split into session subfolders (`YYYY-MM`), so material from every year sits under the same course; each contributor's courses are listed by session in the programme README's "Course timeline". Most material so far is EEE; AIT and ROBO folders are ready and waiting for contributors. University-wide courses (codes starting with G or MPU: electives and Malaysia's compulsory subjects) are shared by every programme and live in `GE/`.

```
README.md
DISCLAIMER.md
CONTRIBUTING.md
CONTRIBUTORS.md
Lecturers.md               (教师名录 | lecturer directory)
Research-Opportunities.md  (机会墙的维护者条目 | curated opportunities)
scripts/update_index.py    (重新生成课程索引 | regenerates the course index)
EEE/
  README.md                (课程索引 + 修课时间表 | course index + course timeline)
  COM107_Circuits_and_Devices/
    README.md              (每学期一行：老师、考核、来源 | one row per session)
    2022-04/               (学期 | session)
      Past-Papers/ Syllabus/ Assignments/ …
  COM208_Engineering_Mathematics_IV/
    2021-09/  2022-09/  2023-04/
  …                        (one folder per course, one subfolder per session)
AIT/README.md       (人工智能 | Artificial Intelligence)
ROBO/README.md      (机器人与自动化工程 | Robotics & Automation Engineering)
GE/README.md        (公共课：G 选修 + MPU | university-wide: G electives + MPU)
```

每门课一个文件夹，里面每个学期一个子文件夹，例如 `EEE/COM107_Circuits_and_Devices/2022-04/`，学期文件夹里按需包含：

Each course has its own folder with one subfolder per session, e.g. `EEE/COM107_Circuits_and_Devices/2022-04/`, and a session folder holds any of these that have content:

- `Past-Papers/` — 空白往年试卷 | blank past papers (questions only)
- `Syllabus/` — 教学大纲、课程介绍 | syllabus, teaching plan, course intro
- `Notes/` — 笔记 | notes
- `Assignments/` — 作业题目 | assignment briefs
- `Labs/` — 实验手册、实验指导 | lab manuals and experiment sheets
- `Tutorials/` — 习题课题目 | tutorial question sheets
- `Handbooks/` — 官方指南、模板、评分标准 | official guidelines, templates, rubrics
- `Exam-Review/` — 复习重点 | revision summaries
- `Tips/` — 学习建议、实验经验 | study and lab tips

课程文件夹根目录可放一个 `README.md`（可选）：每个修读学期一行，写老师、考核比例、资料来自谁，外加小贴士。

The course folder itself may hold a `README.md` (optional): one row per session with lecturer, assessment weighting and contributor, plus tips.

## 如何使用 | How to use

- 知道课程代码：直接进 `EEE/<代码>_<课程名>/<学期>/`，或在 [EEE/README.md](EEE/README.md) 的课程索引里点「资料学期」的链接。
- 只记得大概什么时候上的：看 [EEE/README.md](EEE/README.md) 里的修课时间表，按学期（`YYYY-MM`）找课。
- 课程代码会随届变化（比如 Engineering Graphics：2021 入学的同学大一时是 COM204，2025 入学的则是大二的 EEE220），课程 README 里有互相注明；找不到时按课程名全库搜索。
- 在 GitHub 页面按 `T` 可以直接搜文件名。
- 试卷只有题目，没有答案——自己做、和同学讨论、去问老师，才是正确打开方式。

- Know the course code: go straight to `EEE/<CODE>_<Course_Name>/<session>/`, or click a session link in the course index in [EEE/README.md](EEE/README.md).
- Only remember roughly when you took it: use the course timeline in [EEE/README.md](EEE/README.md) and look it up by session (`YYYY-MM`).
- Course codes change between cohorts (e.g. Engineering Graphics was COM204 in Year 1 for the 2021 intake but EEE220 in Year 2 for the 2025 intake); the course READMEs cross-reference each other. If you can't find something, search the whole repo by course name.
- Press `T` on the GitHub repo page to search file names.
- Papers contain questions only, no answers. Work them out yourself, discuss with classmates, ask your lecturer.

## 如何贡献 | How to contribute

- 最简单的上传方式：[上传表单](https://github.com/xmum-sair/xmum-sair.github.io/issues/new?template=upload.yml)（需要 GitHub 账号）：选专业、拖文件就行，机器人用 AI 分拣、改名、归位、打码、查重，并开 PR 等维护者审核。
- 欢迎上传空白试卷、教学大纲、笔记、实验经验、老师风格和考核比例等。
- 文件命名、存放位置、上传前检查清单，详见 [CONTRIBUTING.md](CONTRIBUTING.md)。
- 不会用 git 也没关系，发邮件给我们，我们帮你上传并署名。

- Easiest way to upload: the [upload form](https://github.com/xmum-sair/xmum-sair.github.io/issues/new?template=upload.yml) (needs a GitHub account): pick your programme and drop your files; the bot sorts, renames, files, redacts and de-duplicates them with AI and opens a PR for review.
- Blank past papers, syllabi, notes, lab tips, lecturer styles, assessment weightings: all welcome.
- See [CONTRIBUTING.md](CONTRIBUTING.md) for file naming, folder placement and the pre-upload checklist.
- Not comfortable with git? Email us and we'll upload it for you, with credit.

## 老师与研究机会 | Lecturers & research

- [Lecturers.md](Lecturers.md) — 老师名录：每位老师教过哪些课；评分只在课程页，不收文字评价。
- [Research-Opportunities.md](Research-Opportunities.md) — 维护者整理的科研、实习、全职等机会和科研入门指南；同学可以直接在网站机会页发帖。

- [Lecturers.md](Lecturers.md) — lecturer directory: which courses each lecturer taught; scores live on course pages, no written reviews.
- [Research-Opportunities.md](Research-Opportunities.md) — opportunities curated by the maintainers (research, internships, jobs …) and a getting-started guide; students can post straight on the site's Opportunities page.

## 联系与获取访问 | Contact & access

- 邮箱：`xieqiyi@ieee.org`
- 其他维护者：`[maintainer-email@example.com]`
- 欢迎直接提 Issue 或 Pull Request。
- 找不到想要的资料、想加入成为贡献者、或者有任何问题，都可以发邮件来问。

- Email: `xieqiyi@ieee.org`
- Additional maintainers: `[maintainer-email@example.com]`
- Issues and pull requests are welcome.
- Email us if you need help finding material, want to be added as a contributor, or just have a question.

## 免责声明 | Disclaimer

本仓库为学生自发维护，与厦门大学马来西亚分校无官方关联；试卷版权归学校及相关老师所有，仅供非商业学习交流，只提供空白试卷，禁止倒卖。完整内容见 [DISCLAIMER.md](DISCLAIMER.md)。

This is a student-run project, not affiliated with or endorsed by XMUM. Papers remain the copyright of XMUM and the lecturers, shared for non-commercial study only; blank papers only, no resale. Full text in [DISCLAIMER.md](DISCLAIMER.md).

## 贡献者 | Contributors

感谢每一届愿意分享的同学！名单见 [CONTRIBUTORS.md](CONTRIBUTORS.md)。

Thanks to everyone, from every intake, who chipped in. See [CONTRIBUTORS.md](CONTRIBUTORS.md).

## 同院其他专业 | Other SAIR programmes

- [AIT/](AIT/README.md) — 人工智能，已预留，等待 AIT 同学加入。
- [ROBO/](ROBO/README.md) — 机器人与自动化工程，已预留，等待 ROBO 同学加入。

- [AIT/](AIT/README.md) — Artificial Intelligence, reserved for AIT students.
- [ROBO/](ROBO/README.md) — Robotics & Automation Engineering, reserved for ROBO students.
