export type SessionItem = {
  id: string
  title: string
  event_date: string | null
  created_at: string
  updated_at: string
  asset_count: number
  draft_status: string | null
}

export type Block = { id: string; position: number; text: string; revision: number }

export type SessionDetail = {
  id: string
  title: string
  event_date: string | null
  blocks: Block[]
}

export type Asset = {
  id: string
  kind: 'photo' | 'slides' | 'reference' | 'voice_memo' | 'recording'
  display_name: string
  mime: string
  size_bytes: number
  page_count: number | null
  status: string
  caption: string
  linked_block_id: string | null
  link_manual: boolean
  chunk_count: number
}

export type AssetList = {
  items: Asset[]
  limits: Record<string, number>
  transcription_enabled: boolean
  recording_enabled: boolean
  recording_max_bytes: number
}

export type Transcript = {
  completed: boolean
  segments: { start_ms: number; end_ms: number; text: string }[]
}

export type ConsentRecord = {
  id: string
  obtained_on: string
  method: string
  revoked_at: string | null
}

export type SummarySource = { kind: string; locator: string; target_id: string }
export type SummaryBullet = { text: string; sources: SummarySource[] }
export type Summary = { id: string; created_at: string; bullets: SummaryBullet[] }
export type SummaryResponse = {
  summary: Summary | null
  llm_configured: boolean
  dropped_bullets?: number
  truncated?: boolean
}

export type DraftSentence = {
  id: string
  text: string
  origin: 'ai' | 'ai_edited' | 'user_insight'
  verify_status: 'verified' | 'unverified' | 'kept_as_opinion' | 'n/a'
  verify_note: string | null
  sources: { kind: string; locator: string }[]
}
export type DraftSection = {
  id: string
  title: string
  insight_slot: boolean
  sentences: DraftSentence[]
}
export type Draft = {
  id: string
  status: 'generating' | 'in_review' | 'approved' | 'failed'
  approved_at: string | null
  review_seconds: number | null
  unverified_count: number
  template_name: string | null
  sections: DraftSection[]
}
export type DraftResponse = { draft: Draft | null; llm_configured: boolean }

export type TemplateInfo = { id: string; name: string; sections: string[] }
export type TemplateSection = {
  id: string
  title: string
  instruction: string
  max_sentences: number
  insight_slot: boolean
}
export type TemplateDetail = {
  id: string
  name: string
  tone: string
  built_in: boolean
  sections: TemplateSection[]
}
