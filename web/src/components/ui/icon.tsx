import { cn } from "@/lib/utils";

type IconProps = {
  /** Имя глифа Material Symbols Rounded в snake_case, например "check". */
  name: string;
  /** Размер в пикселях (высота и ширина квадрата под глиф). */
  size?: number;
  className?: string;
  /** Заливка (Pixel-стиль для активных состояний). */
  filled?: boolean;
};

/** Иконка Material Symbols Rounded — единый набор в стилистике Pixel/Android. */
export function Icon({ name, size = 20, className, filled }: IconProps) {
  return (
    <span
      aria-hidden="true"
      translate="no"
      className={cn("ms", filled && "ms-filled", className)}
      style={{ fontSize: `${size}px`, width: `${size}px`, height: `${size}px`, lineHeight: 1 }}
    >
      {name}
    </span>
  );
}
