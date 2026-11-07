# 小帮手 | The helper

网站右下角的「💬 小帮手」：同学在网站里直接提问，它帮忙找资料、看课程评价、讲知识点、说明怎么用本站。回答带本站页面的链接。

The "💬 小帮手" button on every page: students ask on the site and it finds material, reports course reviews, explains concepts and explains the site, with links to the pages.

## 怎么工作 | How it works

- 网页是静态的，API key 不能放进网页，所以问题先发到一个 Cloudflare Worker（`src/worker.js`），key 只存在 Worker 的 secret 里。
- 第一次提问要过一次 Cloudflare Turnstile 人机验证，之后一小时内不用再验。
- 每个访客每天最多 15 个问题，全站每天最多 150 个（`wrangler.toml` 的 `PER_VISITOR_DAILY`、`GLOBAL_DAILY`）。访客按地址的哈希计数，不存地址本身。
- 先由 Claude Haiku 5.5 判断问题是否和本站、课程、学习有关；无关的直接回一句固定的话，不调用 Opus。
- 有关的由 Claude Opus 5.5 回答，只能用两个工具：在本站搜索（课程、文件和文件里的知识点、老师）和查一门课的信息（学期、资料类型、评价平均分）。不上网。每个问题最多查 4 轮，回答最多 1500 token。
- 不替人做作业、试卷题，不评价老师本人；只回答本站、课程和这里的学习生活。
- 开了 Smart Placement（`wrangler.toml` 的 `[placement]`）：Cloudflare 测出更快时，Worker 改在离 Claude API 更近的机房运行，同学仍然连最近的机房。响应头 `cf-placement` 显示实际位置：`remote-XXX` 表示被挪过，`local-XXX` 表示就地运行。

- The site is static and cannot hold an API key, so questions go to a Cloudflare Worker (`src/worker.js`); the key lives only in the Worker's secrets.
- The first question of a session needs one Cloudflare Turnstile check; the session then lasts an hour.
- 15 questions per visitor and 150 for the whole site per day (`PER_VISITOR_DAILY`, `GLOBAL_DAILY` in `wrangler.toml`). Visitors are counted by a hash, never by their address.
- Claude Haiku 5.5 first checks that the question is about the site, its courses or study; anything else gets a fixed reply and no Opus call.
- Claude Opus 5.5 answers with two tools only: search the site (courses, files and the topics inside them, lecturers) and look up one course (sessions, file types, review averages). No web access. At most 4 tool rounds and 1500 tokens per answer.
- It does not solve homework or exam questions or judge lecturers as people; it stays on this site, its courses and student life here.
- Smart Placement is on (`[placement]` in `wrangler.toml`): when Cloudflare measures it is faster, the Worker runs nearer the Claude API while visitors still connect to their nearest data center. The `cf-placement` response header shows where it ran: `remote-XXX` means moved, `local-XXX` means it ran where the request arrived.

## 第一次设置 | First-time setup

1. 注册 Cloudflare 免费账号（dash.cloudflare.com/sign-up），打开一次 **Workers & Pages**，按提示选一个 `*.workers.dev` 子域名。
2. **Turnstile → Add widget**：名称 `xmum-sair-assistant`；Hostnames 填 `xmum-sair.github.io` 和 `localhost`；模式 **Managed**。记下 Site Key 和 Secret Key。
3. **My Profile → API Tokens → Create Token**，用 **Edit Cloudflare Workers** 模板，记下 token。Account ID 在 Workers & Pages 页面右侧。
4. GitHub 仓库 **Settings → Secrets and variables → Actions**：
   - Secrets：`CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`、`TURNSTILE_SECRET`（`ANTHROPIC_API_KEY` 已经有了）
   - Variables：`TURNSTILE_SITE_KEY`
5. **Actions → assistant → Run workflow**。日志最后会打出 Worker 的地址，形如 `https://xmum-sair-assistant.<子域名>.workers.dev`。
6. 再加一个 Variable：`ASSISTANT_URL` = 上一步的地址，然后 **Actions → pages → Run workflow**。网站右下角就会出现小帮手。

1. Sign up for a free Cloudflare account and open **Workers & Pages** once to pick a `*.workers.dev` subdomain.
2. **Turnstile → Add widget**: name `xmum-sair-assistant`, hostnames `xmum-sair.github.io` and `localhost`, mode **Managed**. Keep the Site Key and Secret Key.
3. **My Profile → API Tokens → Create Token** with the **Edit Cloudflare Workers** template. The Account ID is on the Workers & Pages page.
4. In the repository's Actions settings add secrets `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `TURNSTILE_SECRET` and the variable `TURNSTILE_SITE_KEY`.
5. Run **Actions → assistant**. The log ends with the Worker's address.
6. Add the variable `ASSISTANT_URL` with that address and run **Actions → pages**. The button appears on the site.

## 暂停与费用 | Pausing and cost

