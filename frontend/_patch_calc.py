# -*- coding: utf-8 -*-
path = 'src/pages/Calculator.jsx'
src = open(path, encoding='utf-8').read()

# 1) imports
old = "import { getCalculatorProducts, getSettings } from '../api/index.js'"
new = ("import {\n"
       "  getCalculatorProducts,\n"
       "  getSettings,\n"
       "  searchCalculatorProspects,\n"
       "  registerCalculatorVisit,\n"
       "} from '../api/index.js'")
assert src.count(old) == 1
src = src.replace(old, new, 1)

# 2) firma + api de visita por defecto
old = "export default function Calculator({ storageKey = 'masterCalculadora', extraProducts, calcSettings, businessName }) {"
new = ("export default function Calculator({ storageKey = 'masterCalculadora', extraProducts, calcSettings, businessName, visitApi }) {\n"
       "  // Sincronización de visitas con prospectos/citas. La página pública pasa\n"
       "  // su propia API ligada al token+dispositivo; en el panel se usan los\n"
       "  // endpoints autenticados por defecto.\n"
       "  const visitSearch = visitApi ? visitApi.search : searchCalculatorProspects\n"
       "  const visitRegister = visitApi ? visitApi.register : registerCalculatorVisit")
assert src.count(old) == 1
src = src.replace(old, new, 1)

# 3) estado extra tras hydrated
old = "  const [hydrated, setHydrated] = useState(false)\n"
new = old + (
    "  // Resultado de la visita (sincroniza prospectos y calendario)\n"
    "  const [showVisit, setShowVisit] = useState(false)\n"
    "  const [prospectQuery, setProspectQuery] = useState('')\n"
    "  const [prospectResults, setProspectResults] = useState([])\n"
    "  const [prospectPick, setProspectPick] = useState(null)\n"
    "  const [visitNote, setVisitNote] = useState('')\n"
    "  const [rescheduleAt, setRescheduleAt] = useState('')\n"
    "  const [visitBusy, setVisitBusy] = useState('')\n"
)
assert src.count(old) == 1
src = src.replace(old, new, 1)

open(path, 'w', encoding='utf-8', newline='\n').write(src)
print('part1 OK')
EOF_MARKER = None
import sys
sys.exit(0)
# fin parte 1
PYEOF
python _patch_calc.py && rm _patch_calc.py && echo PART1-DONE
python - <<'PYEOF'
# -*- coding: utf-8 -*-
path = 'src/pages/Calculator.jsx'
src = open(path, encoding='utf-8').read()

# 4) handlers antes del return
anchor = "  return (\n    <div className=\"max-w-4xl mx-auto space-y-6\">"
assert src.count(anchor) == 1
handlers = '''  // Búsqueda de prospectos con debounce (nombre o teléfono)
  useEffect(() => {
    const q = prospectQuery.trim()
    if (q.length < 2) {
      setProspectResults([])
      return
    }
    const t = setTimeout(async () => {
      try {
        setProspectResults(await visitSearch(q))
      } catch {
        setProspectResults([])
      }
    }, 350)
    return () => clearTimeout(t)
  }, [prospectQuery, visitSearch])

  function pickProspect(p) {
    setProspectPick(p)
    setProspectQuery(p.full_name)
    setProspectResults([])
    if (p.phone && !clientPhone) setClientPhone(p.phone)
    if (!clientName) setClientName(p.full_name)
  }

  function clearProspectPick() {
    setProspectPick(null)
    setProspectQuery('')
    setProspectResults([])
  }

  async function registerVisit(result) {
    if (result === 'reagendado' && !rescheduleAt) {
      return toast.error('Indica la fecha y hora para reagendar')
    }
    setVisitBusy(result)
    try {
      const res = await visitRegister({
        prospect_id: prospectPick ? prospectPick.id : null,
        client_name: clientName || null,
        client_phone: clientPhone || null,
        result,
        reschedule_at: result === 'reagendado' ? new Date(rescheduleAt).toISOString() : null,
        note: visitNote || null,
        quote_total: totalPrice || null,
      })
      toast.success(
        result === 'compra'
          ? `Compra registrada: ${res.prospect_name} marcado como cliente`
          : `Visita reagendada: nueva cita en el calendario`
      )
      setProspectPick(null)
      setProspectQuery('')
      setProspectResults([])
      setVisitNote('')
      setRescheduleAt('')
      setShowVisit(false)
    } catch (err) {
      toast.error(err?.message || 'No se pudo registrar la visita')
    } finally {
      setVisitBusy('')
    }
  }

'''
src = src.replace(anchor, handlers + anchor, 1)

