import { useEffect, useRef, useState } from 'react'
import { Html5Qrcode } from 'html5-qrcode'
import Modal from './ui/Modal.jsx'
import { Button, Input } from './ui/Form.jsx'

/* Escáner de códigos de barra.
   - "Lector USB" (PC): el lector actúa como teclado; se captura el código
     en un input enfocado y se resuelve con Enter.
   - "Cámara" (celular): usa la cámara trasera (requiere HTTPS).
   Al decodificar un código llama a onCode(code). */
export default function BarcodeScanner({ open, onClose, onCode }) {
  const [mode, setMode] = useState('usb')
  const [code, setCode] = useState('')
  const [cameraStatus, setCameraStatus] = useState('idle') // idle | starting | scanning | error
  const scannerRef = useRef(null)
  const activeCodeRef = useRef('')

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
    setCameraStatus('idle')
  }

  useEffect(() => {
    if (!open) {
      if (scannerRef.current) stopScanner()
      setMode('usb')
      setCode('')
      setCameraStatus('idle')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => () => {
    if (scannerRef.current) stopScanner()
  }, [])

  async function startCamera() {
    setCameraStatus('starting')
    try {
      if (scannerRef.current) await stopScanner()
      scannerRef.current = new Html5Qrcode('barcode-reader')
      await scannerRef.current.start(
        { facingMode: 'environment' },
        { fps: 10, qrbox: { width: 220, height: 220 } },
        (decodedText) => {
          if (!activeCodeRef.current) {
            submit(decodedText)
          }
        },
        () => {
          /* frames sin código: se ignoran */
        },
      )
      setCameraStatus('scanning')
    } catch (err) {
      setCameraStatus('error')
      console.error(err)
    }
  }

  function submit(value) {
    const clean = String(value || '').trim()
    if (!clean) return
    if (scannerRef.current) stopScanner()
    onCode(clean)
  }

  function handleUsbSubmit(e) {
    e.preventDefault()
    submit(code)
  }

  function switchMode(next) {
    if (scannerRef.current) stopScanner()
    setMode(next)
    setCameraStatus('idle')
    setCode('')
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
              Enciende la cámara y enfoca el código. Funciona mejor con la cámara trasera.
            </p>
            {cameraStatus === 'scanning' ? (
              <div id="barcode-reader" className="w-full overflow-hidden rounded-xl border border-slate-700" />
            ) : (
              <div className="flex h-52 items-center justify-center rounded-xl border border-dashed border-slate-700 bg-slate-800/40 text-center">
                {cameraStatus === 'starting' && <p className="text-sm text-slate-400">Iniciando cámara...</p>}
                {cameraStatus === 'error' && (
                  <div className="space-y-2 px-4">
                    <p className="text-sm text-red-400">No se pudo acceder a la cámara</p>
                    <p className="text-xs text-slate-500">
                      Verifica los permisos de cámara y que el sitio use HTTPS.
                    </p>
                  </div>
                )}
                {cameraStatus === 'idle' && (
                  <Button type="button" onClick={startCamera}>
                    📷 Activar cámara
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  )
}