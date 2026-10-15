import {
  ArrowRight,
  BarChart3,
  Camera,
  FileText,
  MessageSquare,
  Mic,
  ShieldCheck,
  Sparkles,
  Users,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { useQuery } from '@tanstack/react-query'

import { listInterviewers } from '../api/endpoints'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Badge } from '../components/ui/feedback'
import { accent } from '../lib/constants'
import { cn } from '../lib/utils'
import { useAuthStore } from '../stores/auth'

const STEPS = [
  {
    icon: FileText,
    title: '1. 传简历 + 贴 JD',
    desc: '解析出你的技能画像，并从岗位描述里抽出这个岗位真正要考的能力点与权重。',
  },
  {
    icon: Camera,
    title: '2. 打开摄像头，面对真人式追问',
    desc: '六位不同风格的面试官轮流提问，会根据你的回答实时追问细节。你的语速、口头禅、停顿都会被实测。',
  },
  {
    icon: BarChart3,
    title: '3. 回看自己的录像，拿到可执行复盘',
    desc: '五维评分 + 逐题点评（附你的原话作为证据）+ 改写示范 + 7 天训练计划。还能回放自己每一题的表现。',
  },
]

const DIFFS = [
  'JD 驱动的能力模型，不是随机题库',
  '自适应追问：有数字就追来源，答得空就追案例',
  '评分必须引用你的原话，不能瞎打分',
  '视频面试全过程不显示分数，保证沉浸感',
  '录像只存在你本机，从不上传服务器',
  '六位面试官轮换，模拟真实校招多轮流程',
]