# 5) UI: antes del cierre del contenedor principal
old_tail = """          <button
            onClick={clearAll}
            className="flex-1 rounded-lg bg-red-600 px-4 py-3 font-semibold text-white transition hover:bg-red-700"
          >
            Limpiar Todo
          </button>
        </div>
      </div>
    </div>
  )
}
"""
assert src.endswith(old_tail), 'tail no coincide'
ui = """          <button
            onClick={clearAll}
            className="flex-1 rounded-lg bg-red-600 px-4 py-3 font-semibold text-white transition hover:bg-red-700"
          >
            Limpiar Todo
          </button>
        </div>

        {/* Resultado de la visita: sincroniza prospectos y calendario */}
        <div className="mt-6 border-t border-slate-600 pt-4">
          <button
            type="button"
            onClick={() => setShowVisit((v) => !v)}
            className="text-sm font-semibold text-blue-400 transition hover:text-blue-300"
          >
            {showVisit ? '▾' : '▸'} Resultado de la visita (prospectos / calendario)
          </button>
          {showVisit && (
            <div className="mt-3 space-y-3 rounded-lg bg-slate-700/60 p-4">
              <div className="relative">
                <label className="mb-1 block text-xs font-semibold text-slate-300">
                  Vincular prospecto (opcional — si no eliges uno, se usa el nombre/teléfono del cliente o se crea uno nuevo)
                </label>
                {prospectPick ? (
                  <div className="flex items-center justify-between rounded-lg border border-blue-500 bg-slate-800 px-4 py-2">
                    <span className="text-sm text-white">
                      {prospectPick.full_name}
                      {prospectPick.phone ? ` · ${prospectPick.phone}` : ''}
                    </span>
                    <button
                      type="button"
                      onClick={clearProspectPick}
                      className="text-xs font-semibold text-red-400 hover:text-red-300"
                    >
                      Quitar
                    </button>
                  </div>
                ) : (
                  <>
                    <input
                      type="text"
                      value={prospectQuery}
                      onChange={(e) => {
                        setProspectQuery(e.target.value)
                        if (prospectPick) setProspectPick(null)
                      }}
                      className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
                      placeholder="Buscar prospecto por nombre o teléfono…"
                    />
                    {prospectResults.length > 0 && (
                      <div className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded-lg border border-slate-600 bg-slate-800 shadow-lg">
                        {prospectResults.map((p) => (
                          <button
                            key={p.id}
                            type="button"
                            onClick={() => pickProspect(p)}
                            className="block w-full px-4 py-2 text-left text-sm text-slate-200 hover:bg-slate-700"
                          >
                            {p.full_name}
                            {p.phone ? ` · ${p.phone}` : ''}
                          </button>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-300">Nota de la visita (opcional)</label>
                <input
                  type="text"
                  value={visitNote}
                  onChange={(e) => setVisitNote(e.target.value)}
                  maxLength={500}
                  className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
                  placeholder="Ej: le gustó el modelo, vuelve el próximo mes…"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-300">
                  Reagendar para (fecha y hora)
                </label>
                <input
                  type="datetime-local"
                  value={rescheduleAt}
                  onChange={(e) => setRescheduleAt(e.target.value)}
                  className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
                />
              </div>

              <div className="flex flex-wrap gap-3 pt-1">
                <button
                  type="button"
                  onClick={() => registerVisit('compra')}
                  disabled={!!visitBusy}
                  className="flex-1 rounded-lg bg-green-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-green-700 disabled:opacity-50"
                >
                  {visitBusy === 'compra' ? 'Registrando…' : '✓ Cliente compró'}
                </button>
                <button
                  type="button"
                  onClick={() => registerVisit('reagendado')}
                  disabled={!!visitBusy}
                  className="flex-1 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:opacity-50"
                >
                  {visitBusy === 'reagendado' ? 'Registrando…' : 'Reagendar visita'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
"""
src = src[:-len(old_tail)] + ui
open(path, 'w', encoding='utf-8', newline='\n').write(src)
print('part2 OK')
PYEOF
node --check src/pages/Calculator.jsx 2>/dev/null || npx esbuild src/pages/Calculator.jsx --loader:.jsx=jsx --outfile=/dev/null && echo JSX-OK
EOF
cd "/c/Users/eduran/OneDrive - Farmatrix/Documentos/inventory-master-main/frontend" && python _patch_calc.py && rm _patch_calc.py && echo DONE
python - <<'PYEOF'
# -*- coding: utf-8 -*-
path = 'src/pages/Calculator.jsx'
src = open(path, encoding='utf-8').read()

