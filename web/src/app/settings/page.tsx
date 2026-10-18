/** Настройки: профиль, модели, MCP, обслуживание. */

import { api } from "@/lib/api";
import type { Health, Profile } from "@/lib/types";
import { ProfileForm } from "@/components/settings/profile-form";
import { AgentsSettings } from "@/components/settings/agents-settings";
import { McpConnections } from "@/components/settings/mcp-connections";
import { MaintenanceActions } from "@/components/settings/maintenance";
import { TelegramTestButton } from "@/components/settings/integrations";
import { ConnectivitySettings } from "@/components/settings/connectivity";
import { Badge } from "@/components/ui/badge";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const [profile, health] = await Promise.all([
    api<Profile>("/settings/profile").catch(() => null),
    api<Health>("/health").catch(() => null),
  ]);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-3xl flex-col gap-10 px-6 py-10 sm:px-8">
        <div>
          <h1 className="text-xl font-semibold">Настройки</h1>
          <p className="mt-1 text-sm text-muted-foreground">Профиль, модели, интеграции и обслуживание</p>
        </div>

        <section className="rounded-2xl border bg-card p-6">
          <h2 className="font-medium">Профиль</h2>
          <p className="mb-5 mt-1 text-sm text-muted-foreground">
            Машины — для практики в сессиях; предпочтения — параметры уроков по умолчанию
          </p>
          {profile ? (
            <ProfileForm initial={profile} />
          ) : (
            <p className="text-sm text-muted-foreground">Профиль недоступен (ядро не отвечает)</p>
          )}
        </section>

        <section className="rounded-2xl border bg-card p-6">
          <h2 className="font-medium">Модели</h2>
          <p className="mb-4 mt-1 text-sm text-muted-foreground">Единый LLM-слой; роли читаются из llm.yaml</p>
          {health && (
            <div className="flex flex-wrap items-center gap-3 rounded-xl border bg-background/50 p-4 text-sm">
              <Badge variant={health.llm_configured ? "secondary" : "destructive"}>
                {health.llm_configured ? "LLM подключён" : "LLM не настроен"}
              </Badge>
              <span className="text-muted-foreground">
                {health.provider} · {health.model}
                {health.llm_reason ? ` · ${health.llm_reason}` : ""}
              </span>
            </div>
          )}
          <p className="mt-4 text-xs text-muted-foreground">
            Ключ — через <code>sec exec ZAI_API_KEY</code>; смена ролей/моделей — правка <code>server/config/llm.yaml</code>.
          </p>
        </section>

        <section className="rounded-2xl border bg-card p-6">
          <h2 className="font-medium">Поведение агентов</h2>
          <p className="mb-4 mt-1 text-sm text-muted-foreground">
            Раскрой агента — увидишь его промпт и инструменты. Правки — словами через настройщик, новых помощников — конструктором
          </p>
          <AgentsSettings />
        </section>

        <section className="rounded-2xl border bg-card p-6">
          <h2 className="font-medium">Сторонние MCP</h2>
          <p className="mb-4 mt-1 text-sm text-muted-foreground">
            Подключай внешние MCP-серверы — их инструменты сразу доступны агентам
          </p>
          <McpConnections />
        </section>

        <section className="rounded-2xl border bg-card p-6">
          <h2 className="font-medium">Прокси и поиск</h2>
          <p className="mb-5 mt-1 text-sm text-muted-foreground">
            Ключ поиска (Tavily/Serper), socks5-прокси или vless-ключ — YouTube, веб-серчинг и Telegram работают через них без рестартов
          </p>
          <ConnectivitySettings />
        </section>

        <section className="rounded-2xl border bg-card p-6">
          <h2 className="font-medium">Telegram</h2>
          <p className="mb-4 mt-1 text-sm text-muted-foreground">Мост для отправки блоков и глав книги; токен — LEARNOS_TELEGRAM_TOKEN</p>
          <TelegramTestButton />
        </section>

        <section className="rounded-2xl border bg-card p-6">
          <h2 className="font-medium">MCP</h2>
          <p className="mb-4 mt-1 text-sm text-muted-foreground">Подключение ядра из внешних агентов (opencode и др.)</p>
          <div className="text-sm">
            <p>
              Общий сервер: <code className="rounded bg-muted px-1.5 py-0.5">http://localhost:8765/mcp</code>
            </p>
            <p className="mt-2 text-muted-foreground">
              По модулям: <code>/mcp/knowledge</code>, <code>/mcp/library</code>, <code>/mcp/learning</code>, …
            </p>
            <pre className="mt-3 overflow-x-auto rounded-xl border bg-zinc-950 p-4 text-xs leading-relaxed text-zinc-100">{`{
  "mcp": {
    "learnos": { "type": "remote", "url": "http://localhost:8765/mcp" }
  }
}`}</pre>
          </div>
        </section>

        <section className="rounded-2xl border bg-card p-6">
          <h2 className="font-medium">Обслуживание</h2>
          <p className="mb-4 mt-1 text-sm text-muted-foreground">Переиндексация базы знаний и выгрузки</p>
          <MaintenanceActions />
        </section>
      </div>
    </div>
  );
}
