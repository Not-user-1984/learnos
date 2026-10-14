import { redirect } from "next/navigation";

/** Корень — редирект в базу знаний. */
export default function Home() {
  redirect("/kb");
}
