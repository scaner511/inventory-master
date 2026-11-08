// Capa de "Recepción Inteligente" basada SOLO en IA (visión).
//
// La UI llama siempre a `extractDocument(file, { aiProvider, token, model })` y
// obtiene SIEMPRE la misma forma de salida. El reconocimiento lo hace un modelo
// multimodal (lee la foto/imagen del documento directamente, como en la app
// Android TiReport):
//   - Puter  : POST https://api.puter.com/drivers/call (interface
//              "puter-chat-completion", método "complete"), token personal.
//   - Gemini : POST generativelanguage.googleapis.com/v1beta (API key).
// El modelo concreto lo define la config del cliente (ver GET /api/ai/config).
//
// pdf.js se carga por CDN de forma perezosa para renderizar PDFs a imagen.

const PDFJS_VERSION = '4.7.76'
const PDFJS_CDN = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${PDFJS_VERSION}/build/pdf.min.mjs`
const PDFJS_WORKER = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${PDFJS_VERSION}/build/pdf.worker.min.mjs`

const PUTER_DRIVERS_URL = 'https://api.puter.com/drivers/call'
const GEMINI_BASE = 'https://generativelanguage.googleapis.com/v1beta/'
const DEFAULT_PUTER_MODEL = 'google:google/gemini-3.8-flash'
const DEFAULT_GEMINI_MODEL = 'gemini-2.5-flash'

const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf']

let _pdfjsPromise = null

async function loadPdfJs() {
  if (!_pdfjsPromise) {
    _pdfjsPromise = import(/* @vite-ignore */ PDFJS_CDN).then((mod) => {
      mod.GlobalWorkerOptions.workerSrc = PDFJS_WORKER
      return mod
    })
  }
  return _pdfjsPromise
}

export function isAccepted(file) {
  return ACCEPTED.includes(file.type)
}

// ---- Preparación de imagen: PDF -> PNG; toda imagen -> JPEG (máx 1280 px) ----
// Igual que la app: se reduce y se manda JPEG base64, lo que da fotos ligeras
// que el modelo lee bien (fotos gigantes de móvil suelen fallar o expirar).
async function renderPdfToBlobs(file, onProgress) {
  const pdfjs = await loadPdfJs()
  const buf = await file.arrayBuffer()
  const pdf = await pdfjs.getDocument({ data: buf }).promise
  const blobs = []
  const scale = 2.0
  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i)
    const viewport = page.getViewport({ scale })
    const canvas = document.createElement('canvas')
    canvas.width = viewport.width
    canvas.height = viewport.height
    const ctx = canvas.getContext('2d')
    await page.render({ canvasContext: ctx, viewport }).promise
    const blob = await new Promise((res) => canvas.toBlob(res, 'image/jpeg', 0.85))
    blobs.push(blob)
    if (onProgress) onProgress({ status: 'renderizando PDF', progress: i / (pdf.numPages + 1) })
  }
  return blobs
}

async function fileToJpegBlob(file, maxDim = 1280, quality = 0.8) {
  const url = URL.createObjectURL(file)
  try {
    const img = await new Promise((resolve, reject) => {
      const el = new Image()
      el.onload = () => resolve(el)
      el.onerror = () => reject(new Error('No se pudo leer la imagen'))
      el.src = url
    })
    let { width, height } = img
    const mayor = Math.max(width, height)
    if (mayor > maxDim) {
      const factor = maxDim / mayor
      width = Math.round(width * factor)
      height = Math.round(height * factor)
    }
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    ctx.drawImage(img, 0, 0, width, height)
    return await new Promise((res) => canvas.toBlob(res, 'image/jpeg', quality))
  } finally {
    URL.revokeObjectURL(url)
  }
}

async function prepareImages(file, onProgress) {
  if (file.type === 'application/pdf') {
    return renderPdfToBlobs(file, onProgress)
  }
  return [await fileToJpegBlob(file)]
}

async function blobToBase64(blob) {
  const buf = await blob.arrayBuffer()
  const bytes = new Uint8Array(buf)
  let binary = ''
  const chunk = 0x8000
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk))
  }
  return btoa(binary)
}