# 4) handlers antes del return
anchor = "  return (\n    <div className=\"max-w-4xl mx-auto space-y-6\">"
assert src.count(anchor) == 1
handlers = '''  // Búsqueda de prospectos con debounce (nombre o teléfono)
  useEffect(() => {
    const q = prospectQuery.trim()
    if (q.length < 2) {
      setProspectResults([])
      return
    }
    const t = setTimeout(async () => {
      try {
        setProspectResults(await visitSearch(q))
      } catch {
        setProspectResults([])
      }
    }, 350)
    return () => clearTimeout(t)
  }, [prospectQuery, visitSearch])

  function pickProspect(p) {
    setProspectPick(p)
    setProspectQuery(p.full_name)
    setProspectResults([])
    if (p.phone && !clientPhone) setClientPhone(p.phone)
    if (!clientName) setClientName(p.full_name)
  }

  function clearProspectPick() {
    setProspectPick(null)
    setProspectQuery('')
    setProspectResults([])
  }

  async function registerVisit(result) {
    if (result === 'reagendado' && !rescheduleAt) {
      return toast.error('Indica la fecha y hora para reagendar')
    }
    setVisitBusy(result)
    try {
      const res = await visitRegister({
        prospect_id: prospectPick ? prospectPick.id : null,
        client_name: clientName || null,
        client_phone: clientPhone || null,
        result,
        reschedule_at: result === 'reagendado' ? new Date(rescheduleAt).toISOString() : null,
        note: visitNote || null,
        quote_total: totalPrice || null,
      })
      toast.success(
        result === 'compra'
          ? `Compra registrada: ${res.prospect_name} marcado como cliente`
          : `Visita reagendada: nueva cita en el calendario`
      )
      setProspectPick(null)
      setProspectQuery('')
      setProspectResults([])
      setVisitNote('')
      setRescheduleAt('')
      setShowVisit(false)
    } catch (err) {
      toast.error(err?.message || 'No se pudo registrar la visita')
    } finally {
      setVisitBusy('')
    }
  }

'''
src = src.replace(anchor, handlers + anchor, 1)

