// AG Studio -> Anthropic Messages API adapter (Claude Haiku 5.5 by default).
//
// Same contract as the OpenAI adapter in the AG Studio docs (AgLlmAdapter.executeTurn): it encodes
// Studio's conversation items as Messages API input, streams the reply back as Studio events, and
// resolves `complete` with the consolidated response. It runs in the browser and posts to this app's
// own proxy (backend/app/ai_proxy.py), which holds the key, so nothing secret is sent from here.

import type {
  AgAiConversationItem,
  AgAiEvent,
  AgAiOutputItem,
  AgAiToolSchema,
  AgLlmAdapter,
  AgLlmRequest,
  AgLlmResponse,
  AgLlmResponseHandler,
} from 'ag-studio'

type Json = Record<string, unknown>
type Block = Json & { type: string }
interface Message {
  role: 'user' | 'assistant'
  content: Block[]
}

interface ClaudeAdapterOptions {
  /** Base URL of the proxy; the adapter posts to `${endpoint}/messages`. */
  endpoint?: string
  model?: string
  /** Domain context appended to the instructions Studio sends on every turn. */
  system?: string
}

// Tool use needs no prompt help on Haiku 5.5, but with thinking off the model can narrate a call
// instead of making it; this keeps calls real and keeps internal tags out of the answer.
const TOOL_GUARD =
  'When you use a tool, you may say a brief sentence first. If no tool can express what the user asked for, say so instead of guessing. Do not include internal or system XML tags in your response.'

const isRecord = (v: unknown): v is Json => typeof v === 'object' && v !== null && !Array.isArray(v)
const num = (v: unknown) => (typeof v === 'number' ? v : 0)

// --- Schema -----------------------------------------------------------------------------------
// Studio's Shape library marks "optional" with an `anyOf` branch of `{ not: {} }`, which means
// "undefined". The Messages API has no use for it, so it is dropped (the property just stays optional).

const isUndefinedSentinel = (s: unknown) => isRecord(s) && Object.keys(s).length === 1 && isRecord(s.not) && Object.keys(s.not).length === 0

function cleanSchema(node: unknown): unknown {
  if (Array.isArray(node)) return node.map(cleanSchema)
  if (!isRecord(node)) return node
  const out: Json = {}
  for (const [k, v] of Object.entries(node)) out[k] = cleanSchema(v)
  if (Array.isArray(out.anyOf)) {
    const kept = out.anyOf.filter((b) => !isUndefinedSentinel(b))
    if (kept.length !== out.anyOf.length) {
      const { anyOf: _drop, ...rest } = out
      if (kept.length === 1 && isRecord(kept[0])) return { ...kept[0], ...rest }
      return kept.length ? { ...rest, anyOf: kept } : rest
    }
  }
  return out
}

// A model that cannot express an optional value may send an explicit null; Studio's validation
// treats unset optionals as absent, not null. Only object properties are stripped, never array items.
function stripNulls(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stripNulls)
  if (isRecord(value)) {
    const out: Json = {}
    for (const [k, v] of Object.entries(value)) if (v !== null) out[k] = stripNulls(v)
    return out
  }
  return value
}

// --- Encoding: Studio -> Anthropic ------------------------------------------------------------

