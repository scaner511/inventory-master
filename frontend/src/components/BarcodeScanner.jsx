import { useEffect, useRef, useState } from 'react'
import { Html5Qrcode } from 'html5-qrcode'
import { BarcodeDetector as BarcodeDetectorPonyfill, setZXingModuleOverrides } from 'barcode-detector/ponyfill'
import zxingWasmUrl from 'zxing-wasm/reader/zxing_reader.wasm?url'
import Modal from './ui/Modal.jsx'
import { Button } from './ui/Form.jsx'

// El WASM de ZXing se sirve desde nuestro propio build (no desde un CDN).
setZXingModuleOverrides({
  locateFile: (path, prefix) => (path.endsWith('.wasm') ? zxingWasmUrl : prefix + path),
})

const NATIVE_AVAILABLE = typeof window !== 'undefined' && 'BarcodeDetector' in window

/* Escáner de códigos de barra por cámara. Abre la cámara al mostrarse.

   - Se lee a la RESOLUCIÓN COMPLETA de la cámara frame a frame:
     * BarcodeDetector nativo si existe (Android/Chrome, Edge).
     * Si no (Safari/iPhone), el mismo motor con ZXing en WebAssembly, para
       poder leer códigos pequeños.
     * Si eso falla, html5-qrcode como último respaldo.
   - Antes de aceptar un código, debe aparecer el MISMO valor en 3 lecturas
     consecutivas, para evitar datos erróneos.

   Al decodificar un código llama a onCode(code). */
