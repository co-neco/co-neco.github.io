# 评论系统迁移操作指引（LeanCloud → Waline）

LeanCloud 将于 **2027-01-12 停止服务**。本目录是把评论区从 MiniValine + LeanCloud
迁到 Waline + Neon Postgres 的工具与步骤。

代码侧改造、数据导出、格式转换、本地端到端验证**已全部完成**。本文档只列**必须由你手动完成**
的部分——这些步骤需要账号授权，无法自动化。

预计耗时 15～20 分钟。

---

## ⚠️ 开始前必读

**在第 5 步之前，不要执行 `hexo deploy` 或推送到部署分支。**

`themes/shoka/_config.yml` 中 `waline.serverURL` 已指向 `https://comment.conecoy.cn`，
而这个后端在你完成部署前并不存在。此时发布会把一个**当前能正常工作**的评论区
（LeanCloud 已解归档）换成一个坏的。

中途随时可以停下——线上站点不受影响，因为你还没发布。

---

## 已经做完的事（无需重做）

- LeanCloud 应用已解归档，API 恢复正常
- 全部数据已导出到 `_leancloud_backup/`（24 条评论 + 28 条阅读量记录）
  - 该目录已 gitignore，**含访客邮箱与 IP，不要提交**
- 已转换为 Waline 格式并在真实 Postgres 中验证通过：`_leancloud_backup/waline_import.sql`
- 主题代码已改造完毕，`hexo generate` 通过，本地浏览器实测评论区、回复嵌套、
  阅读量、侧边栏最近评论均正常

---

## 第 1 步：部署 Waline 后端

1. 打开官方一键部署链接（未登录会要求登录，**用 GitHub 账号**）：

   https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fwalinejs%2Fwaline%2Ftree%2Fmain%2Fexample

2. 填一个项目名（例如 `coneco-comment`），点 **Create**
3. Vercel 会在你的 GitHub 下自动建仓库并部署，等一两分钟出现庆祝动画即成功

此时后端已跑起来，但还没有数据库，接口会报错——正常，下一步解决。

---

## 第 2 步：创建数据库

**不要单独去 Neon 官网注册**，在 Vercel 内部创建即可。

> 注意：Vercel 的 Neon 集成注入的是「前缀 + `_URL`」形式的**整条连接字符串**
> （默认 `STORAGE_URL`），而 Waline 要的是拆开的 `PG_HOST` / `PG_DB` / `PG_USER` /
> `PG_PASSWORD` / `PG_PORT` / `PG_SSL` 六项离散变量，格式对不上。
> 所以第 4 步仍需手工添加这六项——用 `--print-env` 自动拆，不要手拆。

1. 项目页顶部点 **Storage** → **Create Database**
2. 数据库服务选 **Neon** → **Continue**
3. 提示创建 Neon 账号时选 **Accept and Create**
4. 套餐、地区、数据库名都可以不改，一路 **Continue**

> 官方文档此处让你把 `waline.pgsql` 粘进 Neon 的 SQL Editor 建表。**跳过这步**——
> 第 3 步的脚本会连同历史数据一起建表，比手工粘贴可靠。

---

## 第 3 步：导入历史评论

先取连接串：Vercel 项目 → **Storage** → 点进你的数据库 → 找到 `DATABASE_URL`
（或点 **Open in Neon** 到 Neon 面板复制 Connection string），形如：

```
postgres://用户名:密码@ep-xxxx-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
```

在**仓库根目录**执行。连接串通过环境变量传入，不会写进仓库：

```bash
# 安装依赖（仅首次）
cd tools/waline && npm install && cd ../..

# 你的 shell 里设了 NODE_TLS_REJECT_UNAUTHORIZED=0，会让这次数据库连接不校验证书
unset NODE_TLS_REJECT_UNAUTHORIZED

# 填入连接串。行首留一个空格，可避免记入 bash history
 export DATABASE_URL='postgres://用户名:密码@ep-xxxx-pooler....neon.tech/neondb?sslmode=require'

# 先空跑，确认连得上、条数对
node tools/waline/import.mjs --dry-run

# 确认无误后真正导入
node tools/waline/import.mjs
```

**期望输出：**

```
comments      24
replies       16
dangling pid  0
pages/views   24 / 10554

OK
```

