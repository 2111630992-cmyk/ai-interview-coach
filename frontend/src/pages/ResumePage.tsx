import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Pencil, Trash2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'

import { ApiError } from '../api/client'
import { deleteResume, listResumes, updateResume, uploadResume } from '../api/endpoints'
import type { ResumeParsed, ResumePublic } from '../api/types'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Alert, Badge, EmptyState, Skeleton } from '../components/ui/feedback'
import { Field, Input, Label, Textarea } from '../components/ui/form'
import { Modal } from '../components/ui/modal'
import { useToast } from '../components/ui/toast'

const MAX_MB = 5

function toLines(list: string[] | undefined): string {
  return (list ?? []).join('\n')
}

export function ResumePage() {
  const qc = useQueryClient()
  const toast = useToast()
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [editing, setEditing] = useState<ResumePublic | null>(null)

  const resumes = useQuery({ queryKey: ['resumes'], queryFn: listResumes })

  const upload = useMutation({
    mutationFn: (file: File) => uploadResume(file),
    onSuccess: (data) => {
      toast.success(`已解析「${data.filename}」，识别到 ${data.parsed.skills?.length ?? 0} 项技能`)
      if (data.parse_warning) toast.info(data.parse_warning)
      void qc.invalidateQueries({ queryKey: ['resumes'] })
      void qc.invalidateQueries({ queryKey: ['overview'] })
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : '上传失败，请检查网络后重试')
    },
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteResume(id),
    onSuccess: () => {
      toast.success('已删除')
      void qc.invalidateQueries({ queryKey: ['resumes'] })
      void qc.invalidateQueries({ queryKey: ['overview'] })
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : '删除失败'),
  })

  const handleFiles = (files: FileList | null) => {
    const file = files?.[0]
    if (!file) return
    if (file.size > MAX_MB * 1024 * 1024) {
      toast.error(`文件超过 ${MAX_MB}MB 限制`)
      return
    }
    upload.mutate(file)
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">简历</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          支持 PDF / Word / 纯文本。解析结果可以手动修正 —— 模型认错内容不该影响你的面试练习。
        </p>
      </div>

      {/* 上传区 */}
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          handleFiles(e.dataTransfer.files)
        }}
        className={`flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
          dragging ? 'border-primary bg-primary/5' : 'border-border'
        }`}
      >
        <Upload className="h-6 w-6 text-muted-foreground" aria-hidden />
        <div>
          <p className="font-medium">把简历拖进来，或点击选择文件</p>
          <p className="mt-1 text-xs text-muted-foreground">
            支持 .pdf / .docx / .txt / .md，最大 {MAX_MB}MB
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,.txt,.md"
          className="hidden"
          onChange={(e) => {
            handleFiles(e.target.files)
            e.target.value = ''
          }}
        />
        <Button onClick={() => inputRef.current?.click()} loading={upload.isPending}>
          <Upload className="h-4 w-4" aria-hidden />
          {upload.isPending ? '正在解析…' : '选择文件'}
        </Button>
      </div>

      {upload.isPending && (
        <Alert tone="info" title="正在解析简历">
          抽取教育背景、技能、项目与实习经历，大约需要几秒钟。
        </Alert>
      )}

      {/* 列表 */}
      {resumes.isLoading ? (
        <Skeleton className="h-40" />
      ) : (resumes.data ?? []).length === 0 ? (
        <EmptyState
          icon={<FileText className="h-6 w-6" aria-hidden />}
          title="还没有简历"
          description="上传一份简历后，就可以做匹配分析和模拟面试了。"
        />
      ) : (
        <div className="flex flex-col gap-3">
          {(resumes.data ?? []).map((resume) => (
            <Card key={resume.id}>
              <CardHeader>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <CardTitle className="truncate">{resume.filename}</CardTitle>
                    <CardDescription>
                      {resume.created_at
                        ? new Date(resume.created_at).toLocaleString('zh-CN')
                        : '—'}{' '}
                      · 原文 {resume.text_length} 字
                    </CardDescription>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={() => setEditing(resume)}>
                      <Pencil className="h-3.5 w-3.5" aria-hidden />
                      修正
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        if (window.confirm('确定删除这份简历？')) remove.mutate(resume.id)
                      }}
                      aria-label="删除简历"
                    >
                      <Trash2 className="h-3.5 w-3.5 text-destructive" aria-hidden />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                {resume.parse_warning && <Alert tone="warning">{resume.parse_warning}</Alert>}

                <ParsedSummary parsed={resume.parsed} />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {editing && (
        <EditResumeModal
          resume={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            toast.success('已保存修正')
            void qc.invalidateQueries({ queryKey: ['resumes'] })
          }}
        />
      )}
    </div>
  )
}