- 仓库变量 `BOTS_PAUSED=1` 后，再运行一次 **Actions → assistant** 和 **Actions → pages**：网站上的按钮消失，Worker 只回「暂停中」，不调用模型。
- Cloudflare 免费计划每天 10 万次请求，超出只会报错，不收费。
- Anthropic 的费用：被拦下的问题几乎为零；正常问题大约每个几美分（Opus 5.5，低思考强度，系统提示走缓存）。全站每天 150 个上限，再加上 Console 里设的月度花费上限，就是总闸。
- 美元上限：小帮手每天最多花 2 美元、每月 60 美元（`wrangler.toml` 里的 `HELPER_USD_DAY`、`HELPER_USD_MONTH`，可用同名仓库变量覆盖，在 assistant 工作流里通过 `--var` 传入）。每个问题开始前先预留 0.25 美元，回答完按实际模型和 token 结算多退少补；预留不够就回复额度用完。按次数的上限（全站每天 150、每人每天 15）保留作第二道保险。

- Set the repository variable `BOTS_PAUSED=1`, then run **Actions → assistant** and **Actions → pages**: the button disappears and the Worker answers "paused" without calling any model.
- Cloudflare's free plan allows 100,000 requests a day; beyond that requests fail, nothing is billed.
- Anthropic cost: off-topic questions cost next to nothing; a normal question a few cents (Opus 5.5 at low effort, cached system prompt). The site-wide 150-a-day cap and the monthly spend limit in the Console are the backstops.
- Dollar caps: the helper spends at most 2 USD a day and 60 USD a month (`HELPER_USD_DAY` and `HELPER_USD_MONTH` in `wrangler.toml`, overridden by repository variables of the same name, passed with `--var` in the assistant workflow). Each question reserves 0.25 USD before it starts and is settled against the real model and token usage after the answer; when the reservation does not fit, the reply says the quota is used up. The count caps (150 a day for the site, 15 a day per visitor) stay as a second guard.

## 开发 | Development

```bash
npm ci
npm test
```

本地联调：`npx wrangler dev --port 8787 --var TURNSTILE_SECRET:1x0000000000000000000000000000000AA --var ANTHROPIC_API_KEY:<key>`，再用 `ASSISTANT_URL=http://localhost:8787 TURNSTILE_SITE_KEY=1x00000000000000000000AA python site/build.py` 生成网站（这两个是 Cloudflare 公布的总是通过的测试密钥）。

Local run: start `wrangler dev` as above and build the site with those two variables (Cloudflare's always-pass Turnstile test keys).

## 课程评价 | Course reviews

2026-11-06 起，课程评价也由这个 Worker 处理，不再用 GitHub 表单。

Since 2026-11-06 this Worker also takes the course reviews; the GitHub form is gone.

- 网站 `/rate/` 上直接打分，不用登录。每一票都要过一次 Turnstile 人机验证。
- 同一浏览器对同一门课同一位老师只算一票（浏览器里存一个随机编号），再交一次就是改分。
- 硬上限：同一网络（IP）每天 100 票，同一浏览器每天 20 票。IP 只用于这一条上限，从不把票标成可疑，因为校园 WiFi 下很多同学共用一个地址。地址和浏览器编号都只存加盐哈希。
- 这两种票会被标记「待审」，但照常计入平均分：某门课某位老师一小时内超过 8 票；老师或课程不在网站名单里。名单外的老师名和课程，在你保留之前，网站上只显示「待确认」，免得有人把骂人的话当成名字。
- 管理页：`https://xmum-sair-assistant.xieqiyi.workers.dev/admin`，输入口令（secret `REVIEWS_ADMIN_TOKEN`）后逐个或整组「保留」「丢弃」。每周一工作流 `review-queue` 有待审的票就开 Issue 提醒，审完自动关闭。
- GitHub 表单时期的票在部署时自动导入（可重复，不会重复计票），平均分和人数不变。私有数据仓库留作备份，确认无误后可以删掉。
- 投票存在 Durable Object 的 SQLite 里（`Reviews`），免费计划每天 10 万行写入、5 GB 存储，超出只报错不收费。

- Rate on the site's `/rate/` page with no login; every vote needs one Turnstile check.
- One vote per browser per course and lecturer (a random id in the browser); submitting again changes it.
- Hard caps: 100 votes a day per network (IP) and 20 per browser. The address is used for that cap only and never makes a vote suspicious, since a whole class can share one campus address. Addresses and browser ids are stored as salted hashes.
- Flagged for review but counted: more than 8 votes for one course and lecturer within an hour; a lecturer or course not on the site list. Unlisted names show as "unconfirmed" until you keep one of their votes.
- Admin page at `/admin` on the Worker with the `REVIEWS_ADMIN_TOKEN` secret; the weekly `review-queue` workflow opens an issue while flagged votes wait.
- Votes from the GitHub-form days are imported on every deploy (idempotent).

**设置 | Setup**：在仓库 Secrets 里加 `REVIEWS_ADMIN_TOKEN`（一长串随机字符，自己保存好，管理页要用），然后运行一次 **Actions → assistant**。

Add the `REVIEWS_ADMIN_TOKEN` secret (a long random string you keep for the admin page), then run **Actions → assistant** once.
