import { AlertTriangle, RotateCcw } from 'lucide-react'
import { Component, type ErrorInfo, type ReactNode } from 'react'

import { Button } from './ui/button'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/**
 * 全局错误边界。
 * 单个页面渲染崩溃不应该让整个应用白屏 —— 尤其是面试进行中。
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 生产环境应上报到监控；这里先落到控制台便于排查
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div className="flex min-h-[60vh] items-center justify-center p-6">
        <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 text-center">
          <AlertTriangle className="mx-auto h-8 w-8 text-destructive" aria-hidden />
          <h2 className="mt-3 text-lg font-semibold">页面出了点问题</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            你的面试数据已经保存在服务器上，不会丢失。刷新页面即可继续。
          </p>
          <p className="mt-3 break-all rounded bg-secondary/60 p-2 text-left text-xs text-muted-foreground">
            {error.message}
          </p>
          <div className="mt-4 flex justify-center gap-2">
            <Button onClick={() => window.location.reload()}>
              <RotateCcw className="h-4 w-4" aria-hidden />
              刷新页面
            </Button>
            <Button variant="outline" onClick={() => this.setState({ error: null })}>
              返回上一状态
            </Button>
          </div>
        </div>
      </div>
    )
  }
}
