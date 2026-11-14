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
  status: string
  caption: string
  linked_block_id: string | null
  link_manual: boolean
  chunk_count: number
}

export type AssetList = {
  items: Asset[]
  limits: Record<string, number>
  recording_enabled: boolean
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