**验收标准**：`comments` 必须是 `24`，`dangling pid` 必须是 `0`。
后者非 0 说明回复层级断了，脚本会以非 0 退出码失败并明确提示不要使用该库。

> 脚本带重复导入防护：表中已有数据时会直接拒绝执行，不会把 24 条变成 48 条。
> 确需重来时，在 Neon SQL Editor 执行 `DROP TABLE wl_comment, wl_counter, wl_users;`
> 后重跑，或加 `--force`。

### 备用方案：本机连不上数据库时

企业网络常常封禁出站 5432 端口，或把数据库域名 DNS 劫持到内网地址，表现为：

```
Error: connect ECONNREFUSED 10.x.x.x:5432
```

`10.` / `172.16-31.` / `192.168.` 开头的地址都是内网段，Neon 在公网上，解析到这些地址
即为本地网络问题，与脚本和数据库配置无关。

改走浏览器，完全不需要本机数据库连通性：

```bash
node tools/waline/import.mjs --emit-sql
```

生成 `_leancloud_backup/waline_full_import.sql`（建表语句 + 全部历史数据，约 21KB）。
然后在 Neon 面板左侧 **SQL Editor** 里粘贴该文件全部内容，点 **Run**。

之后在同一个编辑器里执行下面这段核对：

```sql
SELECT
  (SELECT count(*) FROM wl_comment) AS comments,
  (SELECT count(*) FROM wl_comment WHERE pid IS NOT NULL) AS replies,
  (SELECT count(*) FROM wl_comment a WHERE a.pid IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM wl_comment b WHERE b.id = a.pid)) AS dangling,
  (SELECT sum(time) FROM wl_counter) AS views;
```

期望结果：`comments=24`、`replies=16`、`dangling=0`、`views=10554`。

> 该文件含访客邮箱与 IP，位于已 gitignore 的目录，请勿提交或外传。

---

## 第 4 步：补齐环境变量并重新部署

Vercel 项目 → **Settings → Environment Variables**。

先取数据库六项——**不要手工拆连接串**，密码常含 URL 编码字符，手拆易错：

```bash
node tools/waline/import.mjs --print-env
```

把输出的 `PG_HOST` / `PG_PORT` / `PG_DB` / `PG_USER` / `PG_PASSWORD` / `PG_SSL`
六项逐条填入。再添加下面这些：

| 变量 | 取值 | 说明 |
|---|---|---|
| `JWT_TOKEN` | 随机长字符串 | 登录密钥，用 `openssl rand -hex 32` 生成 |
| `SITE_URL` | `https://conecoy.cn` | |
| `SITE_NAME` | `Coneco's diary` | 邮件通知中显示 |
| `SECURE_DOMAINS` | `conecoy.cn` | **建议配置**：限制只有你的站点能调用，防止评论接口被他人滥用 |
| `AUTHOR_EMAIL` | 你的邮箱 | 你的评论显示博主标识，且不给自己发通知 |

可选：

| 变量 | 说明 |
|---|---|
| `DISABLE_REGION` | 设 `true` 则不显示评论者归属地。Waline 会由 IP 推导并展示「广东省」这类信息，MiniValine 原先不显示——按你的隐私取向决定 |
| `SMTP_*` | 邮件通知，见 https://waline.js.org/reference/server/env.html |

**改完必须手动重新部署才生效**：顶部 **Deployments** → 最新一次部署右侧 **Redeploy**。

**验收**：访问

```
https://<你的项目>.vercel.app/api/comment?path=/about/&pageSize=10&page=1
```

应返回 `{"errno":0,...}` 且 `count` 为 `12`。

若报数据库连接错误，加上 `PG_SSL=true`（或 `POSTGRES_SSL=true`）再 Redeploy——
Neon 强制 TLS，而 Waline 该项默认为 false。

---

## 第 5 步：绑定自有域名

`*.vercel.app` 在国内访问不稳定，**必须绑自有域名**，否则等于换个方式坏掉。

1. Vercel 项目 → **Settings → Domains** → 输入 `comment.conecoy.cn` → **Add**
2. 到 DNS 服务商添加记录：

   | 类型 | 主机记录 | 值 |
   |---|---|---|
   | CNAME | `comment` | `cname.vercel-dns.com` |

3. 等待生效（通常几分钟），Vercel 域名状态变为 Valid

**验收**：

```bash
curl -H "Referer: https://conecoy.cn/about/" \
  "https://comment.conecoy.cn/api/comment?path=/about/&pageSize=10&page=1"
```

