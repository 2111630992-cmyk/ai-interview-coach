<#
.SYNOPSIS
  一键启动 / 停止 / 查看 秋招 AI 面试陪练平台的前后端。

.DESCRIPTION
  为什么需要这个脚本：
  1. 前后端是两条命令、两个工作目录，手动开两个终端容易忘；
  2. 服务是后台进程，停的时候需要能准确找到 PID（否则只能靠任务管理器猜）；
  3. 启动后要等依赖装好、端口真正 listen 才算真的可用，"敲完命令就以为好了"是常见坑。

.EXAMPLE
  .\dev.ps1 start      # 启动前后端并等到健康检查通过
  .\dev.ps1 status     # 看端口、健康检查、日志尾部
  .\dev.ps1 stop       # 停掉前后端
  .\dev.ps1 restart    # 重启

.NOTES
  如果启动时报 "SetNamedSecurityInfoW failed (Win32 5)"，
  说明 DSH 会话的沙箱在给工作区加写权限时被 Windows 文件权限挡住了。
  把本会话切到「完全权限」，或在弹出的授权提示里放行这一次即可。
#>
param(
  [ValidateSet('start', 'stop', 'restart', 'status')]
  [string]$Action = 'start'
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.Encoding]::UTF8
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$Root = $PSScriptRoot
$LogDir = Join-Path $Root 'logs'
$BackendDir = Join-Path $Root 'backend'
$FrontendDir = Join-Path $Root 'frontend'

$BackendPort = 8000
$FrontendPort = 5173

$Py = Join-Path $BackendDir '.venv\Scripts\python.exe'
$BackendPidFile = Join-Path $LogDir 'backend.pid'
$FrontendPidFile = Join-Path $LogDir 'frontend.pid'

function Write-Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }
function Write-Ok($text) { Write-Host "    $text" -ForegroundColor Green }
function Write-Warn2($text) { Write-Host "    $text" -ForegroundColor Yellow }
function Write-Err2($text) { Write-Host "    $text" -ForegroundColor Red }

function Get-PortOwner([int]$Port) {
  $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  if ($conn) { return @($conn.OwningProcess)[0] }
  return $null
}

function Get-HealthBackend {
  try { return Invoke-RestMethod "http://127.0.0.1:$BackendPort/api/v1/health" -TimeoutSec 3 } catch { return $null }
}

function Test-Frontend {
  try {
    $r = Invoke-WebRequest "http://localhost:$FrontendPort/" -TimeoutSec 3 -UseBasicParsing
    return $r.StatusCode -eq 200
  } catch { return $false }
}

