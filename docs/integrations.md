# 数据接口与接入预留

除专用签名接入入口与公开健康检查、登录、预览元信息外，`/api` 经营接口要求有效登录会话，并执行相同角色和项目校验。FastAPI提供OpenAPI结构（`/openapi.json`）；字段动态字典由 `/api/schema` 返回。当前未配置任何PMS、OTA、微信、支付或内容平台授权。

- `POST /api/login` / `POST /api/logout` / `GET /api/me`
- `GET /api/preview-info`：公开只读体验开关与演示日期；禁用时仅返回enabled=false，不返回实际经营数据。体验页面路径为 `/preview`，仍使用后端受限演示会话。
- `GET /api/schema`：角色可见的数据类型、字段类型、枚举及可写范围。
- `GET/POST /api/records/{kind}`：列表与新增。写入提供 `dataset, property_id, external_id, data`。
- `PUT /api/records/{kind}/{id}`：更新需要当前 `version`，版本冲突返回409。
- `DELETE /api/records/{kind}/{id}?version=...`：有关联引用时拒绝，关键操作审计留痕。
- `GET /api/dashboard?dataset=...&property_id=...&start=...&end=...&asof=...`：指标、明细、异常、未来房态；空property_id表示授权范围全域。
- `GET /api/order/{id}`：订单及预约、履约、资金、成本、整改等关联记录；财务明细根据角色过滤。
- `GET /api/template/{kind}?format=csv|xlsx`：下载模板。
- `POST /api/import/preview?kind=...&dataset=...&property_id=...&filename=...`：文件原始字节，事务回滚方式预校验，不写业务数据。
- `POST /api/import/commit`：预览返回的批次对象。提交仍会完整校验；重复编号同内容跳过，变更内容拒绝，整批原子提交。
- `GET /api/export/{kind}`：授权范围导出。导出含project/version/updated_at供审计，不是可直接原样重导的模板；字符串以公式符号开头时做CSV公式防护。
- `GET /api/logs`：导入及审计日志。非管理员仅查看本人操作日志。
- `GET/POST /api/users`，`POST /api/users/{id}/disable`：真实集团管理员创建和停用团队账号。

后续平台适配器应将平台稳定订单号/权益号/资金流水号映射为 `external_id`，保留支付、履约和结算三条独立事件。先进行只读对账及映射验证，再通过同一服务校验入库，不能直接绕过接口往records表塞数据。

没有抓取或推断平台私有数据，也不生成所谓「已授权连接」。已实现自定义适配程序凭证与签名投递（见下文）。平台原生webhook验签、专用SDK和自动同步调度仍待确定平台并获得授权后实现。

## 新增管理接口

- `POST /api/alerts/assign`：提交数据集、范围、统计日期、alert_key、项目、负责人和期限；服务端重新计算异常，幂等复用未关闭任务，不能用客户端伪造财务证据。
- `POST /api/account/password`：当前密码校验后更改本人密码，撤销全部原会话；演示会话禁止使用。
- `PUT /api/users/{id}`：集团管理员修改角色、项目范围和启用状态，原会话立即失效。
- 新数据类型 `alert_rule / product / entitlement / touchpoint / sop_item / sop_check / review` 复用已有权限、CRUD、模板、导入与审计接口。SOP不合格会在同一事务中创建整改任务，重复保存复用未关闭任务。
- 导出支持 `start / end`，按记录day或order_date与页面筛选一致；无发生日期的配置台账不做日期裁剪。

当前没有为未确定的平台实现伪造的自动连接状态；接口预留已可被后续经授权的适配器调用。

## 自定义适配程序投递协议（v1.2）

这是本系统定义的入口，不是任何PMS、抖音、携程或支付平台的原生webhook。选择平台后，适配程序仍需获得其授权，将平台字段映射为本系统模板，并执行对账。没有自动抓取或后台定时拉取。

真实集团管理员在「数据中心 → 管理数据接入」创建凭证，选择**当前数据空间**、明确项目、允许投递的数据类型及1—365天有效期。项目基础信息仍由管理员维护，不通过适配器导入。凭证只展示一次，数据库仅保存SHA-256摘要；不提供找回，只能撤销后新建。演示会话和非管理员不能管理凭证。恢复备份后全部旧凭证停用。

- `GET /api/integrations`：凭证元信息与最近100次已验签投递结果，不返回令牌或其摘要。未通过身份/签名验证的请求直接拒绝，不记入业务批次日志。
- `POST /api/integrations`：`name, dataset, properties:[], kinds:[], expires_days`；仅成功创建时返回一次 `token`。
- `POST /api/integrations/{id}/revoke`：立即撤销；重复撤销可安全重试。
- `POST /api/integrations/ingest`：机器身份调用，不使用浏览器Cookie。最大3MB，每批1—500行、同一种业务、同一个项目和数据集，须先创建被关联的订单/合同等记录。SOP不合格仍会在同项目生成整改任务。

