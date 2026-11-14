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
