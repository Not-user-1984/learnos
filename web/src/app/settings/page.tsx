/** Настройки: профиль, агенты, MCP, LLM, связь, обслуживание. */

import { api } from "@/lib/api";
import type { Profile } from "@/lib/types";
import { ProfileForm } from "@/components/settings/profile-form";
import { AgentsSettings } from "@/components/settings/agents-settings";
import { McpConnections } from "@/components/settings/mcp-connections";
import { MaintenanceActions } from "@/components/settings/maintenance";
import { TelegramTestButton } from "@/components/settings/integrations";
import { ConnectivitySettings } from "@/components/settings/connectivity";
import { LlmSettings } from "@/components/settings/llm-settings";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const profile = await api<Profile>("/settings/profile").catch(() => null);

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
            Ключ поиска (Tavily/Serper), socks5-прокси или vless-ключ — YouTube, веб-серчинг и
            Telegram работают через них без рестартов. Ниже — какие провайдеры поиска активны
            для агента (веб, научные статьи, видео)
          </p>
          <ConnectivitySettings />
        </section>

        <section className="rounded-2xl border bg-card p-6">
          <h2 className="font-medium">LLM</h2>
          <p className="mb-5 mt-1 text-sm text-muted-foreground">
            Роли и модели из llm.yaml, состояние цепочки ключей (какой рабочий, кто в cooldown)
          </p>
          <LlmSettings />
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