// ---- Extracción del JSON de la respuesta ----
const AI_PROMPT = `Eres un asistente experto en leer documentos de almacén, remisiones, packing slips y facturas (en español e inglés).
Analiza la IMAGEN del documento y extrae ÚNICAMENTE los productos/renglones listados.
Devuelve EXCLUSIVAMENTE un objeto JSON válido, sin explicaciones ni markdown, con esta forma:
{"items":[{"code":"","description":"","quantity":0,"pallets":0}]}
Reglas:
- "code": el código/SKU/artículo/clave del producto si aparece. Si no hay, deja "".
- "description": el nombre o descripción del producto. No repitas el código aquí.
- "quantity": la cantidad (CTD/QTY/unidades/piezas). Si hay varias columnas de cantidad, usa la de unidades. Si no aparece, usa 1.
- "pallets": número de tarimas/pallets/bultos/cajas si aparece. Si no, usa 0.
- Lee la imagen completa: puede estar rotada o ser una foto de papel.
- NO incluyas filas de totales, subtotales, direcciones, fechas ni encabezados.
- Si un renglón no tiene cantidad clara, asume 1.
- Responde solo con el JSON.`

function normalizarJson(texto) {
  const t = (texto || '').trim()
  let cuerpo = t
  if (cuerpo.startsWith('```')) {
    cuerpo = cuerpo.replace(/^```(?:json)?/i, '').replace(/```\s*$/, '')
  }
  const inicio = cuerpo.indexOf('{')
  const fin = cuerpo.lastIndexOf('}')
  let frag = cuerpo
  if (inicio >= 0 && fin > inicio) frag = cuerpo.slice(inicio, fin + 1)
  else if (inicio >= 0) frag = cuerpo.slice(inicio)
  return repararJson(frag.trim())
}

function repararJson(frag) {
  const sb = []
  const pila = []
  let enCadena = false
  let escape = false
  for (const ch of frag) {
    if (escape) {
      sb.push(ch)
      escape = false
      continue
    }
    if (ch === '\\') {
      sb.push(ch)
      escape = true
      continue
    }
    if (ch === '"') {
      enCadena = !enCadena
      sb.push(ch)
      continue
    }
    if (!enCadena) {
      if (ch === '{') pila.push('}')
      else if (ch === '[') pila.push(']')
      else if (ch === '}' || ch === ']') {
        if (pila.length && pila[pila.length - 1] === ch) pila.pop()
      }
    }
    sb.push(ch)
  }
  if (enCadena) sb.push('"')

  let t = sb.join('').trimEnd()
  while (t.length) {
    const ultimo = t[t.length - 1]
    if (ultimo === ',') {
      t = t.slice(0, -1).trimEnd()
    } else if (ultimo === ':') {
      const m = /"[^"]*"\s*:\s*$/.exec(t)
      t = (m ? t.slice(0, m.index) : t.slice(0, -1)).trimEnd()
    } else {
      break
    }
  }
  while (pila.length) t += pila.pop()
  return t
}

function parseAiItems(raw) {
  if (raw == null) return null
  let text = raw
  if (typeof raw === 'object') {
    text = raw?.message?.content ?? raw?.text ?? raw?.content ?? raw
    if (Array.isArray(text)) {
      text = text.map((b) => (typeof b === 'string' ? b : b?.text || '')).join('')
    }
  }
  if (typeof text !== 'string') return null
  let obj
  try {
    obj = JSON.parse(normalizarJson(text))
  } catch {
    return null
  }
  const items = Array.isArray(obj) ? obj : obj?.items
  return Array.isArray(items) ? items : null
}

function toRows(items) {
  return items
    .map((it) => ({
      code: String(it.code || it.codigo || '').trim(),
      description: String(it.description || it.descripcion || '').trim(),
      quantity: Math.max(parseInt(it.quantity, 10) || 1, 1),
      pallets: Math.max(parseInt(it.pallets, 10) || 0, 0),
    }))
    .filter((r) => r.code || r.description)
}

