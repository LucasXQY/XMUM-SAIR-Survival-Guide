# 评论审核机器人设计 | Comment moderation bot design

2026-11-05 · 适用于本仓库的 Discussions（网站问答）和 Issues（上传表单等）。

For this repository's Discussions (the website's Q&A) and Issues (the upload form and friends).

## 1. 目的 | Intent

网站上的评论登录 GitHub 就能写、立刻可见。维护者不可能盯着看，所以要一个机器人在几分钟内把明显不该出现的内容收起来：脏话、人身攻击、歧视性称呼，以及政治敏感话题（尤其中国相关）。判断留给人，机器人只做"先收起来、记一笔、等人看"。

Comments on the site are posted by anyone signed in to GitHub and appear at once. Nobody watches the page all day, so a bot hides clearly unacceptable content within minutes: profanity, personal attacks, slurs, and politically sensitive topics (China-related above all). Judgement stays with people; the bot only hides, logs and waits.

## 2. 已定 | Decided

- **关键词表打底，Claude 复核**（2026-11-05 只用关键词表；2026-11-06 起维护者接入 Claude API）。关键词命中时请 Claude 给第二意见：`ok` 不折叠（日志里写明，维护者可手动折叠），`hide` 折叠，`human` 或没有答案时按原来的关键词规则。新增 `suspect.txt`（政治话题的宽泛说法、较轻的骂人话）：只在有 Claude 时请它判断，它说 `hide` 才折叠，没有 Claude 时什么都不做。没命中任何词的评论不调用 Claude。模型默认 Claude Haiku 5.5（维护者选择），仓库变量 `CLAUDE_MODEL_MODERATION` 可改；每天最多 100 次（`CLAUDE_DAILY_MODERATION`），计数在 `bot-state` 分支；没有 key、额度用完、出错、Claude 拒答都退回关键词规则。调用代码在 `llm/claude_check.py`。
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

- 不让 Claude 看没有命中关键词的评论（控制费用）；如果漏判多，再考虑扩充 `suspect.txt`。
- 不删任何内容；删除是人的决定。
- 不审网站之外的东西，不审 PR 代码评论之外的 PR 内容（PR 评论走 `issue_comment`，顺带审）。

## 4. 文件 | Files

- `moderation/moderation.py`：`load_words()`、`normalize()`、`scan(text) -> [Hit]`、`plan(event) -> [Action]`（纯函数，可测）、`apply(actions)`（调 gh）、CLI `--event PATH [--dry-run]`。
- `moderation/words/{zh_profanity,en_profanity,slurs,attacks,sensitive,review,allow}.txt`
- `moderation/test_moderation.py`：纯 assert，不联网。
- `.github/workflows/moderation.yml`
