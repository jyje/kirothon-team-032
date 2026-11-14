import { defineConfig } from '@slidev/cli'

export default defineConfig({
  title: 'Open Attendee',
  // shortcut: fonts are not fetched from Google at build time (offline-safe), upgrade to a web font when the deck goes public
  fonts: { provider: 'none' },
})