返回 `{"errno":0,...,"count":12,...}` 即成功。该域名与仓库里已配好的 `serverURL`
一致，**无需改代码**。

> **`-H "Referer: ..."` 不能省。** 配了 `SECURE_DOMAINS` 之后，Waline 会按请求的
> `Referer` 比对白名单，而 curl 默认不发这个头，所以裸 curl 必然返回
> `{"errno":403,"errmsg":"Forbidden"}`——**配置完全正确时也是如此**。
>
> 如何区分是白名单拦截还是别的问题：看响应头有没有 `X-Waline-Version`。
> 有就说明请求已经到达 Waline 应用、服务端和数据库都是活的，403 来自白名单；
> 没有则是 Vercel 层面的拦截（见 Settings → Deployment Protection）。
>
> `SECURE_DOMAINS` 需要**同时包含博客域名和 Waline 服务端域名**，只填博客域名会把
> 自己挡在外面：`conecoy.cn,comment.conecoy.cn`

---

## 第 6 步：注册管理员

访问 `https://comment.conecoy.cn/ui`。

**第一个注册的账号自动成为管理员。** 用你原来评论时的邮箱注册，历史评论即关联到你的身份。

后台可管理评论、给用户设自定义标签（替代原 MiniValine 按邮箱 md5 打标签的
`tagMeta`/`tagMember` 机制）。

---

## 第 7 步：本地确认后再发布

```bash
npx hexo clean && npx hexo server
```

打开 http://localhost:4000/about/ ，滚到评论区逐项确认：

- [ ] 显示 **12 条评论**
- [ ] 回复正确缩进嵌套
- [ ] `@某人` 是链接，点击能跳到对应评论
- [ ] 文章底部阅读量有数字（不是空白）
- [ ] 侧边栏「最近评论」有内容
- [ ] F12 控制台无红色报错
- [ ] 能成功发出一条测试评论（发完去后台删掉）

全部通过后发布：

```bash
npx hexo clean && npx hexo generate && npx hexo deploy
```

建议发布前打标记，方便回退：

```bash
git tag pre-waline-migration
```

---

## 回滚

发布后若线上出问题，`git revert` 主题改动并重新发布即可回到 LeanCloud。
LeanCloud 在 2027-01-12 前仍可用，所以回滚窗口是安全的。

---

## 相关文件

| 路径 | 用途 |
|---|---|
| `py_scripts/leancloud_export.py` | 从 LeanCloud REST API 全量导出，可重跑 |
| `py_scripts/leancloud_to_waline.py` | 转换为 Waline 格式（ID 重映射、路径归一化、`@` 锚点重写） |
| `tools/waline/import.mjs` | 建表 + 导入，含 `--dry-run` / `--print-env` / 重复导入防护 |
| `_leancloud_backup/` | 原始导出与生成的 SQL（**已 gitignore，含邮箱与 IP**） |

`--print-env` 用于手工配置 `PG_*` 变量的场景（例如不走 Vercel 的 Storage 集成、
或改用自建 Postgres），它会把连接串正确拆成 Waline 需要的六项，避免手拆出错。

---

## 已知遗留问题

- **客户端版本**：主题使用 `@waline/client@2`（本地实测 v2.15.8 通过）。官方文档已推荐
  v3，但 v3 未经本项目验证，如需升级请重新走第 7 步的完整核对。
- **2 张 MiniValine 表情图源头已 404**（上游仓库删除了文件），迁移前就是裂图。
  如需清理，在 `leancloud_to_waline.py` 中过滤这些 `<img>` 后重新导入。
- **评论区外观与原先不同**：原皮肤是 548 行针对 `.v*` 类名的定制样式，无法机械移植到
  Waline 的 `.wl-*` 结构。现改为把 Waline 的 CSS 变量映射到 Shoka 调色板
  （`themes/shoka/source/css/_common/components/third-party/waline.styl`），
  配色与暗色模式保持一致。
- **`import.mjs` 的数据库连接层未经真实服务器验证**：它执行的 SQL 已在真实 Postgres
  引擎中完整验证，但 `pg` 客户端连接部分本地无 Postgres 可测（PGlite 的 socket 桥在
  Windows 上崩溃）。故脚本带 `--dry-run` 与重复导入防护，首次执行请先空跑。
