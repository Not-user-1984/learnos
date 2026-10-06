export interface Course {
  id: number;
  topic: string;
  status: string;
  created_at: string;
}

export interface BlockRow {
  id: number;
  course_id: number;
  session_id: number;
  block_uid: string;
  title: string;
  path: string;
  tags_json: string;
  sources_json: string;
  review_json: string;
  created_at: string;
}

export interface Block {
  id: number;
  course_id: number;
  session_id: number;
  block_uid: string;
  title: string;
  path: string;
  tags: string[];
  sources: string[];
  review: { ease?: number; interval?: number; due?: string | null };
  created_at: string;
  content: string;
}

export function stripFrontmatter(md: string): string {
  if (!md.startsWith("---")) return md;
  const end = md.indexOf("---", 3);
  if (end === -1) return md;
  return md.slice(end + 3).trim();
}

export function parseTags(row: BlockRow): string[] {
  try {
    return JSON.parse(row.tags_json) as string[];
  } catch {
    return [];
  }
}

export function parseSources(row: BlockRow): string[] {
  try {
    return JSON.parse(row.sources_json) as string[];
  } catch {
    return [];
  }
}
