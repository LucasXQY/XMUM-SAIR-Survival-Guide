# 贡献指南 | Contributing

谢谢你愿意分享！每多一份资料，就有一位学弟学妹少走一点弯路。

Thanks for wanting to share! Every file you add saves a junior a bit of pain.

## 欢迎上传 | What to upload

- 空白往年试卷（只有题目）：期末、期中、小测等
- 教学大纲（syllabus / teaching plan）、第一周的课程介绍
- 自己的笔记、复习总结
- 实验经验、踩坑记录
- 老师的教学风格、出题习惯
- 课程考核比例（作业、实验、期中、期末各占多少）

- Blank past papers (questions only): finals, midterms, quizzes, etc.
- Syllabus / teaching plan and week-1 course-intro slides
- Your own notes and revision summaries
- Lab tips and lessons learned
- Lecturers' teaching styles and exam habits
- Assessment weightings (assignments, labs, midterm, final)

## 请勿上传 | What NOT to upload

- 答案、评分标准（marking scheme）、参考解答
- 写过的学生答卷
- 学生姓名、学号、签名等个人信息
- 老师的私人联系方式（电话、私人邮箱等）

- Answers, marking schemes, model solutions
- Filled-in student scripts
- Student names, IDs, signatures or any other personal data
- Lecturers' private contact details (phone numbers, personal emails, etc.)

原因很简单：避免学术诚信问题，同时保护每个人的个人信息。

Why: to stay clear of academic-integrity problems and to protect everyone's personal data.

## 文件命名 | File naming

往年试卷统一命名为：

Past papers follow this pattern:

```
<COURSECODE>_<YYYYMM>_<Assessment>[_SetA]_Question.<ext>
```

- `YYYYMM`：试卷上印的学期，例如 `202204` 表示 2022 年 4 月学期。
- `Assessment`：`Final`、`Midterm`、`Quiz1` 等。
- `_SetA`：有多套卷时才加。

- `YYYYMM`: the intake session printed on the paper, e.g. `202204` = April 2022 session.
- `Assessment`: `Final`, `Midterm`, `Quiz1`, etc.
- `_SetA`: only if there are multiple sets.

例子 | Examples:

- `COM107_202204_Final_SetA_Question.pdf`
- `COM108_202109_Quiz1_Question.pdf`

笔记等其他文件尽量以课程代码开头，名字说清楚内容即可。

For notes and other files, start with the course code and describe the content clearly.

## 放在哪里 | Where to put it

路径格式：`<专业>/<入学年>-<毕业年>/Year-<N>/Semester-<N>/<COURSECODE>_<Course_Name>/<子文件夹>/`，例如：

Path format: `<Programme>/<intake-year>-<graduation-year>/Year-<N>/Semester-<N>/<COURSECODE>_<Course_Name>/<subfolder>/`, for example:

```
EEE/2021-2025/Year-1/Semester-3/COM107_Circuits_and_Devices/Past-Papers/
```

- 子文件夹：`Past-Papers/`、`Syllabus/`、`Notes/`、`Assignments/`、`Exam-Review/`、`Tips/`，有内容才建。
- 可以在课程文件夹里加一个 `README.md`，写授课老师、考核比例和小贴士。
- 先放进你自己那一届的目录（入学年-毕业年，例如 2023 入学就是 `2023-2027/`），没有就新建。各届分开存放，不要放进别的届。

- Subfolders: `Past-Papers/`, `Syllabus/`, `Notes/`, `Assignments/`, `Exam-Review/`, `Tips/`. Create only the ones you fill.
- You can add a `README.md` in the course folder with the lecturer, assessment weighting and tips.
- Put files under your own cohort folder (intake-graduation year, e.g. `2023-2027/` for the 2023 intake); create it if missing. Cohorts stay separate: never put files in another cohort's tree.

## 如何提交 | How to submit

- 会用 git：fork 本仓库，添加文件，然后提 Pull Request。
- 不熟悉 git：直接把文件发到 `xieqiyi@ieee.org`，我们帮你上传，并按你的意愿署名。

- Comfortable with git: fork the repo, add your files, open a pull request.
- Not familiar with git: email the files to `xieqiyi@ieee.org`. We'll upload them for you and credit you the way you prefer.

## 上传前检查清单 | Pre-upload checklist

- [ ] 没有答案、评分标准或参考解答 | No answers, marking schemes or model solutions
- [ ] 没有学生姓名、学号或签名 | No student names, IDs or signatures
- [ ] 没有老师的电话或私人邮箱 | No lecturer phone numbers or private emails
- [ ] 文件能正常打开 | The file opens correctly
- [ ] 放在了正确的文件夹 | It's in the correct folder
- [ ] 文件名符合规范 | It follows the naming convention

## 署名 | Credit

你可以选择匿名，也可以用昵称、真名或年级署名，随时可以修改。我们会记在 [CONTRIBUTORS.md](CONTRIBUTORS.md) 里。

You can stay anonymous or be credited by nickname, name or intake, and change it anytime. Credits live in [CONTRIBUTORS.md](CONTRIBUTORS.md).
