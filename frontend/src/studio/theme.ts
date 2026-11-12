import { studioTheme } from 'ag-studio'

// Each param reads a --pg-* CSS token and falls back to that token's hex.
const v = (name: string, fallback: string) => `var(--pg-${name}, ${fallback})`
const font = 'Inter, ui-sans-serif, system-ui, sans-serif'

// Series palette shared with Mission Control, set for fills and strokes alike: left unset, outlines take Studio's own palette.
const SERIES = ['#2563eb', '#0d9488', '#f59e0b', '#e11d48', '#7c3aed', '#0ea5e9', '#64748b']
const palette = Object.fromEntries(
  SERIES.flatMap((c, i) => [
    [`chartPaletteFills${i + 1}Color`, c],
    [`chartPaletteStrokes${i + 1}Color`, c],
  ]),
)

// Compact, flat and consistent with the host chrome, after the AG Studio Report Builder and Widget Library demos.
const shape = {
  fontSize: 13,
  studioWidgetTitleFontFamily: font,
  studioWidgetTitleFontSize: 15,
  studioWidgetTitleFontWeight: 600,
  studioWidgetSubtitleFontSize: 12,
  gridFontFamily: font,
  gridHeaderFontWeight: 600,
  chartFontFamily: font,
  studioWidgetBorderRadius: 8,
  gridRowBorder: false,
  chartTooltipBorder: false,
}

export const pactguardTheme = studioTheme
  .withParams({ ...palette, ...shape })
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