请求体示例（完整文件见 `templates/adapter-batch.example.json`）：

```json
{"batch_id":"sample-customer-001","dataset":"demo","property_id":"bhl","kind":"customer","rows":[{"external_id":"SAMPLE-C001","code":"SAMPLE-C001","day":"2026-11-06","owner":"客服","status":"new"}]}
```

每行使用对应CSV模板的字段名与 `external_id`，不接受未知字段。客户仅记录匿名编号及可选手机号末4位。

签名头：

| Header | 内容 |
|---|---|
| Authorization | `Bearer <token>` |
| X-Hotel-Timestamp | 10位Unix秒时间戳，服务端允许正负300秒偏差 |
| X-Hotel-Nonce | 每次请求新生成的16—100位字母/数字/下划线/短横线随机串 |
| X-Hotel-Signature | `HMAC-SHA256(token, timestamp + "." + nonce + "." + 原始请求体字节)` 的小写十六进制 |
| Content-Type | `application/json` |

必须使用HTTPS，并保留证书校验；本地隔离验收使用临时服务。令牌和签名不应出现在URL或日志中。服务端时间应保持同步。

成功返回 `inserted, skipped, replayed`。同凭证、同 `batch_id`、**完全相同请求体字节**可用新nonce重试，返回首次成功结果并标记 `replayed=true`，不再次入库；改空格/字段顺序也视为内容不同，返回409。相同nonce直接409。新批次中的同外部编号、同归一化业务内容跳过；内容变更拒绝，必须由授权人员显式编辑并保留版本和审计，适配器当前不执行自动覆盖更新。

任何行校验失败时整批回滚，但保留已验签失败日志和已用nonce。失败批次未占用batch_id，可更正后用新nonce重试。401代表身份/签名/过期，403代表范围越权，409代表重复签名或编号内容冲突，422代表业务校验失败。遇到超时，应保持相同batch_id与请求体，生成新签名重试；不要把同一流水重新编号。

提供 `scripts/adapter_push.py`：从 `HOTEL_ADAPTER_TOKEN` 环境变量读取凭证，仅接受HTTPS，不跟随重定向，不输出令牌。先通过安全方式为适配程序配置环境变量，再执行：

```bash
python scripts/adapter_push.py https://已确定的实际域名 /映射完成的批次.json
```

先在演示凭证上校验字段映射及重复投递，再为真实空间单独授权。凭证只允许业务数据写入，不能访问管理接口、账号或读取财务明细。它的权限独立于创建管理员的登录会话；不再使用时需在接入管理中显式撤销。


## v1.5 协同与票据采集接口

所有下列接口执行登录、项目、数据集和记录可见性校验。普通员工仅访问本人或被指派事项；协同归档不使用公开文件目录。

- `GET /api/workspace/config`：本机OCR/中文/HEIC/PDF能力与附件限额；不返回密钥。
- `POST /api/workspace/media?dataset=...&property_id=...&filename=...`：原始字节，最多64MB；校验真实文件类型和媒体时长，返回私有附件ID。
- `GET /api/workspace/media/{id}`：授权预览，视频支持Range；`?download=true`下载原件。
- `GET /api/workspace/items?dataset=...&property_id=...&offset=...`：授权提报、汇总和分页，单页100条，未关闭红线优先。
- `GET /api/workspace/items/{id}`：原件、识别建议、指令、反馈及关联整改/费用。
- `POST /api/workspace/items`：kind为inspection或document，提供稳定client_key及本人同项目的media_ids；单据须有照片/PDF/xlsx，可附录音。重复提交不新建。
- `POST /api/workspace/items/{id}/messages`：反馈或管理指令；指令身份仅取登录的CEO/高管角色，附件不允许冒用或跨项目绑定。
- `POST /api/workspace/items/{id}/assign`：管理者指派部门、负责人、期限和严重性，需version。
- `POST /api/workspace/items/{id}/remediation`：负责人提交照片/录音/说明，需version；`/review`由管理者复查，红线禁止整改人自行通过。
- `POST /api/workspace/items/{id}/recognize`：重新识别；原件先归档，后台双工作线程处理，未完成任务在服务启动时恢复。
- `POST /api/workspace/items/{id}/book`：仅财务/集团管理员，确认expense、金额、日期、科目、费用主体及version；生成一次cost，可关联实际订单。原件或已确认票号重复时拒绝跨项目重复计费。
- `POST /api/workspace/items/{id}/archive`：仅财务/集团管理员确认purchase/asset/payment/other分类，需version；不生成cost或payment，移出待确认队列。

FIELD来源的整改记录只通过协同流程修改，普通issue编辑/删除不能绕过原件与复查。单据OCR建议不会自动写财务账、证明付款、鉴定发票真伪或确认全部成本完整。语音目前供回放，不自动转写为会计数据。

GitHub Pages静态模式只返回全新隔离演示库中的样例，拒绝所有实际写入；原件和实际员工资料不放进公开demo目录。
