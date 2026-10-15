import { Suspense, lazy, useEffect } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'

import { setUnauthorizedHandler } from './api/client'
import { AppShell } from './components/layout/AppShell'
import { Spinner } from './components/ui/feedback'
import { LandingPage } from './pages/LandingPage'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { useAuthStore } from './stores/auth'

// 登录后才会用到的页面按需加载：
// 首屏只需要落地页/登录页，没必要把图表库和面试房间一起下载。
const DashboardPage = lazy(() =>
  import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
)
const ResumePage = lazy(() =>
  import('./pages/ResumePage').then((m) => ({ default: m.ResumePage })),
)
const JdPage = lazy(() => import('./pages/JdPage').then((m) => ({ default: m.JdPage })))
const MatchPage = lazy(() =>
  import('./pages/MatchPage').then((m) => ({ default: m.MatchPage })),
)
const InterviewSetupPage = lazy(() =>
  import('./pages/InterviewSetupPage').then((m) => ({ default: m.InterviewSetupPage })),
)
const InterviewRoomPage = lazy(() =>
  import('./pages/InterviewRoomPage').then((m) => ({ default: m.InterviewRoomPage })),
)
const ReportPage = lazy(() =>
  import('./pages/ReportPage').then((m) => ({ default: m.ReportPage })),
)
const HistoryPage = lazy(() =>
  import('./pages/HistoryPage').then((m) => ({ default: m.HistoryPage })),
)

function FullPageLoader() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center gap-3 text-sm text-muted-foreground">
      <Spinner />
      正在加载…
    </div>
  )
}

/** 路由守卫：未登录跳登录页。 */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user)
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  const ready = useAuthStore((s) => s.ready)
  const user = useAuthStore((s) => s.user)
  const bootstrap = useAuthStore((s) => s.bootstrap)
  const navigate = useNavigate()

  useEffect(() => {
    void bootstrap()
  }, [bootstrap])

  // token 失效时统一登出并跳转，避免各页面各写一套
  useEffect(() => {
    setUnauthorizedHandler(() => navigate('/login', { replace: true }))
    return () => setUnauthorizedHandler(null)
  }, [navigate])

  // 首次校验 token 期间不要闪登录页
  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center gap-3 text-sm text-muted-foreground">
        <Spinner />
        正在加载…
      </div>
    )
  }

  return (
    <Suspense fallback={<FullPageLoader />}>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={user ? <Navigate to="/dashboard" replace /> : <LoginPage />} />
        <Route
          path="/register"
          element={user ? <Navigate to="/dashboard" replace /> : <RegisterPage />}
        />

        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/resume" element={<ResumePage />} />
          <Route path="/jd" element={<JdPage />} />
          <Route path="/match" element={<MatchPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/interview/setup" element={<InterviewSetupPage />} />
          <Route path="/interview/:sessionId/report" element={<ReportPage />} />
        </Route>

        {/* 面试进行页刻意放在 AppShell 之外：全屏沉浸，不出现导航栏 */}
        <Route
          path="/interview/:sessionId"
          element={
            <RequireAuth>
              <InterviewRoomPage />
            </RequireAuth>
          }
        />

        <Route path="*" element={<Navigate to={user ? '/dashboard' : '/'} replace />} />
      </Routes>
    </Suspense>
  )
}
