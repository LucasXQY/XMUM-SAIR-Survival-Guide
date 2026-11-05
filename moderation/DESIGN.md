# 评论审核机器人设计 | Comment moderation bot design

2026-11-05 · 适用于本仓库的 Discussions（网站问答与老师页评论）和 Issues（上传表单等）。

For this repository's Discussions (the website's Q&A and lecturer threads) and Issues (the upload form and friends).

## 1. 目的 | Intent

网站上的评论登录 GitHub 就能写、立刻可见。维护者不可能盯着看，所以要一个机器人在几分钟内把明显不该出现的内容收起来：脏话、人身攻击、歧视性称呼，以及政治敏感话题（尤其中国相关）。判断留给人，机器人只做"先收起来、记一笔、等人看"。

Comments on the site are posted by anyone signed in to GitHub and appear at once. Nobody watches the page all day, so a bot hides clearly unacceptable content within minutes: profanity, personal attacks, slurs, and politically sensitive topics (China-related above all). Judgement stays with people; the bot only hides, logs and waits.

## 2. 已定 | Decided

- **只用关键词表**（维护者选择：免费、粗）。误杀和漏判都会有；维护者可以在日志里恢复或补删。
- **分两档**：`hide`（脏话、攻击、歧视、政治敏感）命中就隐藏；`review`（投诉类词，如"性骚扰""抄袭"）不隐藏，只记日志给维护者看，因为这类内容可能是正当反映。
- **词表就是仓库里的文本文件**（`moderation/words/*.txt`，一行一个，`#` 注释），改词表走 PR，不用改代码。
- **动作**：
  - Discussion 评论 / Issue 评论命中 `hide` → 用 GraphQL `minimizeComment(classifier: ABUSE)` 折叠，并在同一串里回复一句双语说明。
  - Discussion 正文或 Issue 正文命中 `hide` → 锁定该串（`lockLockable` / `gh issue lock`），加标签 `moderation`，回复说明。正文无法折叠，锁定能阻止继续发酵，维护者再决定删除。
  - 任何命中（含 `review`）→ 在置顶的「审核记录 | Moderation log」Issue 下追加一条：时间、位置链接、类别、命中词。日志里不复述整段原文，只给链接。
- **跳过机器人**：`github-actions[bot]`、`giscus[bot]`，以及维护者自己（仓库 admin / write 权限的账号不审）。
- **匹配规则**：全部小写；全角转半角；中文词在去掉空白和标点后的文本上做子串匹配（"傻 逼""傻~逼"都算）；英文词按单词边界匹配（`assess` 不会命中 `ass`）。允许表 `allow.txt` 里的词先从文本里去掉再匹配。
- **触发**：`discussion` / `discussion_comment` 的 created、edited，`issues` opened、edited，`issue_comment` created、edited。权限 `discussions: write`、`issues: write`、`pull-requests: write`。
- 没有 pip 依赖，只用标准库和 `gh`。

## 3. 不做 | Not doing

- 不做语义判断（大模型），维护者如以后想要，在 `scan()` 后面加一层即可。
- 不删任何内容；删除是人的决定。
- 不审网站之外的东西，不审 PR 代码评论之外的 PR 内容（PR 评论走 `issue_comment`，顺带审）。

## 4. 文件 | Files

- `moderation/moderation.py`：`load_words()`、`normalize()`、`scan(text) -> [Hit]`、`plan(event) -> [Action]`（纯函数，可测）、`apply(actions)`（调 gh）、CLI `--event PATH [--dry-run]`。
- `moderation/words/{zh_profanity,en_profanity,slurs,attacks,sensitive,review,allow}.txt`
- `moderation/test_moderation.py`：纯 assert，不联网。
- `.github/workflows/moderation.yml`
