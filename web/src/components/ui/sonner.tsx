"use client"

import { useTheme } from "next-themes"
import { Toaster as Sonner, type ToasterProps } from "sonner"
import { Icon } from "@/components/ui/icon";

const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme()

  return (
    <Sonner
      theme={(theme === "dark" ? "dark" : "light") as ToasterProps["theme"]}
      className="toaster group"
      icons={{
        success: (
          <Icon name="check_circle" size={16} />
        ),
        info: (
          <Icon name="info" size={16} />
        ),
        warning: (
          <Icon name="warning" size={16} />
        ),
        error: (
          <Icon name="block" size={16} />
        ),
        loading: (
          <Icon name="progress_activity" size={16} className="animate-spin" />
        ),
      }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "cn-toast",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
