import { cn } from '../../lib/utils'

export interface OptionItem<T> {
  value: T
  label: string
  desc?: string
}

interface OptionGroupProps<T extends string | number> {
  label: string
  items: readonly OptionItem<T>[]
  value: T
  onChange: (value: T) => void
  columns?: 2 | 3
}

/** 面试配置用的单选卡片组。语义上是 radiogroup，键盘可用。 */
export function OptionGroup<T extends string | number>({
  label,
  items,
  value,
  onChange,
  columns = 3,
}: OptionGroupProps<T>) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-sm font-medium">{label}</legend>
      <div
        role="radiogroup"
        aria-label={label}
        className={cn('grid gap-2', columns === 3 ? 'sm:grid-cols-3' : 'sm:grid-cols-2')}
      >
        {items.map((item) => {
          const active = item.value === value
          return (
            <button
              key={String(item.value)}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(item.value)}
              className={cn(
                'flex flex-col gap-0.5 rounded-md border p-3 text-left transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                active
                  ? 'border-primary bg-primary/5 ring-1 ring-primary/30'
                  : 'border-border hover:border-primary/40',
              )}
            >
              <span className="text-sm font-medium">{item.label}</span>
              {item.desc && <span className="text-xs text-muted-foreground">{item.desc}</span>}
            </button>
          )
        })}
      </div>
    </fieldset>
  )
}
