import KbPage from "./kb/page";

export const dynamic = "force-dynamic";

/** Корень сразу рендерит базу знаний (серверный редирект ломался во встроенном браузере). */
export default function Home() {
  return <KbPage searchParams={Promise.resolve({})} />;
}
