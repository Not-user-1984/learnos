/** Ручные типы данных API (до gen:api — SSE-события и карточки описываем руками). */

export type BlockCard = {
  block_uid: string;
  kind: "lesson" | "note" | string;
  title: string;
  summary: string | null;
  category_path: string | null;
  category_status: "suggested" | "confirmed" | string;
  tags: string[];
  sources: { source: string; chapter: number | null; title: string }[];
  weak_spots_count: number;
  version: number;
  created_at: string;
  updated_at: string;
};

export type BlockDetail = BlockCard & {
  content: string;
  session_uid?: string | null;
  conversation_uid?: string | null;
  versions_count: number;
  links: string[];
  back_links: string[];
};

export type CategoryNode = {
  path: string;
  title: string;
  color: string | null;
  icon: string | null;
  count: number;
  children: CategoryNode[];
};

export type SourceCard = {
  id: number;
  uid: string;
  kind: string;
  title: string;
  author: string | null;
  url: string | null;
  status: string;
  summary: string | null;
  chapters_count: number;
  meta: Record<string, unknown>;
};

export type ChapterCard = {
  idx: number;
  title: string;
  tokens_est: number | null;
  summary: string | null;
  key_points: string[];
  has_exercises: boolean;
  /** Номер главы из самой книги («Глава 3. …» → 3); null — приложения/без номера. */
  number?: number | null;
  start_page?: number | null;
  end_page?: number | null;
};

/** Оглавление книги для PDF-ридера (из /outline). */
export type BookOutline = {
  source: string;
  total_pages: number;
  pages: Record<string, number>;
  numbers: Record<string, number>;
  sections: Record<string, { title: string; page: number }[]>;
};

export type SourceDetail = SourceCard & { chapters: ChapterCard[] };

export type ActivityCard = {
  id: number;
  uid: string;
  source_id: number;
  source_uid: string;
  title: string;
  status: string;
  cursor_chapter: number;
  total_chapters: number;
  created_at: string;
  updated_at: string;
};

export type ConversationItem = {
  uid: string;
  title: string;
  active_agent?: string | null;
  mode: string;
  /** Человекочитаемый сценарий («Разбор видео», «Сессия · глава 3») от бэкенда. */
  scenario?: string | null;
  updated_at: string;
  messages_count?: number;
};

export type ChatMessage = {
  id: number;
  role: "user" | "assistant" | "tool";
  content: string;
  cards: Card[];
  created_at: string;
};

export type SessionState = {
  session_uid: string;
  state: string;
  status: string;
  allowed_events: string[];
  chapter_idx: number | null;
  config: Record<string, unknown>;
} | null;

/** Прогресс быстрого разбора книги в разговоре (активность разговора, T-046).
 *  Отдельная сущность от сессии-урока: разбор — курсор книги по главам. */
export type ReviewProgress = {
  activity_uid: string;
  source_uid: string;
  title: string;
  kind: string;
  done_chapters: number;
  total_chapters: number;
  current_chapter: number | null;
  current_title: string | null;
  status: string;
};

/** Живой запуск агента из agent_runs (root или субагент). */
export type AgentRunInfo = {
  agent: string;
  steps: number;
  tool_calls: number;
  /** Чем запуск занят прямо сейчас: label последнего инструмента (BUG-003). */
  current?: string | null;
  started_at: string;
};

/** Правда о генерации разговора (T-041): агент работает / генерация прервана. */
export type AgentState = {
  working: boolean;
  runs: AgentRunInfo[];
  interrupted: boolean;
};

export type ConversationDetail = {
  uid: string;
  title: string;
  mode: string;
  active_agent?: string | null;
  scenario?: string | null;
  activity_id: number | null;
  chapter_idx: number | null;
  focus_block_uid: string | null;
  messages: ChatMessage[];
  session: SessionState;
  review_progress?: ReviewProgress | null;
  agent_state?: AgentState | null;
};

export type CourseItem = {
  id: number;
  item_type: string;
  source_id: number | null;
  chapter_idx: number | null;
  block_uid: string | null;
  note: string | null;
  done: boolean;
  title: string;
  hint: string;
};

export type Course = {
  uid: string;
  title: string;
  topic: string;
  description: string | null;
  status: string;
  items_count: number;
  items_done: number;
  items?: CourseItem[];
  next_step?: { item_id: number; item_type: string; title: string; hint: string } | null;
};

