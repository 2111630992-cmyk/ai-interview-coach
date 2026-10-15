import { useEffect } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  BarChart3,
  Briefcase,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Sun,
  Target,
  X,
} from 'lucide-react'
import { useState } from 'react'

import { useAuthStore } from '../../stores/auth'
import { useThemeStore } from '../../stores/theme'
import { cn } from '../../lib/utils'
import { Button } from '../ui/button'

const NAV = [
  { to: '/dashboard', label: '工作台', icon: LayoutDashboard },
  { to: '/resume', label: '简历', icon: FileText },
  { to: '/jd', label: '岗位 JD', icon: Briefcase },
  { to: '/match', label: '匹配分析', icon: Target },
  { to: '/history', label: '历史与趋势', icon: BarChart3 },
]

export function AppShell() {
  const user = useAuthStore((s) => s.user)
  const signOut = useAuthStore((s) => s.signOut)
  const { theme, toggle } = useThemeStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)

  // 路由变化时关闭移动端菜单
  useEffect(() => setMenuOpen(false), [location.pathname])

  const handleSignOut = () => {
    signOut()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex min-h-screen flex-col bg-secondary/25">
      <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center gap-4 px-4">
          <NavLink to="/dashboard" className="flex items-center gap-2 font-semibold">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-xs font-bold text-primary-foreground">
              AI
            </span>
            <span className="hidden sm:inline">秋招面试陪练</span>
          </NavLink>

          <nav className="hidden flex-1 items-center gap-1 md:flex" aria-label="主导航">
            {NAV.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors',
                    isActive
                      ? 'bg-secondary text-foreground'
                      : 'text-muted-foreground hover:bg-secondary/60 hover:text-foreground',
                  )
                }
              >
                <Icon className="h-4 w-4" aria-hidden />
                {label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={toggle}
              aria-label={theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
            >
              {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>

            <span className="hidden max-w-[10rem] truncate text-sm text-muted-foreground sm:inline">
              {user?.nickname ?? '未登录'}
              {user?.is_guest && <span className="ml-1 text-xs">(游客)</span>}
            </span>

            <Button variant="outline" size="sm" onClick={handleSignOut} className="hidden sm:flex">
              <LogOut className="h-4 w-4" aria-hidden />
              退出
            </Button>

            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              aria-label={menuOpen ? '关闭菜单' : '打开菜单'}
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((v) => !v)}
            >
              {menuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </Button>
          </div>
        </div>

        {menuOpen && (
          <nav className="border-t border-border bg-background md:hidden" aria-label="移动端导航">
            <div className="mx-auto flex w-full max-w-6xl flex-col p-2">
              {NAV.map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2 rounded-md px-3 py-2 text-sm',
                      isActive ? 'bg-secondary' : 'text-muted-foreground',
                    )
                  }
                >
                  <Icon className="h-4 w-4" aria-hidden />
                  {label}
                </NavLink>
              ))}
              <button
                type="button"
                onClick={handleSignOut}
                className="flex items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-muted-foreground"
              >
                <LogOut className="h-4 w-4" aria-hidden />
                退出登录
              </button>
            </div>
          </nav>
        )}
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Outlet />
      </main>

      <footer className="border-t border-border py-4 text-center text-xs text-muted-foreground">
        面试练习工具 · AI 评分仅供参考，不代表真实面试结果
      </footer>
    </div>
  )
}
