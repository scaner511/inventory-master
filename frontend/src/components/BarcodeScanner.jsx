import { useEffect, useRef, useState } from 'react'
import { Html5Qrcode } from 'html5-qrcode'
import Modal from './ui/Modal.jsx'
import { Button, Input } from './ui/Form.jsx'

/* Escáner de códigos de barra.

   - "Lector USB" (PC): el lector actúa como teclado; se captura el código
     en un input enfocado y se resuelve con Enter.
   - "Cámara" (celular):
     * Si el navegador tiene BarcodeDetector (Android/Chrome, Edge), se lee a
       la RESOLUCIÓN COMPLETA de la cámara frame a frame (muy preciso).
     * Si no (Safari/iOS), se usa html5-qrcode como respaldo.
     Antes de aceptar un código, debe aparecer el MISMO valor en 3 lecturas
     consecutivas, para evitar datos erróneos.

   Al decodificar un código llama a onCode(code). */
export default function BarcodeScanner({ open, onClose, onCode }) {
  const [mode, setMode] = useState('usb')
  const [code, setCode] = useState('')
  const [cameraStatus, setCameraStatus] = useState('idle') // idle | starting | scanning | error
  const [engine, setEngine] = useState(
    typeof window !== 'undefined' && 'BarcodeDetector' in window ? 'native' : 'zxing',
  )
  const [cameraFacing, setCameraFacing] = useState('environment')
  const [torchOn, setTorchOn] = useState(false)

  const scannerRef = useRef(null) // instancia html5-qrcode (respaldo)
  const nativeStreamRef = useRef(null) // MediaStream (motor nativo)
  const videoTrackRef = useRef(null) // pista para controlar la linterna
  const nativeRafRef = useRef(0)
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const probeRef = useRef({ code: '', count: 0 }) // estabilización anti lecturas erróneas
  const activeCodeRef = useRef('')

  const NATIVE_AVAILABLE = typeof window !== 'undefined' && 'BarcodeDetector' in window

  function resetProbe() {
    probeRef.current = { code: '', count: 0 }
  }

  async function stopScanner() {
    if (scannerRef.current) {
      try {
        await scannerRef.current.stop()
      } catch {
        /* ya detenido */
      }
      try {
        scannerRef.current.clear()
      } catch {
        /* sin instancia de escaneo */
      }
      scannerRef.current = null
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
    if (!open) {
      stopScanner()
      setMode('usb')
      setCode('')
      setCameraStatus('idle')
      activeCodeRef.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(
    () => () => {
      stopScanner()
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

  function submit(value) {
    const clean = String(value || '').trim()
    if (!clean || activeCodeRef.current) return
    activeCodeRef.current = true
    stopScanner()
    onCode(clean)
  }

  /* -------- Motor nativo (BarcodeDetector): resolucion completa -------- */
  async function startNativeCamera(facing) {
    const formatWhitelist = undefined // todos los formatos soportados por el navegador
    const detector = new BarcodeDetector({ formats: formatWhitelist })
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: facing,
        width: { ideal: 4096 },
        height: { ideal: 2160 },
      },
    })
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
      nativeRafRef.current = requestAnimationFrame(tick)
    }
    nativeRafRef.current = requestAnimationFrame(tick)
    setCameraStatus('scanning')
  }

  /* -------- Motor de respaldo (html5-qrcode) -------- */
  async function startZxingCamera(facing) {
    const element = document.getElementById('barcode-reader')
    if (!element) throw new Error('Contenedor de escaneo no disponible')
    scannerRef.current = new Html5Qrcode('barcode-reader', { verbose: false })
    resetProbe()
    let lastCode = ''
    await scannerRef.current.start(
      { facingMode: facing, width: { ideal: 4096 }, height: { ideal: 2160 } },
      {
        fps: 30,
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
    setCameraStatus('scanning')
  }

  async function startCamera(facing = 'environment') {
    if (window.isSecureContext === false) {
      setCameraStatus('error')
      return
    }
    try {
      await stopScanner()
      setCameraStatus('starting')
      resetProbe()
      setEngine(NATIVE_AVAILABLE ? 'native' : 'zxing')
      setCameraFacing(facing)
      if (NATIVE_AVAILABLE) {
        try {
          await startNativeCamera(facing)
        } catch (err) {
          console.error('Motor nativo:', err)
          // Respaldo: si el nativo falla, intenta con html5-qrcode.
          await startZxingCamera(facing)
        }
      } else {
        await startZxingCamera(facing)
      }
    } catch (err) {
      console.error('Cámara:', err)
      if (facing === 'environment') {
        try {
          await startCamera('user')
          return
        } catch {
          /* la frontal tampoco sirvió */
        }
      }
      setCameraStatus('error')
    }
  }

  async function switchCamera() {
    const next = cameraFacing === 'environment' ? 'user' : 'environment'
    setCameraFacing(next)
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

  function handleUsbSubmit(e) {
    e.preventDefault()
    submit(code)
  }

  function switchMode(next) {
    if (next !== 'camera') {
      stopScanner()
    }
    setMode(next)
    setCode('')
    setCameraStatus('idle')
  }

  return (
    <Modal open={open} onClose={onClose} title="📷 Escanear código">
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-2">
          <Button
            type="button"
            variant={mode === 'usb' ? 'primary' : 'ghost'}
            onClick={() => switchMode('usb')}
          >
            ⌨️ Lector USB
          </Button>
          <Button
            type="button"
            variant={mode === 'camera' ? 'primary' : 'ghost'}
            onClick={() => switchMode('camera')}
          >
            📱 Cámara
          </Button>
        </div>

        {mode === 'usb' ? (
          <form onSubmit={handleUsbSubmit} className="space-y-2">
            <p className="text-xs text-slate-400">
              Apunta el lector USB y escanea. El código aparece aquí y se busca al presionar Enter.
            </p>
            <Input
              autoFocus
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Código escaneado..."
            />
            <Button type="submit" className="w-full">
              Buscar producto
            </Button>
          </form>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-slate-400">
              Mantén el código quieto y bien iluminado, alineado al centro. Se confirma tras 3 lecturas
              idénticas para evitar errores. Motor: {engine === 'native' ? 'nativo (alta precisión)' : 'compatibilidad'}.
            </p>
            <div
              id="barcode-reader"
              className="relative h-72 w-full overflow-hidden rounded-xl border border-slate-700"
            >
              {engine === 'native' && (
                <video ref={videoRef} className="h-full w-full object-cover" playsInline muted />
              )}
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
                    <Button type="button" variant="ghost" onClick={switchCamera} disabled={cameraStatus !== 'scanning'}>
                      🔄 Cambiar cámara
                    </Button>
                  </div>
                </div>
              )}
              {cameraStatus === 'error' && (
                <div className="space-y-2">
                  <p className="text-sm text-red-400">No se pudo acceder a la cámara</p>
                  <p className="text-xs text-slate-500">
                    Verifica que el sitio use HTTPS (no http ni IP) y concede el permiso de cámara al navegador.
                    En Android, abre con Chrome. En los ajustes del navegador, revisa que la cámara no esté bloqueada.
                  </p>
                  <Button type="button" onClick={() => startCamera('environment')}>
                    🔄 Reintentar
                  </Button>
                </div>
              )}
              {cameraStatus === 'idle' && (
                <Button type="button" onClick={() => startCamera('environment')}>
                  📷 Activar cámara
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}