function parseArguments(json: string): Json {
  try {
    const parsed: unknown = JSON.parse(json || '{}')
    return isRecord(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

function imageBlock(url: string): Block | undefined {
  const data = /^data:(image\/[a-z+.-]+);base64,(.+)$/i.exec(url)
  if (data) return { type: 'image', source: { type: 'base64', media_type: data[1], data: data[2] } }
  if (/^https?:\/\//i.test(url)) return { type: 'image', source: { type: 'url', url } }
  return undefined
}

function encodeConversation(items: AgAiConversationItem[]): { system: string[]; messages: Message[] } {
  const system: string[] = []
  const messages: Message[] = []
  const push = (role: Message['role'], block: Block) => {
    const last = messages.at(-1)
    if (last?.role === role) last.content.push(block)
    else messages.push({ role, content: [block] })
  }

  for (const item of items) {
    if (item.type === 'function_call_output') {
      push('user', { type: 'tool_result', tool_use_id: item.callId, content: item.output || '(no output)', is_error: item.status === 'incomplete' })
    } else if (item.type === 'function_call') {
      push('assistant', { type: 'tool_use', id: item.callId, name: item.name, input: parseArguments(item.arguments) })
    } else if (item.type === 'message' && item.kind === 'input') {
      for (const c of item.content) {
        if (item.role === 'system') {
          if (c.type === 'text' && c.text) system.push(c.text)
        } else if (c.type === 'text') {
          if (c.text) push('user', { type: 'text', text: c.text })
        } else if (c.type === 'image' && c.imageUrl) {
          const block = imageBlock(c.imageUrl)
          if (block) push('user', block)
        } else if (c.type === 'file') {
          push('user', { type: 'text', text: `[Attached file${c.filename ? ` "${c.filename}"` : ''} could not be forwarded to the model.]` })
        }
      }
    } else if (item.type === 'message') {
      for (const c of item.content) {
        const text = c.type === 'text' ? c.text : c.refusal
        if (text) push('assistant', { type: 'text', text })
      }
    }
    // Reasoning items are not replayed: thinking is off, and a thinking block is only valid in the
    // conversation that produced it.
  }
  return { system, messages: repair(messages) }
}

// The API rejects a tool_use with no result and a tool_result with no call. A cancelled run can leave
// either behind in Studio's history, so drop the unpaired halves rather than fail the next turn.
function repair(messages: Message[]): Message[] {
  const used = new Set<string>()
  const resulted = new Set<string>()
  for (const m of messages) {
    for (const b of m.content) {
      if (b.type === 'tool_use') used.add(String(b.id))
      if (b.type === 'tool_result') resulted.add(String(b.tool_use_id))
    }
  }
  const out: Message[] = []
  for (const m of messages) {
    const content = m.content.filter((b) => {
      if (b.type === 'tool_use') return resulted.has(String(b.id))
      if (b.type === 'tool_result') return used.has(String(b.tool_use_id))
      return true
    })
    if (!content.length) continue
    // tool_result blocks must lead the user message that answers the calls.
    if (m.role === 'user') content.sort((a, b) => Number(b.type === 'tool_result') - Number(a.type === 'tool_result'))
    const last = out.at(-1)
    if (last?.role === m.role) last.content.push(...content)
    else out.push({ role: m.role, content })
  }
  if (out[0]?.role === 'assistant') out.unshift({ role: 'user', content: [{ type: 'text', text: '(conversation start)' }] })
  return out
}

function toolInstruction(choice: AgLlmRequest['toolChoice']): string | undefined {
  if (choice === 'required') return 'You must call at least one tool to answer this turn.'
  if (isRecord(choice)) return `You must call the tool "${String(choice.name)}" to answer this turn.`
  return undefined
}

// Strict tool use makes the model's arguments validate against the schema exactly. Studio's tools
// need it: `delegate_to` takes `type: { id: 'data' }`, and without strict mode the model sends the
// bare string. The API caps strict tools per request and rejects schemas it finds too complex, so a
// refused set is remembered and sent without `strict` from then on.
const MAX_STRICT_TOOLS = 20
const strictRefused = new Set<string>()
const toolSetKey = (tools: AgAiToolSchema[]) => tools.map((t) => t.name).sort().join(',')
const wantsStrict = (tools: AgAiToolSchema[]) => tools.length > 0 && tools.length <= MAX_STRICT_TOOLS && !strictRefused.has(toolSetKey(tools))

function buildBody(model: string, request: AgLlmRequest, strict: boolean, extraSystem?: string): Json {
  const { system, messages } = encodeConversation(request.input)
  const format = request.responseFormat
  const parts = [
    request.instructions,
    extraSystem,
    ...system,
    TOOL_GUARD,
    toolInstruction(request.toolChoice),
    // Plain JSON mode: the schema goes in the prompt, and Studio validates what comes back.
    format?.type === 'json'
      ? `Respond with only a JSON object (no prose, no code fences) matching this JSON Schema for "${format.name}": ${JSON.stringify(cleanSchema(format.schema))}`
      : undefined,
  ].filter(Boolean)

  const tools = (request.tools ?? []).map((t: AgAiToolSchema) => ({
    name: t.name,
    description: t.description,
    input_schema: cleanSchema(t.parameters),
    ...(strict && { strict: true }),
  }))
  return {
    model,
    system: parts.join('\n\n'),
    messages,
    ...(tools.length && { tools }),
    tool_choice: { type: request.toolChoice === 'none' ? 'none' : 'auto' },
  }
}

// --- Decoding: Anthropic -> Studio ------------------------------------------------------------

interface Open {
  kind: 'text' | 'tool' | 'ignored'
  id: string
  name?: string
  text: string
  json: string
}

/**
 * Translates the Messages stream into the events Studio reads, and collects the final response.
 * Anthropic is block-and-index shaped; Studio is message-shaped, keyed by id, so each open block is
 * remembered by index until its stop event.
 */
class StreamTranslator {
  private open = new Map<number, Open>()
  private output: AgAiOutputItem[] = []
  private id = ''
  private model = ''
  private stopReason: string | null = null
  private usage = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }
  error?: Error
  finished = false

  translate(ev: Json): AgAiEvent[] {
    switch (ev.type) {
      case 'message_start': {
        const m = isRecord(ev.message) ? ev.message : {}
        this.id = String(m.id ?? '')
        this.model = String(m.model ?? '')
        this.readUsage(m.usage)
        return []
      }
      case 'content_block_start':
        return this.start(num(ev.index), isRecord(ev.content_block) ? ev.content_block : {})
      case 'content_block_delta':
        return this.delta(num(ev.index), isRecord(ev.delta) ? ev.delta : {})
      case 'content_block_stop':
        return this.stop(num(ev.index))
      case 'message_delta': {
        const d = isRecord(ev.delta) ? ev.delta : {}
        if (typeof d.stop_reason === 'string') this.stopReason = d.stop_reason
        this.readUsage(ev.usage)
        return []
      }
      case 'message_stop':
        this.finished = true
        return []
      case 'error': {
        const e = isRecord(ev.error) ? ev.error : {}
        this.error ??= new Error(`${String(e.type ?? 'api_error')}: ${String(e.message ?? 'The model request failed.')}`)
        return []
      }
      default:
        return [] // ping and anything unknown
    }
  }

  private readUsage(usage: unknown) {
    if (!isRecord(usage)) return
    if (usage.input_tokens !== undefined) this.usage.input = num(usage.input_tokens)
    if (usage.output_tokens !== undefined) this.usage.output = num(usage.output_tokens)
    if (usage.cache_read_input_tokens !== undefined) this.usage.cacheRead = num(usage.cache_read_input_tokens)
    if (usage.cache_creation_input_tokens !== undefined) this.usage.cacheWrite = num(usage.cache_creation_input_tokens)
  }

  private start(index: number, block: Json): AgAiEvent[] {
    if (block.type === 'text') {
      const id = `${this.id}:${index}`
      this.open.set(index, { kind: 'text', id, text: '', json: '' })
      return [{ type: 'TEXT_MESSAGE_START', messageId: id, role: 'assistant' }]
    }
    if (block.type === 'tool_use') {
      const id = String(block.id)
      const name = String(block.name)
      this.open.set(index, { kind: 'tool', id, name, text: '', json: '' })
      return [{ type: 'TOOL_CALL_START', toolCallId: id, toolCallName: name }]
    }
    this.open.set(index, { kind: 'ignored', id: '', text: '', json: '' })
    return []
  }

  private delta(index: number, d: Json): AgAiEvent[] {
    const b = this.open.get(index)
    if (!b) return []
    if (b.kind === 'text' && d.type === 'text_delta') {
      const text = String(d.text ?? '')
      b.text += text
      return [{ type: 'TEXT_MESSAGE_CONTENT', messageId: b.id, delta: text }]
    }
    if (b.kind === 'tool' && d.type === 'input_json_delta') {
      const part = String(d.partial_json ?? '')
      b.json += part
      return part ? [{ type: 'TOOL_CALL_ARGS', toolCallId: b.id, delta: part }] : []
    }
    return []
  }

  private stop(index: number): AgAiEvent[] {
    const b = this.open.get(index)
    this.open.delete(index)
    if (!b) return []
    if (b.kind === 'text') {
      this.output.push({
        id: b.id,
        kind: 'output',
        type: 'message',
        role: 'assistant',
        status: 'completed',
        content: [{ type: 'text', text: b.text, annotations: [] }],
      })
      return [{ type: 'TEXT_MESSAGE_END', messageId: b.id }]
    }
    if (b.kind === 'tool') {
      this.output.push({
        id: b.id,
        kind: 'output',
        type: 'function_call',
        callId: b.id,
        name: b.name ?? '',
        arguments: JSON.stringify(stripNulls(parseArguments(b.json))),
        status: 'completed',
      })
      return [{ type: 'TOOL_CALL_END', toolCallId: b.id }]
    }
    return []
  }

  response(): AgLlmResponse {
    const u = this.usage
    const truncated = this.stopReason === 'max_tokens'
    const refused = this.stopReason === 'refusal'
    return {
      id: this.id,
      createdAt: Date.now(),
      model: this.model,
      output: this.output,
      status: truncated || refused ? 'incomplete' : 'completed',
      incompleteDetails: truncated ? { reason: 'max_output_tokens' } : refused ? { reason: 'content_filter' } : undefined,
      usage: {
        inputTokens: u.input + u.cacheRead + u.cacheWrite,
        outputTokens: u.output,
        totalTokens: u.input + u.cacheRead + u.cacheWrite + u.output,
        cachedInputTokens: u.cacheRead,
        cacheWriteTokens: u.cacheWrite,
      },
    }
  }
}

const post = (url: string, body: Json, signal?: AbortSignal) =>
  fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal })

async function* streamClaude(
  url: string,
  build: (strict: boolean) => Json,
  tools: AgAiToolSchema[],
  translator: StreamTranslator,
  signal?: AbortSignal,
): AsyncIterableIterator<AgAiEvent> {
  let response = await post(url, build(wantsStrict(tools)), signal)
  if (response.status === 400 && wantsStrict(tools)) {
    strictRefused.add(toolSetKey(tools))
    response = await post(url, build(false), signal)
  }
  if (!response.ok) {
    const failure = (await response.json().catch(() => ({}))) as { error?: { message?: string } }
    throw new Error(failure.error?.message || `HTTP ${response.status}: ${response.statusText}`)
  }

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  const frame = (text: string): AgAiEvent[] => {
    const data = text
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n')
    if (!data) return []
    try {
      const parsed: unknown = JSON.parse(data)
      return isRecord(parsed) ? translator.translate(parsed) : []
    } catch (e) {
      translator.error ??= e instanceof Error ? e : new Error(String(e))
      return []
    }
  }
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const f of frames) yield* frame(f)
  }
  if (buffer.trim()) yield* frame(buffer)
}