// ---- Proveedor Puter (REST) ----
async function puterExtractImage(token, blob, model) {
  const b64 = await blobToBase64(blob)
  const res = await fetch(PUTER_DRIVERS_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      interface: 'puter-chat-completion',
      method: 'complete',
      args: {
        model: model || DEFAULT_PUTER_MODEL,
        temperature: 0.1,
        max_tokens: 2048,
        messages: [
          { role: 'system', content: AI_PROMPT },
          {
            role: 'user',
            content: [
              { type: 'text', text: 'Extrae los productos de esta imagen (lee la foto del documento).' },
              { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${b64}` } },
            ],
          },
        ],
      },
      auth_token: token,
    }),
  })
  const texto = await res.text()
  if (!res.ok) {
    throw new Error(`Puter respondió ${res.status}: ${texto.slice(0, 300)}`)
  }
  let raiz
  try {
    raiz = JSON.parse(texto)
  } catch {
    throw new Error('Puter devolvió una respuesta no válida')
  }
  if (raiz.success === false) {
    const err = raiz.error || {}
    const code = String(err.code || '')
    if (code.includes('insufficient_funds') || code.includes('no_usage')) {
      throw new Error('Se agotó la cuota de Puter. Revisa tu saldo o cambia a Gemini.')
    }
    if (code.includes('subscription_required')) {
      throw new Error(`Puter exige plan de pago: ${err.message || code}`)
    }
    throw new Error(`Puter: ${err.message || code || 'respuesta vacía'}`)
  }
  const items = parseAiItems(raiz?.result?.message?.content)
  if (!items) throw new Error('La IA no devolvió un JSON válido (Puter)')
  return toRows(items)
}

// ---- Proveedor Gemini (REST) ----
async function geminiExtractImage(token, blob, model) {
  const b64 = await blobToBase64(blob)
  const payload = {
    contents: [
      {
        parts: [
          { text: AI_PROMPT },
          { inline_data: { mime_type: 'image/jpeg', data: b64 } },
        ],
      },
    ],
    generationConfig: {
      temperature: 0.1,
      maxOutputTokens: 2048,
      responseMimeType: 'application/json',
      responseSchema: {
        type: 'object',
        properties: {
          items: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                code: { type: 'string' },
                description: { type: 'string' },
                quantity: { type: 'integer' },
                pallets: { type: 'integer' },
              },
            },
          },
        },
      },
    },
  }
  const url = `${GEMINI_BASE}models/${model || DEFAULT_GEMINI_MODEL}:generateContent?key=${encodeURIComponent(token)}`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify(payload),
  })
  const texto = await res.text()
  if (!res.ok) {
    let msg = texto.slice(0, 300)
    try {
      msg = JSON.parse(texto)?.error?.message || msg
    } catch {
      /* texto crudo */
    }
    throw new Error(`Gemini respondió ${res.status}: ${msg}`)
  }
  const crudo = JSON.parse(texto)?.candidates?.[0]?.content?.parts?.[0]?.text
  const items = parseAiItems(crudo)
  if (!items) throw new Error('La IA no devolvió un JSON válido (Gemini)')
  return toRows(items)
}

async function aiExtractImage(provider, token, blob, model) {
  if (provider === 'gemini') return geminiExtractImage(token, blob, model)
  return puterExtractImage(token, blob, model)
}

/**
 * Reconoce un documento con IA (visión). Renderiza PDFs y baja cada página.
 * @param aiProvider 'puter' | 'gemini'.
 * @param token token/API key del proveedor del cliente.
 * @param model modelo a usar.
 * @returns {Promise<{rows:Array, engine:'ai', pages:number}>}
 */
export async function extractDocument(file, { onProgress, aiProvider = 'puter', token, model } = {}) {
  if (!file) throw new Error('No se recibió ningún archivo')
  if (!token) throw new Error('La IA no tiene token configurado para este cliente. Pídelo al administrador.')

  const images = await prepareImages(file, onProgress)
  const all = []
  for (let i = 0; i < images.length; i++) {
    if (onProgress) {
      onProgress({ status: `Analizando con IA (${i + 1}/${images.length})`, progress: (i + 1) / (images.length + 1) })
    }
    const rows = await aiExtractImage(aiProvider, token, images[i], model)
    all.push(...rows)
  }
  return { rows: all, text: '', confidence: 100, pages: images.length, engine: 'ai' }
}

/**
 * Cruza las filas contra un catálogo para marcar existentes/desconocidos.
 * @param rows filas { code, description, quantity, pallets }
 * @param products lista con { code, name, stock }
 */
export function matchRows(rows, products) {
  const fold = (s) =>
    (s || '')
      .toString()
      .trim()
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
  const byCode = new Map()
  const byName = new Map()
  for (const p of products || []) {
    byCode.set(fold(p.code), p)
    byName.set(fold(p.name), p)
  }
  return rows.map((r) => {
    const hit = byCode.get(fold(r.code)) || byName.get(fold(r.description)) || null
    return {
      ...r,
      product: hit,
      exists: !!hit,
      ok: !!(r.code || r.description) && r.quantity > 0,
    }
  })
}