export function LandingPage() {
  const user = useAuthStore((s) => s.user)
  const primaryTo = user ? '/dashboard' : '/register'

  const interviewers = useQuery({
    queryKey: ['interviewers', 'zh'],
    queryFn: () => listInterviewers('zh'),
    staleTime: 10 * 60_000,
  })

  return (
    <div className="min-h-screen bg-background">
      <header className="mx-auto flex h-16 w-full max-w-6xl items-center px-4">
        <div className="flex items-center gap-2 font-semibold">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-xs font-bold text-primary-foreground">
            AI
          </span>
          秋招面试陪练
        </div>
        <nav className="ml-auto flex items-center gap-2">
          {user ? (
            <Link to="/dashboard">
              <Button size="sm">进入工作台</Button>
            </Link>
          ) : (
            <>
              <Link to="/login">
                <Button variant="ghost" size="sm">
                  登录
                </Button>
              </Link>
              <Link to="/register">
                <Button size="sm">免费开始</Button>
              </Link>
            </>
          )}
        </nav>
      </header>

      {/* ---------- Hero ---------- */}
      <section className="mx-auto w-full max-w-6xl px-4 pb-14 pt-8 sm:pt-14">
        <Badge tone="primary" className="mb-4">
          <Sparkles className="h-3 w-3" aria-hidden />
          面试机会有限，练习不该有限
        </Badge>
        <h1 className="max-w-3xl text-3xl font-bold leading-tight tracking-tight sm:text-4xl md:text-5xl">
          打开摄像头，
          <span className="text-primary">面对一场会追问的视频面试</span>
        </h1>
        <p className="mt-4 max-w-2xl text-base text-muted-foreground sm:text-lg">
          上传简历、粘贴目标岗位 JD，六位不同风格的面试官轮流陪你练一场真实的视频面试。
          25 分钟后，你会拿到五维评分、逐题点评和 7 天训练计划 ——
          以及你自己的录像。
        </p>

        <div className="mt-8 flex flex-wrap gap-3">
          <Link to={primaryTo}>
            <Button size="lg">
              开始第一场视频面试
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Button>
          </Link>
          <Link to="/login">
            <Button size="lg" variant="outline">
              我已有账号
            </Button>
          </Link>
        </div>

        <ul className="mt-8 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {DIFFS.map((item) => (
            <li key={item} className="flex items-start gap-2 text-sm text-muted-foreground">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden />
              {item}
            </li>
          ))}
        </ul>
      </section>

      {/* ---------- 三位面试官预览 ---------- */}
      {interviewers.data && interviewers.data.length > 0 && (
        <section className="border-y border-border bg-secondary/25 py-12">
          <div className="mx-auto w-full max-w-6xl px-4">
            <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="flex items-center gap-2 text-xl font-semibold">
                  <Users className="h-5 w-5 text-primary" aria-hidden />
                  你会遇到六位面试官
                </h2>
                <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                  真实校招是多轮制的：HR 关心动机，技术专家关心原理，主管关心你到底做了什么。
                  换面试官不只是换个名字 —— 提问口径和评分侧重都会跟着变。
                </p>
              </div>
              <Link to="/interview/setup" className="text-sm text-primary underline-offset-4 hover:underline">
                查看全部 →
              </Link>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {interviewers.data.slice(0, 6).map((p) => {
                const tone = accent(p.accent)
                return (
                  <Card key={p.type} className="h-full">
                    <CardHeader>
                      <span className="flex items-center gap-3">
                        <span
                          className={cn(
                            'flex h-10 w-10 items-center justify-center rounded-full text-xl',
                            tone.bg,
                          )}
                          aria-hidden
                        >
                          {p.emoji}
                        </span>
                        <span className="min-w-0">
                          <CardTitle className="truncate">{p.name}</CardTitle>
                          <CardDescription className="truncate">{p.title}</CardDescription>
                        </span>
                      </span>
                    </CardHeader>
                    <CardContent className="flex flex-col gap-2">
                      <p className="line-clamp-3 text-xs leading-6 text-muted-foreground">
                        {p.personality}
                      </p>
                      <div className="flex flex-wrap gap-1">
                        {p.focus_areas.slice(0, 3).map((f) => (
                          <span
                            key={f}
                            className={cn('rounded-full border px-2 py-0.5 text-[10px]', tone.chip)}
                          >
                            {f}
                          </span>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )
              })}
            </div>
          </div>
        </section>
      )}

      {/* ---------- 三步 ---------- */}
      <section className="mx-auto w-full max-w-6xl px-4 py-14">
        <h2 className="mb-6 text-xl font-semibold">三步跑通一次完整练习</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {STEPS.map(({ icon: Icon, title, desc }) => (
            <Card key={title}>
              <CardHeader>
                <span className="flex h-9 w-9 items-center justify-center rounded-md bg-primary/12 text-primary">
                  <Icon className="h-4 w-4" aria-hidden />
                </span>
                <CardTitle className="mt-2">{title}</CardTitle>
                <CardDescription>{desc}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
      </section>

      {/* ---------- 两种模式 ---------- */}
      <section className="border-t border-border py-12">
        <div className="mx-auto grid w-full max-w-6xl gap-6 px-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Camera className="h-4 w-4 text-primary" aria-hidden />
                模拟模式 · 像真的面试
              </CardTitle>
              <CardDescription>默认推荐</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-sm text-muted-foreground">
              <p>· 全程不显示任何分数，你只能像真实面试一样"不知道对方怎么想"</p>
              <p>· 面试官语音提问，你对着镜头口述回答</p>
              <p>· 录下你自己的表现，结束后可以逐题回看</p>
              <p>· 实测语速、口头禅占比、长停顿次数</p>
              <p className="pt-1 text-foreground">适合：面试前一周的真实状态演练</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-primary" aria-hidden />
                练习模式 · 当场学
              </CardTitle>
              <CardDescription>反馈来得越快，改得越快</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-sm text-muted-foreground">
              <p>· 每答完一题，评分直接贴在你那句话下面</p>
              <p>· 五维得分 + 你被扣分的那句原话 + 改写示范</p>
              <p>· 还会告诉你"就凭这句话，面试官下一步会追什么"</p>
              <p>· 可以随时点"看参考答案"（缺数据的地方会留占位符，不会替你编）</p>
              <p className="pt-1 text-foreground">适合：把某个薄弱点练到能脱口而出</p>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* ---------- 诚实说明 ---------- */}
      <section className="border-t border-border bg-secondary/30 py-12">
        <div className="mx-auto grid w-full max-w-6xl gap-6 px-4 md:grid-cols-2">
          <div>
            <h2 className="text-xl font-semibold">关于评分，我们保持诚实</h2>
            <p className="mt-2 text-sm leading-7 text-muted-foreground">
              AI 评分存在主观漂移，我们不会假装它等同于真实面试结果。为了让它尽量可信，
              我们做了四件事：出题与评分拆成两次独立调用；每个分数必须附带你的原话作为证据；
              使用固定锚点的 1-5 分 rubric；视频面试时把语速、口头禅、停顿这些
              <strong className="text-foreground">客观数字</strong>一起喂给评分模型，
              而不是让它凭阅读感受猜"表达流畅不流畅"。
            </p>
            <p className="mt-2 text-sm leading-7 text-muted-foreground">
              它最适合用来做<strong className="text-foreground">结构与表达的刻意练习</strong>，
              以及发现"你以为是细节、其实面试官听不出你的贡献"这类问题。技术正确性还得自己把关。
            </p>
            <p className="mt-2 text-sm leading-7 text-muted-foreground">
              还有一个我们没做但应该做的事：<strong className="text-foreground">评分一致性的人工校准</strong>。
              取 20 份真实问答人工按同一标准打分，算相关性 —— 这是下一步的计划。
            </p>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Mic className="h-4 w-4 text-primary" aria-hidden />
                隐私与合规
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-sm text-muted-foreground">
              <p>· 摄像头与麦克风数据只在你本机处理，<strong className="text-foreground">录像不上传服务器</strong>。</p>
              <p>· 只有语音转写后的文字会发给服务器用于评分，你可以随时修改识别结果。</p>
              <p>· 面试官不会询问或推断年龄、性别、婚育、籍贯、民族、宗教、健康、家庭背景。</p>
              <p>· 评分维度不含形象、气质等歧视性项，口音问题只以中性的"表达清晰度"衡量。</p>
              <p>· 改写示范与参考答案只能基于你真实经历，缺数据的地方留占位符，不会替你编造。</p>
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="py-12 text-center">
        <Link to={primaryTo}>
          <Button size="lg">
            现在开始练习
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Button>
        </Link>
        <p className="mt-3 text-xs text-muted-foreground">
          无需 API Key 也能完整跑通（内置演示面试官）
        </p>
      </section>

      <footer className="border-t border-border py-8 text-center text-xs text-muted-foreground">
        个人练习工具 · AI 评分仅供参考，不代表雇主录用决定
      </footer>
    </div>
  )
}
