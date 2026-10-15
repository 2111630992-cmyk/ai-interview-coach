# 第二轮迭代：从 JobPilot 学到的，以及我们做了但 JobPilot 没有的

> 参考项目：[jlifeng/JobPilot](https://github.com/jlifeng/JobPilot)（Apache-2.0）
> —— 免部署桌面端 AI 求职助手（Next.js + Tauri + Rust），141 stars。
>
> 本文记录：读完之后**采纳了什么**、**刻意没采纳什么**、以及**我们做得不一样的地方**。
> 所有判断都基于实际读过它的源码，不是看 README 猜的。

---

## 0. 先说结论：JobPilot 没有视频面试

这一条必须先讲清楚，因为它直接决定了本次迭代的定位。

```bash
# 在 JobPilot 仓库里搜索音视频相关 API
grep -rE "getUserMedia|MediaRecorder|SpeechRecognition|speechSynthesis|AudioContext|whisper|transcri" .
```

结果：

| 位置 | 命中 | 说明 |
|---|---|---|
| `desktop/src/`（整个面试模块） | **0 处** | 面试是**纯打字**的，没有摄像头、没有麦克风、没有语音、没有转写 |
| `src/app/[locale]/linkedin-photo/page.tsx` | 有 | 只用于**拍 LinkedIn 证件照**：`getUserMedia` + `<video>` 预览 + canvas 截图 |

也就是说：**"视频面试 + 真实模拟场景"不是从 JobPilot 搬过来的，是我们自己做的。**
JobPilot 只提供了一个摄像头预览 + 镜像截图的写法参考（`getUserMedia` → `<video>` → canvas `translate` 翻转），
我们把它用在了自视窗上，但音频采集、实时转写、表达指标计算、录像本地存储、回放全是新的。

---

## 1. 采纳的设计（按价值排序）

### 1.1 面试官人格库 ★★★★★

这是 JobPilot 最有价值的设计。它的 `desktop/src/lib/interviewers.ts` 定义了 6 个预设
（`hr` / `technical` / `scenario` / `behavioral` / `project_deep_dive` / `leader`），
每个人格不是"一个提示词字符串"，而是：

```ts
interface InterviewerConfig {
  name, title, avatar,
  bio,           // 背景故事：读过多少份简历、面过多少人
  style,         // 提问风格：怎么追问、不喜欢什么样的回答
  personality,   // 性格：严厉还是温和
  focusAreas,    // 关注点
}
```

**为什么这比"一个通用面试官"好得多**：只有一个面试官的模拟面试，无论提示词写得多好，
都会退化成"一个 AI 在问问题"。有了人格，考生会真的感到"对面换人了"。

**我们的改动**：
- 内容按**大学生秋招**重写。JobPilot 的 `leader` 预设面向资深候选人（"20 年经验、从工程师到 CTO"、
  "管理 200+ 人团队"），对校招生毫无代入感 —— 我们把它换成了**压力面面试官**（终面质疑数据自洽性）。
- 人格同时注入**提问提示词**和**评分提示词**（JobPilot 只影响提问）。
  同一位候选人对 HR 和对技术专家，"好"的定义不一样，评分侧重必须跟着变。
- **环节 ↔ 人格 1:1 映射**，六个环节正好对应六位面试官，且支持"单人整场"模式。
- 换人时 LLM 会**先自报身份再提问**（"我是陈刚，接下来聊聊你的项目部分"），
  否则考生会觉得面试官人格分裂。

实现：`backend/app/interviewers.py`（中英双语）· `backend/app/constants.py::STAGE_INTERVIEWER`

### 1.2 单题即时评分卡 ★★★★★

JobPilot 的 `interview-room.tsx:93-276` 是一个 `AnswerEvaluationCard`：
把五维评分直接渲染在**考生自己的那句话下面**，包含分数胶囊、维度格子、
"面试官可能质疑的点"（琥珀色）、"训练建议"（绿色）、以及一个可折叠的参考答案。

**我们采纳了，但加了一个关键区分**：加了 `feedback_mode`。

| 模式 | 行为 | 适用 |
|---|---|---|
| `practice` 练习模式 | 每答完一题立刻显示评分卡 | 把薄弱点练到能脱口而出 |
| `simulation` 模拟模式（默认） | **全程隐藏分数** | 面试前一周的真实状态演练 |

理由：JobPilot 的做法在"学"的维度上更优（反馈离回答越近越好），
但**真实面试里你不会当场知道自己得几分**。既然本次迭代的目标是"真实模拟面试场景"，
就不该把分数摆在屏幕上 —— 所以做成可选，并把视频面试的默认值设为 `simulation`。

实现：`frontend/src/components/interview/AnswerFeedbackCard.tsx`

### 1.3 回合状态机 + 提示/跳过/标记 ★★★★☆

JobPilot 把一次面试建模成状态机而不是自由聊天：

```ts
type InterviewTurnKind = "start" | "answer" | "hint" | "skip" | "end_round";
```

界面上是四个按钮：请求提示 / 跳过当前题 / 标记上一条 / 结束本轮。

**采纳，并且把"诚实机制"做深了一层**：
- **提示只给回答结构，不给答案**（按环节给不同的结构模板，例如项目题给
  "背景一句 → 我的具体职责 → 2-3 个动作 → 量化结果"）。给答案等于帮他作弊，给结构才是教他怎么想。
- 提示是**只增不减**的：用过一次就永久记录，防止"看完提示再取消勾选"自欺。
- 报告里明确写出 `_honesty: {hint_count, skip_count, marked_count}`。
- **跳过必须写原因**，且记 0 分不中断面试 —— 让学生因一道题卡死而放弃整场是产品设计的失败。

实现：`backend/app/services/interview_service.py::update_turn_tracking / hint_for_stage / skip_current_question`

### 1.4 参考答案的"占位符纪律" ★★★★★

JobPilot 的参考答案生成提示词里有一句非常关键的话（`ai.rs:3651`）：

> 参考回答必须忠于证据；**缺少事实时保留 `[补充具体指标]`、`[补充你的具体职责]` 等占位符，不要猜测**。

**这是我们见过最好的抗幻觉设计**。没有这条约束，模型会顺手编造
"我把 QPS 提升到 5000"这类漂亮但不存在的成绩 —— 那等于教学生编简历，
是这个产品最不能做的事。

**采纳并强化**：把占位符单独抽成 `placeholders: string[]` 字段返回，
界面上用琥珀色框高亮"这些地方需要你补上真实数据（AI 不会替你编）"。
生成结果**缓存进 turn**，同一题永远只花一次模型调用。

实现：`backend/app/services/prompts.py::SUGGESTED_ANSWER_SYSTEM`

### 1.5 人味护栏（反 AI 腔） ★★★★☆

JobPilot 的面试官提示词里（`ai.rs:3348-3370`）有几条我们直接抄了：

- "说话像一个真实、资深的面试官，**不要像 AI 助手**"
- "不使用 emoji，不使用模板化寒暄"
- "每次只提出一个问题，等待候选人完整作答后再回应"
- "**先对候选人的回答做出简短反应**，再继续追问"
- "**不质疑候选人提到的新技术是否存在**" ← 这条最妙

最后一条值得展开：如果考生说了个面试官没听过的技术名词，AI 很容易反问"这是什么"。
真人面试官不会这么干 —— 那会立刻暴露你不是行业里的人。所以要在提示词里
**禁止模型"装懂"式反问**。

实现：`backend/app/services/prompts.py::QUESTION_SYSTEM`

### 1.6 评分隔离与防谄媚 ★★★★☆

JobPilot 的做法：严格 JSON 评分契约 + 固定维度 id + 显式反谄媚指令
（"不要安慰式泛泛评价，不要虚构候选人没说过的细节"），
并且**把面试官自己的追问也喂给评分器**（`ai.rs:3660-3673`）——
分数应该反映真实交锋，而不是孤立判断。

我们没有 JobPilot 那套 skill 体系，但采纳了另外两点：
- 评分提示词里加入**反谄媚 + 拉开区分度**指令（我们在第一轮就有了）；
- 本轮新增：**把面试官实际追问的内容传给评分器**。

实现：`backend/app/services/interview_service.py::advance_turn`（`interviewer_response` 参数）

### 1.7 暂停 / 续做 ★★★☆☆

JobPilot 的 `InterviewSessionStatus` 里有 `"paused"`。

**采纳，并解决了一个它没提的问题**：暂停时长**不计入面试时长**。
否则学生暂停 10 分钟去查资料，回来发现"剩余时间"被吃光了 —— 那这个按钮就是坑。
实现方式是把 `started_at` 整体后移，等价于"这段时间没发生"。

实现：`backend/app/services/interview_service.py::pause_session / resume_session`

### 1.8 暂停时也要能生成报告 ★★☆☆☆

从 JobPilot 的四层降级（runtime-fallback / loading / not-found / "Skill 被删除"阻塞卡）
得到的启发：**任何状态下都不该让用户卡死**。所以我们允许从 `paused` 直接 `finish`。

### 1.9 其余小项

| 采纳项 | 来源 | 我们的实现 |
|---|---|---|
| 分数配色语义（≥80 绿 / ≥60 琥珀 / 否则红） | `interview-room.tsx:74-82` | `lib/constants.ts::scoreTone()`，气泡与报告共用 |
| 面试官配色身份（每人一个色相） | `interviewers.ts:236-251` | `ACCENT_CLASSES`，6 色 |
| 录音时 `REC` 角标 | linkedin-photo 的 `cameraReady` 状态 | `SelfView` 的 REC + 计时 + 麦克风音量条 |
| 镜像画面 | `ctx.translate(canvas.width, 0)` | CSS `scale-x-[-1]`（自视窗必须镜像，否则抬手方向是反的） |
| 卸载时释放摄像头 | `streamRef` cleanup（`:176`） | `useMediaStream` 的 unmount cleanup |

---

## 2. 刻意**没有**采纳的

| JobPilot 的做法 | 为什么不采纳 |
|---|---|
| **每个 turn 都全量重新拉取整个 session**（`refreshSession`） | 40 分钟的面试会产生 40 次全量查询。我们用 SSE 增量推送，只在出错时回源一次 |
| **用哨兵字符串 `[ROUND_COMPLETE]` 控制轮次结束**（`ai.rs:937`） | 靠文本匹配判断状态太脆。我们的轮次推进是确定性纯函数（`interview_engine.decide_next`），可单测 |
| **固定 `h-[520px]` 的转写视口且不自动滚动** | 长回答会被截断且看不到最新内容。我们自动滚到底部 |
| **Skill（可插拔人格包）体系** | 对个人项目是过度设计。6 个内置人格已经覆盖校招场景；真要做也是下一轮的事 |
| **Tauri 桌面端 + OS Keyring 存密钥** | 我们是 Web 应用，密钥在服务端环境变量里。桌面端反而让"秋招现场演示"变麻烦 |
| **`leader` 人格（20 年 CTO 视角）** | 面向资深候选人，对校招生零代入感。替换为压力面面试官 |

---

## 3. 我们做了但 JobPilot 完全没有的

这是本次迭代的主体，也是"视频面试 + 真实模拟场景"的落地。

### 3.1 完整视频面试链路

```
设备检测 → 3-2-1 倒计时 → 摄像头自视窗 + 面试官面板
   → 面试官 TTS 语音提问（面板同步显示"正在说话"波形）
   → 考生对镜头口述，ASR 实时转写（可手工修正）
   → MediaRecorder 录像 → 存进浏览器 IndexedDB
   → 实测语速 / 口头禅占比 / 长停顿 → 随回答上报后端 → 进入评分
   → 结束后报告里逐题回放自己的录像
```

| 能力 | 实现 | 文件 |
|---|---|---|
| 设备检测（预览 + 麦克风音量计 + 设备切换 + 权限说明） | `DeviceCheck` + `useMediaStream` | `components/interview/DeviceCheck.tsx` |
| 摄像头不可用时自动降级为"只录音" | `useMediaStream.start()` 的 fallback | `hooks/useMediaStream.ts` |
| 镜像自视窗 + REC 角标 + 音量条 | `SelfView` | `components/interview/SelfView.tsx` |
| 实时转写（可编辑，识别错误不该由考生背锅） | `useVoiceAnswer` | `hooks/useVoiceAnswer.ts` |
| 录像本地存储（IndexedDB）+ 回放 | `videoStore` + `AnswerPlayback` | `lib/videoStore.ts` |
| 表达指标计算 | `DeliveryTracker` + `computeDeliveryMetrics` | `lib/deliveryMetrics.ts` |

### 3.2 把"表达流畅"从印象变成数字

这是第一轮就存在但一直没解决的问题：模型读一段文字，**既听不出你语速多快，也听不出你卡了几次**。
所以 `delivery` 维度之前只能凭文本长度猜。

现在：前端从 ASR 结果 + 录音时间轴算出客观指标，随回答上报；评分提示词里写死口径：

```
语速低于 180 字/分钟 → 像背稿或思路不清，最高 3.5 分
语速高于 320 字/分钟 → 像赶时间，最高 3.5 分
口头禅占比超过 6%   → 明显影响听感，最高 3 分
长停顿超过 3 次      → 卡壳明显，最高 3 分
纯文字作答           → 不要臆测语速或停顿
```

最后一条同样重要：**没有数据时明确告诉模型"没有数据"，而不是让它编**。

### 3.3 隐私优先的录像策略

**录像永远不上传服务器，只存浏览器 IndexedDB，服务端只记一个 key。**

这是一个刻意的取舍：用"换设备看不到录像"换"录像永远不会泄露"。
上传意味着服务器要存、要备份、要能删干净、要防越权下载、要考虑合规 ——
而这个功能对用户的价值只是"回看自己"。同时提供了按题删除 / 按会话清空的能力。

### 3.4 逐题"下一步会被追问什么"

JobPilot 的评分卡有"面试官可能质疑的点"，是**回溯性**的（"你这句讲得不好"）。
我们新增了 `risk_points`，是**前瞻性**的：

> 你提到成果但没给数字，面试官接下来一定会问「具体提升了多少」。
> 你给了数字，面试官接下来会追问统计口径与对比基线。

对考生更可操作：知道下一句会被打哪儿，才能提前准备。

---

## 4. 迭代后的验证结果

| 门禁 | 迭代前 | 迭代后 |
|---|---|---|
| 后端 pytest | 104 项 | **135 项** |
| 端到端验收（真实 HTTP + SSE） | 39 项 | **85 项** |
| 前后端联调 | 5 项 | 5 项 |
| ruff | 0 问题 | 0 问题 |
| `tsc --noEmit` | 0 错误 | 0 错误 |
| 前端生产构建 | ✅ | ✅（首屏 gzip ≈ 92 kB） |

新增的 E2E 检查覆盖：人格接口、多轮换人、视频配置、表达指标落库与拒绝非法值、
提示（含"给结构不给答案"断言）、标记、跳过、参考答案（含占位符与幂等）、
暂停与时长扣除、报告含表达汇总与面试官标注、诚实计数、练习/模拟模式的评分可见性差异。

---

## 5. 许可与归属

JobPilot 使用 Apache-2.0 许可。我们**没有复制它的任何代码**，
而是重写了面试官人格文案（按秋招场景，中文优先）并重新设计了数据流；
采纳的是**设计思路**（人格库、单题评分卡、回合状态机、占位符纪律、人味护栏）。

按 Apache-2.0 的要求，在此明确标注来源与许可，并在
`backend/app/interviewers.py` 的文件头注明设计参考来源。