# 5) UI: antes del cierre del contenedor principal
old_tail = """          <button
            onClick={clearAll}
            className="flex-1 rounded-lg bg-red-600 px-4 py-3 font-semibold text-white transition hover:bg-red-700"
          >
            Limpiar Todo
          </button>
        </div>
      </div>
    </div>
  )
}
"""
assert src.endswith(old_tail), 'tail no coincide'
ui = """          <button
            onClick={clearAll}
            className="flex-1 rounded-lg bg-red-600 px-4 py-3 font-semibold text-white transition hover:bg-red-700"
          >
            Limpiar Todo
          </button>
        </div>

        {/* Resultado de la visita: sincroniza prospectos y calendario */}
        <div className="mt-6 border-t border-slate-600 pt-4">
          <button
            type="button"
            onClick={() => setShowVisit((v) => !v)}
            className="text-sm font-semibold text-blue-400 transition hover:text-blue-300"
          >
            {showVisit ? '▾' : '▸'} Resultado de la visita (prospectos / calendario)
          </button>
          {showVisit && (
            <div className="mt-3 space-y-3 rounded-lg bg-slate-700/60 p-4">
              <div className="relative">
                <label className="mb-1 block text-xs font-semibold text-slate-300">
                  Vincular prospecto (opcional — si no eliges uno, se usa el nombre/teléfono del cliente o se crea uno nuevo)
                </label>
                {prospectPick ? (
                  <div className="flex items-center justify-between rounded-lg border border-blue-500 bg-slate-800 px-4 py-2">
                    <span className="text-sm text-white">
                      {prospectPick.full_name}
                      {prospectPick.phone ? ` · ${prospectPick.phone}` : ''}
                    </span>
                    <button
                      type="button"
                      onClick={clearProspectPick}
                      className="text-xs font-semibold text-red-400 hover:text-red-300"
                    >
                      Quitar
                    </button>
                  </div>
                ) : (
                  <>
                    <input
                      type="text"
                      value={prospectQuery}
                      onChange={(e) => {
                        setProspectQuery(e.target.value)
                        if (prospectPick) setProspectPick(null)
                      }}
                      className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
                      placeholder="Buscar prospecto por nombre o teléfono…"
                    />
                    {prospectResults.length > 0 && (
                      <div className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded-lg border border-slate-600 bg-slate-800 shadow-lg">
                        {prospectResults.map((p) => (
                          <button
                            key={p.id}
                            type="button"
                            onClick={() => pickProspect(p)}
                            className="block w-full px-4 py-2 text-left text-sm text-slate-200 hover:bg-slate-700"
                          >
                            {p.full_name}
                            {p.phone ? ` · ${p.phone}` : ''}
                          </button>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-300">Nota de la visita (opcional)</label>
                <input
                  type="text"
                  value={visitNote}
                  onChange={(e) => setVisitNote(e.target.value)}
                  maxLength={500}
                  className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
                  placeholder="Ej: le gustó el modelo, vuelve el próximo mes…"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-300">
                  Reagendar para (fecha y hora)
                </label>
                <input
                  type="datetime-local"
                  value={rescheduleAt}
                  onChange={(e) => setRescheduleAt(e.target.value)}
                  className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
                />
              </div>

              <div className="flex flex-wrap gap-3 pt-1">
                <button
                  type="button"
                  onClick={() => registerVisit('compra')}
                  disabled={!!visitBusy}
                  className="flex-1 rounded-lg bg-green-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-green-700 disabled:opacity-50"
                >
                  {visitBusy === 'compra' ? 'Registrando…' : '✓ Cliente compró'}
                </button>
                <button
                  type="button"
                  onClick={() => registerVisit('reagendado')}
                  disabled={!!visitBusy}
                  className="flex-1 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:opacity-50"
                >
                  {visitBusy === 'reagendado' ? 'Registrando…' : 'Reagendar visita'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
"""
src = src[:-len(old_tail)] + ui
open(path, 'w', encoding='utf-8', newline='\n').write(src)
print('part2 OK')
PYEOF
node --check src/pages/Calculator.jsx 2>/dev/null || npx esbuild src/pages/Calculator.jsx --loader:.jsx=jsx --outfile=/dev/null && echo JSX-OK