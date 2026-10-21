// Capa de OCR para "Recepción Inteligente".
//
// Arquitectura por adaptadores: la UI llama siempre a `extractDocument(file)`
// y obtiene SIEMPRE la misma forma de salida, sin depender del motor.
// El motor por defecto es Tesseract.js (100% en el navegador, sin subir el
// documento a ningún servidor). Para migrar a Google Vision / otro proveedor
// basta con implementar un adaptador con la misma firma y pasarlo en
// `provider`, sin tocar la UI.
//
// Tesseract.js y pdf.js se cargan por CDN de forma perezosa (solo la primera
// vez) para no engordar el bundle ni requerir dependencias nuevas en npm.

const TESSERACT_VERSION = '5.1.0'
const TESSERACT_CDN = `https://cdn.jsdelivr.net/npm/tesseract.js@${TESSERACT_VERSION}/dist/tesseract.min.js`
const TESSERACT_WORKER = `https://cdn.jsdelivr.net/npm/tesseract.js@${TESSERACT_VERSION}/dist/worker.min.js`
const TESSERACT_CORE = 'https://cdn.jsdelivr.net/npm/tesseract.js-core@5.1.0'
const TESSERACT_LANG = 'https://tessdata.projectnaptha.com/4.0.0'
const PDFJS_VERSION = '4.7.76'
const PDFJS_CDN = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${PDFJS_VERSION}/build/pdf.min.mjs`
const PDFJS_WORKER = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${PDFJS_VERSION}/build/pdf.worker.min.mjs`

const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf']

let _tesseractPromise = null
let _pdfjsPromise = null

function loadScript(src) {
  return new Promise((resolve, reject) => {
    if ([...document.scripts].some((s) => s.src === src)) return resolve()
    const el = document.createElement('script')
    el.src = src
    el.async = true
    el.onload = () => resolve()
    el.onerror = () => reject(new Error(`No se pudo cargar ${src}`))
    document.head.appendChild(el)
  })
}

async function loadTesseract() {
  if (!_tesseractPromise) {
    _tesseractPromise = loadScript(TESSERACT_CDN).then(() => {
      if (!window.Tesseract) throw new Error('Tesseract.js no disponible')
      return window.Tesseract
    })
  }
  return _tesseractPromise
}

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

// ---- Motor Tesseract ----
async function tesseractExtract(file, onProgress) {
  const Tesseract = await loadTesseract()
  const { data } = await Tesseract.recognize(file, 'spa+eng', {
    workerPath: TESSERACT_WORKER,
    corePath: TESSERACT_CORE,
    langPath: TESSERACT_LANG,
    logger: (m) => {
      if (onProgress && m.status) {
        onProgress({
          status: m.status,
          progress: typeof m.progress === 'number' ? m.progress : 0,
        })
      }
    },
  })
  return { text: data.text || '', confidence: data.confidence ?? 0 }
}

async function renderPdfToBlob(file, onProgress) {
  const pdfjs = await loadPdfJs()
  const buf = await file.arrayBuffer()
  const pdf = await pdfjs.getDocument({ data: buf }).promise
  const pages = []
  const scale = 2.0 // mayor resolución => mejor OCR
  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i)
    const viewport = page.getViewport({ scale })
    const canvas = document.createElement('canvas')
    canvas.width = viewport.width
    canvas.height = viewport.height
    const ctx = canvas.getContext('2d')
    await page.render({ canvasContext: ctx, viewport }).promise
    const blob = await new Promise((res) => canvas.toBlob(res, 'image/png'))
    pages.push(blob)
    if (onProgress) {
      onProgress({ status: 'rendering pdf', progress: i / (pdf.numPages + 1) })
    }
  }
  return pages
}

/**
 * Extrae texto de una imagen o PDF.
 * @returns {Promise<{text:string, confidence:number, pages:number}>}
 */
export async function extractDocument(file, { onProgress, provider } = {}) {
  if (provider) return provider(file, { onProgress })
  if (!file) throw new Error('No se recibió ningún archivo')

  const isPdf = file.type === 'application/pdf'
  const images = isPdf ? await renderPdfToBlob(file, onProgress) : [file]

  const texts = []
  let confidenceSum = 0
  for (let i = 0; i < images.length; i++) {
    const { text, confidence } = await tesseractExtract(images[i], (p) => {
      if (onProgress) {
        const base = isPdf ? 1 / (images.length + 1) : 0
        onProgress({
          status: p.status,
          progress: base + (p.progress || 0) * (1 - base),
        })
      }
    })
    texts.push(text)
    confidenceSum += confidence || 0
  }

  return {
    text: texts.join('\n'),
    confidence: images.length ? confidenceSum / images.length : 0,
    pages: images.length,
  }
}

// ---------------------------------------------------------------------------
// Parser heurístico: convierte el texto OCR en filas estructuradas.
// Columnas soportadas: CÓDIGO/SKU, DESCRIPCIÓN/PRODUCTO, CANTIDAD/QTY/CTD,
// TARIMAS/PALLETS. Tolerante a documentos variables (packing slips, facturas).
// ---------------------------------------------------------------------------