function runRequest(url: string, build: (strict: boolean) => Json, tools: AgAiToolSchema[], signal?: AbortSignal): AgLlmResponseHandler {
  const translator = new StreamTranslator()
  let resolveComplete!: (r: AgLlmResponse) => void
  let rejectComplete!: (e: Error) => void
  const complete = new Promise<AgLlmResponse>((resolve, reject) => {
    resolveComplete = resolve
    rejectComplete = reject
  })
  // A failed turn is reported once, through `complete`; this marks it observed for a consumer that
  // abandons the stream (Stop, an HTTP error) without ever awaiting it.
  void complete.catch(() => {})

  async function* wrapped(): AsyncIterableIterator<AgAiEvent> {
    try {
      yield* streamClaude(url, build, tools, translator, signal)
    } catch (e) {
      translator.error ??= e instanceof Error ? e : new Error(String(e))
    }
    if (translator.error) rejectComplete(translator.error)
    else if (translator.finished) resolveComplete(translator.response())
    else rejectComplete(new Error('Stream completed without a final response.'))
  }
  const iterator = wrapped()
  return { stream: { [Symbol.asyncIterator]: () => iterator }, complete }
}

export function claudeAdapter(options: ClaudeAdapterOptions = {}): AgLlmAdapter {
  const endpoint = options.endpoint ?? '/api/ai'
  const defaultModel = options.model ?? 'claude-haiku-5-5'
  return {
    executeTurn: (request, turn) =>
      runRequest(
        `${endpoint}/messages`,
        (strict) => buildBody(request.model?.id ?? defaultModel, request, strict, options.system),
        request.tools ?? [],
        turn?.signal,
      ),
  }
}
