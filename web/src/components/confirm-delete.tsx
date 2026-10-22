"use client";

/** Кнопка удаления с единым диалогом подтверждения: DELETE + тост + обновление страницы/редирект. */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { apiDelete } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export function ConfirmDeleteButton({
  endpoint,
  title,
  name,
  description,
  successMessage,
  redirectTo,
  label,
  appearance = "icon",
  className,
  buttonClassName,
}: {
  /** API-путь удаления, например `/sources/${uid}`. */
  endpoint: string;
  /** Заголовок диалога: «Удалить источник?» */
  title: string;
  /** Что удаляем — показывается в диалоге отдельной строкой. */
  name?: string;
  /** Предупреждение о последствиях (и о зависимостях, если сервер их запретит). */
  description?: string;
  /** Тост при успехе. */
  successMessage: string;
  /** Куда уйти после удаления (без него — router.refresh()). */
  redirectTo?: string;
  /** Текст кнопки для appearance="button". */
  label?: string;
  /** icon — только иконка-«мусорка»; button — outline-кнопка с текстом. */
  appearance?: "icon" | "button";
  /** Класс на обёртку триггера (позиционирование на карточке). */
  className?: string;
  /** Дополнительный класс на сам триггер. */
  buttonClassName?: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const confirm = async () => {
    setDeleting(true);
    try {
      await apiDelete(endpoint);
      toast.success(successMessage);
      setOpen(false);
      if (redirectTo) router.push(redirectTo);
      else router.refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "не удалось удалить");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className={className}>
      {appearance === "icon" ? (
        <button
          onClick={() => setOpen(true)}
          aria-label={title}
          title="удалить"
          className={
            buttonClassName ??
            "rounded-lg bg-background/60 p-1.5 text-muted-foreground backdrop-blur transition hover:text-rose-500"
          }
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      ) : (
        <Button variant="outline" size="sm" className={buttonClassName} onClick={() => setOpen(true)}>
          <Trash2 className="h-3.5 w-3.5" />
          {label ?? "Удалить"}
        </Button>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          {name && <p className="text-sm font-medium">{name}</p>}
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
          <DialogFooter>
            <Button variant="outline" disabled={deleting} onClick={() => setOpen(false)}>
              Отмена
            </Button>
            <Button variant="destructive" disabled={deleting} onClick={() => void confirm()}>
              {deleting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Trash2 className="mr-1 h-4 w-4" />}
              Удалить
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