const CODE_KEYS = ['codigo', 'código', 'code', 'sku', 'clave', 'item', 'art', 'articulo', 'referencia']
const DESC_KEYS = ['descripcion', 'descripción', 'descrip', 'producto', 'nombre', 'detalle', 'concepto', 'material']
const QTY_KEYS = ['cantidad', 'cant', 'qty', 'ctd', 'quantity', 'unidades', 'pzs', 'piezas', 'uds']
const PALLET_KEYS = ['tarima', 'tarimas', 'pallet', 'pallets', 'bulto', 'bultos', 'cajas']

function fold(s) {
  return (s || '')
    .toString()
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
}

function keyIndex(headerCells, keys) {
  for (let i = 0; i < headerCells.length; i++) {
    const h = fold(headerCells[i])
    if (keys.some((k) => h === k || h.includes(k))) return i
  }
  return -1
}

// Divide una línea en celdas. Prioriza separadores de tabla; si no hay,
// usa 2+ espacios o tabuladores (muy común en OCR de columnas).
function splitCells(line) {
  let cells = line.split(/[|\t;]+/)
  if (cells.length < 2) cells = line.split(/\s{2,}/)
  return cells.map((c) => c.trim()).filter((c) => c.length > 0)
}

function toInt(s) {
  const m = (s || '').toString().match(/\d[\d.,]*/)
  if (!m) return null
  return parseInt(m[0].replace(/[.,]/g, ''), 10)
}

function looksLikeCode(s) {
  const t = (s || '').trim()
  if (t.length < 2 || t.length > 20) return false
  if (/\s/.test(t)) return false
  return /[0-9]/.test(t) || /^[A-Z0-9][A-Z0-9._/-]+$/i.test(t)
}

/**
 * Parsea el texto OCR en filas { code, description, quantity, pallets }.
 * Estrategia:
 *  1) Detectar una fila de encabezado y mapear columnas por su nombre.
 *  2) Para líneas siguientes, extraer según el mapeo.
 *  3) Fallback por heurística: primer token tipo código, primer entero como cantidad.
 */
export function parseDocumentRows(text) {
  const rawLines = (text || '')
    .split(/\r?\n/)
    .map((l) => l.replace(/\s+$/g, ''))
    .filter((l) => l.trim().length > 0)
  if (!rawLines.length) return { rows: [], mapping: null }

  let mapping = null
  let headerIdx = -1
  for (let i = 0; i < Math.min(rawLines.length, 15); i++) {
    const cells = splitCells(rawLines[i])
    if (cells.length < 2) continue
    const code = keyIndex(cells, CODE_KEYS)
    const desc = keyIndex(cells, DESC_KEYS)
    const qty = keyIndex(cells, QTY_KEYS)
    const pal = keyIndex(cells, PALLET_KEYS)
    // Consideramos encabezado si reconocemos código/descripción y cantidad.
    if ((code >= 0 || desc >= 0) && qty >= 0) {
      mapping = { code, desc, qty, pal }
      headerIdx = i
      break
    }
  }

  const rows = []
  const start = headerIdx >= 0 ? headerIdx + 1 : 0
  for (let i = start; i < rawLines.length; i++) {
    const line = rawLines[i]
    if (/^(total|subtotal|suma|gran total|observ|firma|pagina|page)/i.test(line.trim())) continue
    const cells = splitCells(line)

    let code = ''
    let description = ''
    let quantity = null
    let pallets = null

    if (mapping && cells.length > 1) {
      if (mapping.code >= 0 && cells[mapping.code] !== undefined) code = cells[mapping.code]
      if (mapping.desc >= 0 && cells[mapping.desc] !== undefined) description = cells[mapping.desc]
      if (mapping.qty >= 0 && cells[mapping.qty] !== undefined) quantity = toInt(cells[mapping.qty])
      if (mapping.pal >= 0 && cells[mapping.pal] !== undefined) pallets = toInt(cells[mapping.pal])
    }

    // Fallback heurístico por línea.
    const tokens = line.split(/\s+/).filter(Boolean)
    if (!code) {
      const idx = tokens.findIndex(looksLikeCode)
      if (idx >= 0) {
        code = tokens[idx]
        if (!description) description = tokens.slice(idx + 1).join(' ')
      }
    }
    if (quantity == null) {
      const nums = tokens
        .map((t) => ({ t, n: toInt(t) }))
        .filter((x) => x.n != null)
      if (nums.length) quantity = nums[nums.length - 1].n
    }
    if (!description && tokens.length > 1) {
      description = tokens.slice(1).filter((t) => !/^\d+$/.test(t)).join(' ')
    }

    if (!code && !description) continue
    if (!code && !quantity) continue

    rows.push({
      code: (code || '').trim(),
      description: (description || '').replace(/\s{2,}/g, ' ').trim(),
      quantity: quantity && quantity > 0 ? quantity : 1,
      pallets: pallets && pallets > 0 ? pallets : 0,
    })
  }

  return { rows, mapping }
}

/**
 * Cruza las filas OCR contra un catálogo para marcar existentes/desconocidos.
 * @param rows filas de parseDocumentRows
 * @param products lista con { code, name, stock }
 */
export function matchRows(rows, products) {
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
      // Confianza local de la fila (para la advertencia <80%).
      ok: !!(r.code || r.description) && r.quantity > 0,
    }
  })
}