export default function BarcodeScanner({ open, onClose, onCode }) {
  const [cameraStatus, setCameraStatus] = useState('idle') // idle | starting | scanning | error
  const [engine, setEngine] = useState('native') // native | zxing
  const [cameraFacing, setCameraFacing] = useState('environment')
  const [torchOn, setTorchOn] = useState(false)

  const scannerRef = useRef(null) // instancia html5-qrcode (respaldo)
  const nativeStreamRef = useRef(null) // MediaStream (motor de alta resolución)
  const videoTrackRef = useRef(null) // pista para controlar la linterna
  const nativeRafRef = useRef(0)
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const probeRef = useRef({ code: '', count: 0 }) // estabilización anti lecturas erróneas
  const activeCodeRef = useRef(false)
  const startTokenRef = useRef(0) // invalida arranques viejos si se cierra o reinicia

  function resetProbe() {
    probeRef.current = { code: '', count: 0 }
  }

  async function stopScanner() {
    if (scannerRef.current) {
      const scanner = scannerRef.current
      scannerRef.current = null
      try {
        await scanner.stop()
      } catch {
        /* ya detenido */
      }
      try {
        scanner.clear()
      } catch {
        /* sin instancia de escaneo */
      }
    }
    if (nativeRafRef.current) {
      cancelAnimationFrame(nativeRafRef.current)
      nativeRafRef.current = 0
    }
    if (nativeStreamRef.current) {
      nativeStreamRef.current.getTracks().forEach((t) => t.stop())
      nativeStreamRef.current = null
    }
    videoTrackRef.current = null
    setTorchOn(false)
    if (videoRef.current) videoRef.current.srcObject = null
    resetProbe()
    setCameraStatus('idle')
  }

  useEffect(() => {
    if (!open) return undefined
    activeCodeRef.current = false
    startCamera('environment')
    return () => {
      startTokenRef.current += 1
      stopScanner()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  function submit(value) {
    const clean = String(value || '').trim()
    if (!clean || activeCodeRef.current) return
    activeCodeRef.current = true
    startTokenRef.current += 1
    stopScanner()
    onCode(clean)
  }

  /* -------- Motor principal: frames a resolución completa -------- */
  async function startNativeCamera(facing, token) {
    const Detector = NATIVE_AVAILABLE ? window.BarcodeDetector : BarcodeDetectorPonyfill
    const detector = new Detector()
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: facing,
        width: { ideal: 4096 },
        height: { ideal: 2160 },
      },
    })
    if (token !== startTokenRef.current) {
      stream.getTracks().forEach((t) => t.stop())
      return
    }
    nativeStreamRef.current = stream
    videoTrackRef.current = stream.getVideoTracks()[0] || null
    const video = videoRef.current
    if (!video) throw new Error('Video de escaneo no disponible')
    video.srcObject = stream
    video.playsInline = true
    video.muted = true
    await video.play()

    const canvas = canvasRef.current
    if (!canvas) throw new Error('Lienzo de escaneo no disponible')
    const ctx = canvas.getContext('2d', { willReadFrequently: true })

    resetProbe()
    let lastCode = ''

    async function tick() {
      if (!nativeStreamRef.current) return
      const w = video.videoWidth
      const h = video.videoHeight
      if (w && h) {
        // Dibujar el frame a resolución NATIVA completa (sin recortar).
        canvas.width = w
        canvas.height = h
        ctx.drawImage(video, 0, 0, w, h)
        try {
          const codes = await detector.detect(canvas)
          if (codes && codes.length) {
            const value = String(codes[0].rawValue || '').trim()
            if (value && value !== lastCode) {
              lastCode = value
              resetProbe()
            }
            if (value) {
              const p = probeRef.current
              p.code = value
              p.count += 1
              // Solo aceptar tras 3 lecturas idénticas consecutivas.
              if (p.count >= 3) {
                submit(value)
                return
              }
            }
          } else {
            lastCode = ''
            resetProbe()
          }
        } catch {
          /* frame no analizable, se sigue en el siguiente */
        }
      }
      if (!nativeStreamRef.current) return
      nativeRafRef.current = requestAnimationFrame(tick)
    }
    nativeRafRef.current = requestAnimationFrame(tick)
    setCameraStatus('scanning')
  }

  /* -------- Motor de respaldo (html5-qrcode) -------- */
  async function startZxingCamera(facing, token) {
    const element = document.getElementById('barcode-reader')
    if (!element) throw new Error('Contenedor de escaneo no disponible')
    const scanner = new Html5Qrcode('barcode-reader', { verbose: false })
    scannerRef.current = scanner
    resetProbe()
    let lastCode = ''
    // html5-qrcode solo acepta 1 clave en el primer argumento; la resolución va
    // en videoConstraints (si no, lanza error y la cámara nunca abre en iOS).
    await scanner.start(
      { facingMode: facing },
      {
        fps: 30,
        videoConstraints: {
          facingMode: facing,
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
        qrbox: (w, h) => {
          // Recuadro amplio centrado para no cortar el código.
          const size = Math.max(180, Math.min(w, h) * 0.8)
          return { width: size, height: size }
        },
      },
      (decodedText) => {
        const value = String(decodedText || '').trim()
        if (value && value !== lastCode) {
          lastCode = value
          resetProbe()
        }
        if (value) {
          const p = probeRef.current
          p.code = value
          p.count += 1
          if (p.count >= 3) {
            submit(value)
          }
        }
      },
      () => {
        /* frames sin código: se ignoran */
      },
    )
    if (token !== startTokenRef.current) {
      if (scannerRef.current === scanner) await stopScanner()
      return
    }
    setCameraStatus('scanning')
  }

  async function startCamera(facing = 'environment') {
    if (window.isSecureContext === false || !navigator.mediaDevices?.getUserMedia) {
      setCameraStatus('error')
      return
    }
    await stopScanner()
    startTokenRef.current += 1
    const token = startTokenRef.current
    setCameraStatus('starting')
    setCameraFacing(facing)
    try {
      setEngine('native')
      try {
        await startNativeCamera(facing, token)
      } catch (err) {
        console.error('Motor de alta resolución:', err)
        if (token !== startTokenRef.current) return
        await stopScanner()
        setCameraStatus('starting')
        setEngine('zxing')
        // Respaldo: si el motor principal falla, intenta con html5-qrcode.
        await startZxingCamera(facing, token)
      }
    } catch (err) {
      console.error('Cámara:', err)
      if (token !== startTokenRef.current) return
      if (facing === 'environment') {
        await startCamera('user')
        return
      }
      setCameraStatus('error')
    }
  }

  async function switchCamera() {
    const next = cameraFacing === 'environment' ? 'user' : 'environment'
    await startCamera(next)
  }

  async function toggleTorch() {
    const track = videoTrackRef.current
    if (!track || typeof track.applyConstraints !== 'function') return
    const next = !torchOn
    try {
      await track.applyConstraints({ advanced: [{ torch: next }] })
      setTorchOn(next)
    } catch {
      /* el dispositivo no soporta linterna */
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="📷 Escanear código">
      <div className="space-y-3">
        <p className="text-xs text-slate-400">
          Mantén el código quieto y bien iluminado, alineado al centro. Se confirma tras 3 lecturas idénticas para
          evitar errores.
        </p>
        <div className="relative h-72 w-full overflow-hidden rounded-xl border border-slate-700">
          {/* Contenedor exclusivo de html5-qrcode: la librería vacía su contenido. */}
          <div id="barcode-reader" className="h-full w-full" />
          <video
            ref={videoRef}
            className={engine === 'native' ? 'absolute inset-0 h-full w-full object-cover' : 'hidden'}
            playsInline
            muted
          />
          <canvas ref={canvasRef} className="absolute inset-0 h-0 w-0" />
        </div>
        <div className="text-center">
          {cameraStatus === 'starting' && <p className="text-sm text-slate-400">Iniciando cámara...</p>}
          {cameraStatus === 'scanning' && (
            <div className="space-y-2">
              <p className="text-sm text-emerald-400">🔍 Escaneando... enfoca el código</p>
              <div className="flex justify-center gap-2">
                {engine === 'native' && (
                  <Button type="button" variant="ghost" onClick={toggleTorch}>
                    {torchOn ? '🔦 Apagar linterna' : '🔦 Encender linterna'}
                  </Button>
                )}
                <Button type="button" variant="ghost" onClick={switchCamera}>
                  🔄 Cambiar cámara
                </Button>
              </div>
            </div>
          )}
          {cameraStatus === 'error' && (
            <div className="space-y-2">
              <p className="text-sm text-red-400">No se pudo acceder a la cámara</p>
              <p className="text-xs text-slate-500">
                Verifica que el sitio use HTTPS (no http ni IP) y concede el permiso de cámara al navegador. En Android,
                abre con Chrome. En iPhone, permite la cámara en Ajustes › Safari › Cámara (o en el ícono «aA» de la
                barra de direcciones).
              </p>
              <Button type="button" onClick={() => startCamera('environment')}>
                🔄 Reintentar
              </Button>
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}
