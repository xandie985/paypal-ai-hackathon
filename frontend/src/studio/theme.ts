import { studioTheme } from 'ag-studio'

// Each param reads a --pg-* token (doc 11 §4.2) and falls back to that token's hex until UI-0.1 defines them.
const v = (name: string, fallback: string) => `var(--pg-${name}, ${fallback})`
const font = 'Inter, ui-sans-serif, system-ui, sans-serif'

export const pactguardTheme = studioTheme
  .withParams(
    {
      backgroundColor: v('surface', '#FFFFFF'),
      foregroundColor: v('ink', '#0B1220'),
      accentColor: v('primary', '#0070E0'),
      borderColor: v('border', '#E1E6EF'),
      studioCanvasBackgroundColor: v('bg', '#F5F7FB'),
      studioWidgetBackgroundColor: v('surface', '#FFFFFF'),
      fontFamily: font,
      browserColorScheme: 'light',
    },
    'light',
  )
  .withParams(
    {
      backgroundColor: v('surface', '#111827'),
      foregroundColor: v('ink', '#E7EBF3'),
      accentColor: v('primary', '#4D9BFF'),
      borderColor: v('border', '#26314B'),
      studioCanvasBackgroundColor: v('bg', '#0A0F1C'),
      studioWidgetBackgroundColor: v('surface', '#111827'),
      fontFamily: font,
      browserColorScheme: 'dark',
    },
    'dark',
  )