function Stop-One([int]$Port, [string]$PidFile, [string]$Name) {
  $stopped = $false
  if (Test-Path $PidFile) {
    $pidValue = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($pidValue) {
      $p = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
      if ($p) { Stop-Process -Id $p.Id -Force; Write-Ok "$Name 已停止 (pid $($p.Id))"; $stopped = $true }
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
  }
  # 兜底：pid 文件丢了就按端口占用者杀
  $owner = Get-PortOwner $Port
  if ($owner) {
    Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
    Write-Ok "$Name 已停止 (pid $owner，按端口回收)"
    $stopped = $true
  }
  if (-not $stopped) { Write-Warn2 "$Name 本来就没在运行" }
}

function Start-All {
  New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

  if (-not (Test-Path $Py)) {
    Write-Err2 "找不到虚拟环境：$Py"
    Write-Err2 "先跑：cd backend; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
    exit 1
  }
  $vite = Join-Path $FrontendDir 'node_modules\vite\bin\vite.js'
  if (-not (Test-Path $vite)) {
    Write-Err2 "找不到 vite：$vite"
    Write-Err2 "先跑：cd frontend; npm install"
    exit 1
  }

  # ---------- 后端 ----------
  Write-Step "启动后端 (端口 $BackendPort)"
  if (Get-PortOwner $BackendPort) {
    Write-Warn2 "端口已被占用，跳过启动（先 .\dev.ps1 stop 再启动）"
  } else {
    $proc = Start-Process -FilePath $Py `
      -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$BackendPort") `
      -WorkingDirectory $BackendDir `
      -RedirectStandardOutput (Join-Path $LogDir 'backend.out.log') `
      -RedirectStandardError  (Join-Path $LogDir 'backend.err.log') `
      -PassThru
    $proc.Id | Set-Content $BackendPidFile
    Write-Ok "已拉起 (pid $($proc.Id))，日志 logs\backend.out.log"
  }

  # ---------- 前端 ----------
  Write-Step "启动前端 (端口 $FrontendPort)"
  if (Get-PortOwner $FrontendPort) {
    Write-Warn2 "端口已被占用，跳过启动（先 .\dev.ps1 stop 再启动）"
  } else {
    $node = (Get-Command node -ErrorAction SilentlyContinue).Source
    if (-not $node) { Write-Err2 '找不到 node，请确认 Node.js 已安装并在 PATH 中'; exit 1 }
    # 用 --host localhost 而不是 0.0.0.0：浏览器只在 localhost / https 下允许访问摄像头
    $proc2 = Start-Process -FilePath $node `
      -ArgumentList @($vite, '--port', "$FrontendPort", '--host', 'localhost') `
      -WorkingDirectory $FrontendDir `
      -RedirectStandardOutput (Join-Path $LogDir 'frontend.out.log') `
      -RedirectStandardError  (Join-Path $LogDir 'frontend.err.log') `
      -PassThru
    $proc2.Id | Set-Content $FrontendPidFile
    Write-Ok "已拉起 (pid $($proc2.Id))，日志 logs\frontend.out.log"
  }

  # ---------- 等待就绪 ----------
  Write-Step '等待服务就绪'
  $health = $null
  $backendOk = $false
  $frontendOk = $false
  for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 600
    if (-not $backendOk) { $health = Get-HealthBackend; if ($health) { $backendOk = $true } }
    if (-not $frontendOk) { $frontendOk = Test-Frontend }
    if ($backendOk -and $frontendOk) { break }
  }

  Write-Host ''
  if ($backendOk) {
    Write-Ok "后端就绪  http://127.0.0.1:$BackendPort"
    Write-Host "        API 文档 http://127.0.0.1:$BackendPort/docs" -ForegroundColor DarkGray
    Write-Host "        LLM 模式 $($health.llm_mode)（mock = 未配置 LLM_API_KEY，用内置规则引擎）" -ForegroundColor DarkGray
  } else {
    Write-Err2 "后端未就绪，看 logs\backend.err.log"
  }
  if ($frontendOk) {
    Write-Ok "前端就绪  http://localhost:$FrontendPort"
  } else {
    Write-Err2 "前端未就绪，看 logs\frontend.err.log"
  }

  if ($backendOk -and $frontendOk) {
    Write-Host ''
    Write-Host '  打开 http://localhost:5173 即可开始。' -ForegroundColor White
    Write-Host '  注意：必须用 localhost，不要用局域网 IP —— 浏览器只在安全上下文里允许访问摄像头。' -ForegroundColor DarkGray
  }

  # 把 pid 文件改写成**实际监听端口**的进程。
  # 原因：venv 的 python.exe / node 可能先起一个启动器再拉起真正干活的子进程，
  # 只记 Start-Process 返回的 pid 会指向那个已经退出的启动器。
  foreach ($item in @(
      @{ p = $BackendPort; f = $BackendPidFile },
      @{ p = $FrontendPort; f = $FrontendPidFile }
    )) {
    $owner = Get-PortOwner $item.p
    if ($owner) { $owner | Set-Content $item.f }
  }
}

function Show-Status {
  Write-Step '端口'
  foreach ($item in @(@{p = $BackendPort; n = '后端' }, @{p = $FrontendPort; n = '前端' })) {
    $owner = Get-PortOwner $item.p
    if ($owner) { Write-Ok "$($item.n) $($item.p) LISTENING (pid $owner)" }
    else { Write-Warn2 "$($item.n) $($item.p) 未监听" }
  }

  Write-Step '健康检查'
  $h = Get-HealthBackend
  if ($h) {
    Write-Ok "后端 OK  llm_mode=$($h.llm_mode)  env=$($h.env)  version=$($h.version)"
  } else { Write-Err2 '后端无响应' }
  if (Test-Frontend) { Write-Ok "前端 OK  http://localhost:$FrontendPort" } else { Write-Err2 '前端无响应' }

  Write-Step '日志尾部'
  foreach ($f in @('backend.err.log', 'frontend.out.log')) {
    $path = Join-Path $LogDir $f
    if (Test-Path $path) {
      Write-Host "--- $f ---" -ForegroundColor DarkGray
      Get-Content $path -Tail 6 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "    $_" }
    }
  }
}

switch ($Action) {
  'start' { Start-All }
  'stop' {
    Write-Step '停止服务'
    Stop-One $FrontendPort $FrontendPidFile '前端'
    Stop-One $BackendPort $BackendPidFile '后端'
  }
  'restart' {
    Write-Step '停止服务'
    Stop-One $FrontendPort $FrontendPidFile '前端'
    Stop-One $BackendPort $BackendPidFile '后端'
    Start-Sleep -Seconds 1
    Start-All
  }
  'status' { Show-Status }
}