function ParsedSummary({ parsed }: { parsed: ResumeParsed }) {
  const skills = parsed.skills ?? []
  const highlights = parsed.highlights ?? []
  const projects = parsed.projects ?? []
  const internships = parsed.internships ?? []

  return (
    <div className="flex flex-col gap-3 text-sm">
      <div>
        <p className="mb-1.5 text-xs font-medium text-muted-foreground">技能（{skills.length}）</p>
        {skills.length ? (
          <div className="flex flex-wrap gap-1.5">
            {skills.map((s) => (
              <Badge key={s} tone="primary">
                {s}
              </Badge>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">未识别到技能，建议手动补充</p>
        )}
      </div>

      <div>
        <p className="mb-1.5 text-xs font-medium text-muted-foreground">
          面试官最可能追问的要点（{highlights.length}）
        </p>
        {highlights.length ? (
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {highlights.map((h, i) => (
              <li key={i}>{h}</li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">
            没有识别到带数字的成果 —— 面试官会因此怀疑真实性，建议手动补充量化结果。
          </p>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <p className="mb-1.5 text-xs font-medium text-muted-foreground">
            项目经历（{projects.length}）
          </p>
          {projects.length ? (
            <ul className="space-y-1 text-xs text-muted-foreground">
              {projects.slice(0, 4).map((p, i) => (
                <li key={i} className="truncate">
                  · {p.name || '未命名项目'}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted-foreground">未识别到</p>
          )}
        </div>
        <div>
          <p className="mb-1.5 text-xs font-medium text-muted-foreground">
            实习经历（{internships.length}）
          </p>
          {internships.length ? (
            <ul className="space-y-1 text-xs text-muted-foreground">
              {internships.slice(0, 4).map((it, i) => (
                <li key={i} className="truncate">
                  · {it.company || '未命名'}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted-foreground">未识别到</p>
          )}
        </div>
      </div>
    </div>
  )
}

function EditResumeModal({
  resume,
  onClose,
  onSaved,
}: {
  resume: ResumePublic
  onClose: () => void
  onSaved: () => void
}) {
  const [skills, setSkills] = useState(toLines(resume.parsed.skills).replace(/\n/g, '、'))
  const [highlights, setHighlights] = useState(toLines(resume.parsed.highlights))
  const [rawOpen, setRawOpen] = useState(false)
  const [raw, setRaw] = useState(() => JSON.stringify(resume.parsed, null, 2))
  const [rawError, setRawError] = useState<string | null>(null)
  const toast = useToast()

  const save = useMutation({
    mutationFn: async () => {
      let parsed: ResumeParsed = { ...resume.parsed }

      if (rawOpen) {
        try {
          parsed = JSON.parse(raw) as ResumeParsed
        } catch {
          throw new Error('JSON 格式不正确，请检查括号与引号')
        }
      }

      parsed.skills = skills
        .split(/[、,，\n]/)
        .map((s) => s.trim())
        .filter(Boolean)
      parsed.highlights = highlights
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean)

      return updateResume(resume.id, parsed as unknown as Record<string, unknown>)
    },
    onSuccess: onSaved,
    onError: (err) => {
      const msg = err instanceof Error ? err.message : '保存失败'
      if (rawOpen) setRawError(msg)
      else toast.error(msg)
    },
  })

  return (
    <Modal
      open
      onClose={onClose}
      title="修正解析结果"
      description="模型抽取难免出错，你可以直接改。技能用顿号或逗号分隔，要点一行一条。"
      className="max-w-2xl"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={() => save.mutate()} loading={save.isPending}>
            保存
          </Button>
        </>
      }
    >
      <div className="flex max-h-[60vh] flex-col gap-4 overflow-y-auto pr-1">
        <Field label="技能" hint="例如：Java、MySQL、Redis、Docker">
          {(id) => <Input id={id} value={skills} onChange={(e) => setSkills(e.target.value)} />}
        </Field>

        <Field
          label="面试官最可能追问的要点"
          hint="一行一条，尽量带数字（如：把下单接口 P99 从 800ms 降到 120ms）"
        >
          {(id) => (
            <Textarea
              id={id}
              rows={6}
              value={highlights}
              onChange={(e) => setHighlights(e.target.value)}
            />
          )}
        </Field>

        <div className="flex flex-col gap-2">
          <button
            type="button"
            className="flex items-center gap-2 self-start text-xs text-muted-foreground underline-offset-4 hover:underline"
            onClick={() => setRawOpen((v) => !v)}
            aria-expanded={rawOpen}
          >
            {rawOpen ? '收起' : '展开'}高级编辑（完整 JSON）
          </button>
          {rawOpen && (
            <>
              <Label htmlFor="raw-json" className="sr-only">
                解析结果 JSON
              </Label>
              <Textarea
                id="raw-json"
                rows={10}
                className="font-mono text-xs"
                value={raw}
                onChange={(e) => {
                  setRaw(e.target.value)
                  setRawError(null)
                }}
              />
              {rawError && (
                <p className="text-xs text-destructive" role="alert">
                  {rawError}
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </Modal>
  )
}
