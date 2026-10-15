/**
 * 本地录像存储（IndexedDB）。
 *
 * ## 为什么视频不上传服务器
 *
 * 视频面试录像是最敏感的个人数据。上传意味着：服务器要存、要备份、要能删干净、
 * 要防越权下载、要考虑合规。而对这个产品来说，录像的唯一用途是**让本人回看自己的表现**。
 *
 * 所以：**录像只存在浏览器 IndexedDB 里，key 记在服务端**。
 * 换设备看不到录像，但简历和评分报告是全量同步的 —— 这是刻意的取舍：
 * 用"换设备看不到录像"换"录像永远不会泄露"。
 *
 * 同时提供 `clearSession` / `clearAll`，让用户能真正把数据删掉。
 */

const DB_NAME = 'aicoach-recordings'
const DB_VERSION = 1
const STORE = 'recordings'

export interface Recording {
  key: string
  sessionId: string
  turnIndex: number
  blob: Blob
  mimeType: string
  durationMs: number
  createdAt: number
  /** 便于在 UI 上显示体积，不重复算 blob.size */
  size: number
}

function hasIndexedDB(): boolean {
  return typeof indexedDB !== 'undefined'
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (!hasIndexedDB()) {
      reject(new Error('当前浏览器不支持 IndexedDB，无法在本机保存录像'))
      return
    }
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: 'key' })
        // 按会话检索 + 按会话批量删除，都需要这个索引
        store.createIndex('sessionId', 'sessionId', { unique: false })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error ?? new Error('打开本地录像库失败'))
  })
}

function tx<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return openDb().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const transaction = db.transaction(STORE, mode)
        const req = run(transaction.objectStore(STORE))
        req.onsuccess = () => resolve(req.result)
        req.onerror = () => reject(req.error ?? new Error('本地录像操作失败'))
        transaction.oncomplete = () => db.close()
      }),
  )
}

export async function putRecording(rec: Omit<Recording, 'size'>): Promise<Recording> {
  const full: Recording = { ...rec, size: rec.blob.size }
  await tx('readwrite', (store) => store.put(full) as IDBRequest<IDBValidKey>)
  return full
}

export async function getRecording(key: string): Promise<Recording | undefined> {
  if (!hasIndexedDB()) return undefined
  try {
    return (await tx<Recording | undefined>('readonly', (store) => store.get(key))) ?? undefined
  } catch {
    return undefined
  }
}

export async function listRecordings(sessionId: string): Promise<Recording[]> {
  if (!hasIndexedDB()) return []
  try {
    const db = await openDb()
    return await new Promise<Recording[]>((resolve, reject) => {
      const transaction = db.transaction(STORE, 'readonly')
      const idx = transaction.objectStore(STORE).index('sessionId')
      const req = idx.getAll(sessionId)
      req.onsuccess = () => {
        const rows = (req.result as Recording[]).sort((a, b) => a.turnIndex - b.turnIndex)
        resolve(rows)
      }
      req.onerror = () => reject(req.error)
      transaction.oncomplete = () => db.close()
    })
  } catch {
    return []
  }
}

export async function deleteRecording(key: string): Promise<void> {
  await tx('readwrite', (store) => store.delete(key) as IDBRequest<undefined>)
}

/** 删除某场面试的全部录像。 */
export async function clearSession(sessionId: string): Promise<number> {
  const rows = await listRecordings(sessionId)
  await Promise.all(rows.map((r) => deleteRecording(r.key)))
  return rows.length
}

/** 清空所有本地录像（「删除我的数据」按钮用）。 */
export async function clearAll(): Promise<number> {
  if (!hasIndexedDB()) return 0
  const db = await openDb()
  const count = await new Promise<number>((resolve) => {
    const transaction = db.transaction(STORE, 'readonly')
    const req = transaction.objectStore(STORE).count()
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => resolve(0)
    transaction.oncomplete = () => db.close()
  })
  await tx('readwrite', (store) => store.clear() as IDBRequest<undefined>)
  return count
}

export interface StorageEstimate {
  usageBytes: number
  quotaBytes: number
  recordingCount: number
  recordingBytes: number
}

/** 本地存储占用情况，用于提醒用户清理。 */
export async function storageEstimate(): Promise<StorageEstimate | null> {
  if (!hasIndexedDB()) return null
  let usageBytes = 0
  let quotaBytes = 0
  if (navigator.storage?.estimate) {
    try {
      const est = await navigator.storage.estimate()
      usageBytes = est.usage ?? 0
      quotaBytes = est.quota ?? 0
    } catch {
      /* 部分浏览器不支持，忽略 */
    }
  }
  const rows = await (async () => {
    try {
      const db = await openDb()
      return await new Promise<Recording[]>((resolve) => {
        const transaction = db.transaction(STORE, 'readonly')
        const req = transaction.objectStore(STORE).getAll()
        req.onsuccess = () => resolve(req.result as Recording[])
        req.onerror = () => resolve([])
        transaction.oncomplete = () => db.close()
      })
    } catch {
      return []
    }
  })()

  return {
    usageBytes,
    quotaBytes,
    recordingCount: rows.length,
    recordingBytes: rows.reduce((sum, r) => sum + (r.size || 0), 0),
  }
}

export function formatBytes(bytes: number): string {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

export function newRecordingKey(sessionId: string, turnIndex: number): string {
  return `${sessionId}:${turnIndex}:${Date.now()}`
}