export type Profile = {
  name: string;
  about: string;
  machines: { id: string; name: string; kind: string; specs: string; tools: string[]; notes: string }[];
  learning: {
    session_minutes: number;
    theory_concepts: number;
    questions_per_concept: number;
    practice_default: boolean;
    explain_style: string;
  };
};

/** Детальный статус LLM (GET /api/llm/status): роли и цепочки ключей (BB-004). */
export type LlmStatus = {
  configured: boolean;
  provider: string | null;
  model: string | null;
  keys: number;
  reason: string | null;
  roles: Record<
    string,
    {
      provider: string;
      model: string;
      params: Record<string, unknown>;
      keys: number;
      configured: boolean;
      reason?: string;
    }
  >;
  providers: Record<
    string,
    {
      type: string;
      enabled: boolean;
      keyless: boolean;
      keys_total: number;
      reason?: string;
      keychain?: {
        keys_total: number;
        sticky: number | null;
        keys: LlmKeyState[];
      };
    }
  >;
};

export type LlmKeyState = {
  index: number;
  state: "active" | "ready" | "cooldown";
  cooldown_seconds?: number;
};

/** Провайдеры поиска по категориям (GET /api/research/providers): где агент ищет. */
export type SearchProvidersView = {
  web: { mode: string; providers: SearchProviderInfo[] };
  academic: { mode: string; providers: SearchProviderInfo[] };
  video: { mode: string; providers: SearchProviderInfo[] };
};

export type SearchProviderInfo = {
  name: string;
  enabled: boolean;
  note: string;
};

/** Карточки UI из SSE (см. ТЗ 04): один интерфейс с опциональными полями по типу. */
/** Драфт блока для карточки-превью конспекта (preview_note). */
export type NoteDraft = {
  title: string;
  summary?: string;
  kind?: string;
  concepts?: { term: string; definition: string }[];
  theses?: string[];
  my_examples?: string[];
  mermaid?: string | null;
  weak_spots?: string[];
  open_questions?: string[];
  tags?: string[];
  category_suggestion?: string | null;
};

export interface Card {
  type: string;
  // command
  machine?: string;
  machine_name?: string;
  command?: string;
  explanation?: { part: string; text: string }[];
  expected?: string;
  risk?: string;
  step?: number;
  // question / evaluation
  concept?: string;
  question?: string;
  index?: number;
  total?: number;
  verdict?: string;
  comment?: string;
  weak_spot?: string;
  // block_saved / block_updated
  title?: string;
  summary?: string;
  block_uid?: string;
  kind?: string;
  category?: string | null;
  category_suggested?: string | null;
  category_status?: string;
  version?: number;
  from_version?: number;
  to_version?: number;
  reason?: string;
  // prompt_change (kind: prompt | skill)
  status?: string;
  change_id?: number;
  agent?: string;
  file?: string;
  diff?: { op: string; line: string }[];
  // git_change (ветка агента, ступень 2 ревизии T-038)
  branch?: string;
  commit?: string;
  files?: string[];
  diffstat?: string;
  // note_draft (превью конспекта)
  preview_id?: number;
  draft?: NoteDraft;
  // action_offer (предложение действия) / attachment (вложение сообщения)
  description?: string;
  source_uid?: string;
  // quick_replies (кнопки-ответы на вопрос агента, T-045)
  replies?: string[];
  // chapter_review (блочный разбор главы/видео, T-046 Э2)
  media?: "chapter" | "video";
  key_points?: string[];
  concepts?: { term: string; definition: string }[];
  applicable?: string[];
  questions?: string[];
}

/** SSE-события чата. */
export type SseEvent =
  | { event: "user_saved"; data: { message_id: number } }
  | { event: "handoff"; data: { agent: string; reason?: string } }
  | { event: "delta"; data: { text: string } }
  | { event: "tool_start"; data: { call_id: string; name: string; args: Record<string, unknown>; label: string } }
  | { event: "tool_end"; data: { call_id: string; name: string; ok: boolean; summary: string } }
  | { event: "card"; data: { call_id?: string; card: Card } }
  | { event: "session"; data: { session_uid?: string; state: string; allowed_events: string[]; chapter_idx?: number | null; progress: { theory_done: number; questions_done: number } } }
  | { event: "review_progress"; data: ReviewProgress }
  | { event: "title"; data: { title: string } }
  | { event: "done"; data: { message_id: number | null } }
  | { event: "error"; data: { error: string; message: string } };
