import { useEffect, useRef, useState, type ElementType, type ReactNode } from "react"

export function Reveal({
  as: Tag = "div",
  className = "",
  id,
  children,
}: {
  as?: ElementType
  className?: string
  id?: string
  children: ReactNode
}) {
  const ref = useRef<HTMLElement | null>(null)
  const [inView, setInView] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setInView(true)
            observer.unobserve(entry.target)
          }
        }
      },
      { threshold: 0.12 },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <Tag
      ref={ref}
      id={id}
      className={`reveal${inView ? " in" : ""}${className ? ` ${className}` : ""}`}
    >
      {children}
    </Tag>
  )
}
