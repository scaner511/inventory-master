import { useState, useEffect, useMemo } from 'react'
import toast from 'react-hot-toast'
import { getCalculatorProducts } from '../api/index.js'

// Array de productos (los mismos de master-calculadora)
const products = [
  // Aros
  { code: 'SP0420', name: 'Aro 16 cm. y ventana', price: 1700 },
  { code: 'SP0430', name: 'Aro 20 cm. y ventana', price: 1800 },
  { code: 'SP0440', name: 'Aro 26 cm. y ventana', price: 2200 },
  { code: 'SP0450', name: 'Aro 30 cm. y ventana', price: 2400 },
  { code: 'SP0460', name: 'Aro 35 cm. y ventana', price: 2800 },
  { code: 'SP0470', name: 'Aro 38 cm. y ventana', price: 3000 },
  { code: 'SP0488', name: 'Aros para tapas Altas', price: 2000 },
  { code: 'ARO5', name: 'Aros Juego 5 pzs comp.', price: 4000 },
  { code: 'ARO7', name: 'Aros Juego 7 pzs clásico', price: 5700 },
  { code: 'ARO8', name: 'Aros Juego 8 pzs especial', price: 8500 },
  { code: 'ARO10', name: 'Aros Juego 10 pzs familiar', price: 7700 },
  
  // Juegos de Ollas
  { code: 'CO9245', name: 'Sistema de Cocina Complem. de 5 Pzs', price: 111000 },
  { code: 'CO9247', name: 'Sistema de Cocina Complem. de 5 Pzs + Perfect Pop', price: 119200 },
  { code: 'CO9253', name: 'Sistema de Cocina Clásico de 7 Pzs', price: 137500 },
  { code: 'CO9254', name: 'Sistema de Cocina Especial de 8 Pzs', price: 168500 },
  { code: 'CO9261', name: 'Sistema de Cocina Familiar de 10 Pzs + Perfect Pop', price: 215000 },
  
  // Juegos + Tapa Adicional
  { code: 'CO9245-TG', name: 'Sist. de Cocina Complementario de 5 Pzs + Tapa Grand. 26cm', price: 125500 },
  { code: 'CO9253-TM', name: 'Sist. de Cocina Clásico de 7 Pzs + Tapa Med. 20 Cm', price: 150000 },
  { code: 'CO9261-TM', name: 'Sist. de Cocina Familiar de 10 Pzs + Perfect Pop + Tapa Med. 20 Cm', price: 227500 },
  
  // Ollas de Sancocho
  { code: 'CO9224', name: 'Olla de 12 Qt. c/tapa Sancocho Peq.', price: 53000 },
  { code: 'CO9226', name: 'Olla de 20 Qt. c/tapa Sancocho Med.', price: 65000 },
  { code: 'CO9228', name: 'Olla 30 QT/38 cm c/tapa Sancocho Grand.', price: 80000 },
  
  // Piezas Individuales (Ollas y Sartenes)
  { code: 'CO9201', name: 'Olla de 2 Qt.', price: 20000 },
  { code: 'CO9201-T', name: 'Olla de 2 Qt. Con Tapa', price: 31500 },
  { code: 'CO9203', name: 'Olla de 3 Qt.', price: 26500 },
  { code: 'CO9203-T', name: 'Olla de 3 Qt. Con Tapa', price: 39000 },
  { code: 'CO9205', name: 'Olla de 4 Qt.', price: 26700 },
  { code: 'CO9236', name: 'Olla de 4 Qt. Con Tapa', price: 39800 },
  { code: 'CO9207', name: 'Olla de 6 Qt.', price: 32500 },
  { code: 'CO9207-T', name: 'Olla de 6 Qt. con Tapa', price: 47000 },
  { code: 'CO9209', name: 'Olla de 8 Qt.', price: 35000 },
  { code: 'CO9237', name: 'Olla de 8 Qt. Con Tapa', price: 48000 },
  { code: 'CO9211', name: 'Sartén de 8"', price: 26500 },
  { code: 'CO9211-T', name: 'Sartén de 8" Con Tapa', price: 39000 },
  { code: 'CO9213', name: 'Sartén de 10.5" / 4QT / 26cm', price: 33500 },
  { code: 'CO9213-T', name: 'Sartén de 10.5" / 4QT / 26cm Con Tapa', price: 48000 },
  { code: 'CO9217', name: 'Paellera de 10" con tapa', price: 35500 },
  { code: 'CO9215', name: 'Paellera de 14" con tapa', price: 58000 },
  
  // Tapas y Accesorios
  { code: 'CO9076', name: 'Colador Pequeño de 20 cm.', price: 14800 },
  { code: 'CO9080', name: 'Colador Grande de 26 cm.', price: 16800 },
  { code: 'CO9085', name: 'Tapa Pequeña de 16 cm.', price: 11500 },
  { code: 'CO9086', name: 'Tapa Mediana de 20 cm.', price: 12500 },
  { code: 'CO9087', name: 'Tapa Grande de 26 cm.', price: 14500 },
  { code: 'CO9088', name: 'Tapa Alta de 26 cm.', price: 27000 },
  { code: 'CO6500', name: 'Tapa Pequeña de 16 cm 5 y 9 Capas (modelo anterior)', price: 5700 },
  { code: 'CO6505', name: 'Tapa Mediana de 20 cm 5 y 9 Capas (modelo anterior)', price: 6500 },
  { code: 'CO6510', name: 'Tapa Grande de 26 cm 5 y 9 Capas (modelo anterior)', price: 8500 },
  { code: 'CO6516', name: 'Tapa Alta - 26 cm C/Base 5 y 9 Capas (modelo anterior)', price: 18500 },
  { code: 'PR0025', name: 'Perfect Pop (Palomitas)', price: 8000 },
  { code: 'PR1675', name: 'Hervidor de 1/2 Qt- 5 Capas Mango Negro', price: 8500 },
  { code: 'PR1685', name: 'Hervidor de 1 Qt- 5 Capas Mango Negro', price: 9500 },
  { code: 'SP0145', name: 'Recipiente / Organizador para Utensilios', price: 2500 },
  { code: 'PR0196', name: 'Utensilios de Cocina de 6 pzs', price: 10700 },
  { code: 'SP0135', name: 'Juego de 4 Tazas Con Pared de Doble', price: 6500 },
  { code: 'SP0136', name: 'Juego de 2 Tazas 16 oz. con Pared Doble', price: 5000 },
  { code: 'CO6589', name: 'Pavera Ovalada', price: 55000 },
  { code: 'PR2614', name: 'Máquina para Ensaladas', price: 54000 },
  { code: 'LT1199', name: 'Recetario', price: 1000 },
  { code: 'CO2124', name: 'Cacerola para Huevos', price: 14000 },
  { code: 'SP0305', name: 'Base Magneticas para Ollas', price: 3000 },
  { code: 'SP5050', name: 'Limpiador', price: 1000 },
  
  // Café / Té / Chocolate
  { code: 'CO2106', name: 'Cafetera Barista', price: 42000 },
  { code: 'PR2134', name: 'Kit Completo Baristart', price: 5300 },
  { code: 'CO0801', name: 'Expertea', price: 38500 },
  { code: 'PR2129', name: 'Cafetera (Greca) Espresso 10 Tazas Doble Pared', price: 17000 },
  { code: 'PR2120', name: 'Cafetera (Greca) Espresso 4 Tazas', price: 14000 },
  { code: 'CO0101', name: 'Chocolatera', price: 26000 },
  
  // Electrodomésticos
  { code: 'ES0003', name: 'Power Blender C/ Recetario 120-127v - Licuadora', price: 110000 },
  { code: 'LT2209', name: 'Recetario Nuevo Power Blender - Licuadora', price: 1000 },
  { code: 'ES3101', name: 'Precision Cook Estufa Inducción', price: 67000 },
  { code: 'JU0026', name: 'Extractor de Jugos C/Recetario', price: 115000 },
  { code: 'PR1460', name: '3 Coladores Extractor Jugo', price: 18500 },
  { code: 'PR1459', name: 'Exprimidor de (Cítricos) Jugo', price: 9000 },
  { code: 'JU0026-COMP', name: 'Extractor de Jugos Completo', price: 135000 },
  { code: 'PR1452', name: '3 Coladores para el Maxtractor (modelo anterior)', price: 17500 },
  { code: 'LT2258', name: 'Recetario Extractor de Jugos', price: 1000 },
  
  // Recipientes / Tazones
  { code: 'SP0252', name: 'Jgo. de 2 Copas P/Helados C/Pared Doble', price: 4500 },
  { code: 'SP0066', name: 'Tazón Mezclar De 10 QT C/Tapa Con Base Silicona', price: 8000 },
  { code: 'SP0062', name: 'Tazón De 5 QT C/Tapa Doble Pared', price: 6000 },
  { code: 'PR1044', name: 'Jgo 4 Tazones P/Mezclar C/Tapas 1, 2, 3 y 5 QT Base Silic', price: 14500 },
  { code: 'SP0262', name: 'Jgo 2 Tazónes P/Mezclar con Silicona 2.5 &4 QT.', price: 7300 },
  { code: 'SP0111', name: '6 Recipientes C/Capacidad de 2 Tzs - 500ml', price: 2900 },
  { code: 'SP0111-1', name: '1 Recipiente C/Capacidad de 2 Tzs - 500ml', price: 800 },
  { code: 'SP0113', name: 'Jgo 8 Pzs Recip. de Comida 4, 8,32,48 OZ', price: 4000 },
  
  // Planchas
  { code: 'CO9218', name: 'Plancha Doble Acero', price: 28000 },
  { code: 'CO9219', name: 'Plancha Redonda', price: 26000 },
  { code: 'CO9220', name: 'Plancha Cuadrada sencilla', price: 22500 },
  
  // Cubertería
  { code: 'SP0081', name: 'Jgo. P/Servir de 3 Pzs Deluxe', price: 2300 },
  { code: 'SP0091', name: 'Jgo. P/Servir de 3 Pzs Complementario', price: 2300 },
  { code: 'SP0009', name: 'Jgo. de Cubiertos 24 Pzs Americana 18/8', price: 9000 },
  
  // Sartenes Gourmet
  { code: 'CO9230', name: 'Sarten Gourmet 8"/20CM C/Tapa', price: 24000 },
  { code: 'CO9232', name: 'Sarten Gourmet 10"/25CM C/Tapa', price: 29000 },
  { code: 'CO9234', name: 'Sartén Gourmet 12"/30CM C/Tapa', price: 41000 },
  { code: 'CO9265', name: 'Juego de Sartenes Gourmet de 6 pzs', price: 91000 },
  { code: 'CO9222', name: 'Wok con Tapa', price: 41000 },
  
  // Easy Release / Vidrio
  { code: 'CO9732', name: 'Easy Release 8" Peq C/ Tapa Vidrio + 3PZ Utensilios', price: 38500 },
  { code: 'CO9733', name: 'Easy Release 10" Med C/ Tapa Vidrio + 3PZ Utensilios', price: 47000 },
  { code: 'CO9734', name: 'Easy Release 12" Grad. C/ Tapa Vidrio + 3PZ Utensilios', price: 58500 },
  { code: 'CO9726', name: 'Juego Easy Release 6 Pzs C/ Tapa Vidrio + 3PZ Utensilios', price: 129500 },
  { code: 'CO9777', name: 'Olla 2 Qt /18Cm Easy Release C/ Tapa Vidrio + 3PZ Utensilios', price: 38000 },
  { code: 'CO9778', name: 'Olla 3 Qt /20Cm Easy Release C/ Tapa Vidrio + 3PZ Utensilios', price: 41000 },
  { code: 'CO9779', name: 'Olla 3.5 Qt 10.5" /26Cm Easy Release C/Tapa Vidrio + 3PZ Utensilios', price: 48000 },
  { code: 'CO9779-SET', name: 'Jgo. Ollas Easy Release 6PZ C/Tapa Vidrio + 3PZ Utensilios', price: 127000 },
  { code: 'SP0018', name: 'Jgo Utensilios 3PZ Easy Release', price: 6000 },
  
  // Easy Release / Acero
  { code: 'CO9718', name: 'Juego Easy Release 6 Pzs Tapa Acero + Jgo Utensilios 3 Pzs', price: 115000 },
  { code: 'CO9714', name: 'Easy Release 12" Grad. C/ Tapa Acero + 3PZ Utensilios', price: 58500 },
  
  // Ollas de Presión
  { code: 'CO1251', name: 'Nueva Olla Presión de 6 Litros', price: 53500 },
  { code: 'CO1255', name: 'Nueva Olla de Presión de 10 Litros', price: 63000 },
  
  // Cuchillería
  { code: 'CU0800', name: 'Precisión Básico 5 pzs', price: 23000 },
  { code: 'CU0815', name: 'Precisión para Rebanar 4 pzs (Parrillero)', price: 18000 },
  { code: 'CU0820', name: 'Precisión para Carne 4 pzs (Comensal)', price: 12000 },
  { code: 'CU0056', name: 'Bloque de Cuchillos 17 Hoyos (Sólo bloque)', price: 16500 },
  { code: 'CU0810', name: 'Cuchillo p/ Pelar 2.75"', price: 6000 },
  { code: 'CU0814', name: 'Cuchillo Multiuso 5"', price: 6700 },
  { code: 'CU0831', name: 'Juego completo Precisión', price: 82000 },
  { code: 'CU0825', name: 'Hacha de Cocina 7"', price: 8000 },
  { code: 'SP0296', name: 'Cuchillo Santoku de 5"', price: 3700 },
  { code: 'SP0297', name: 'Cuchillo Santoku de 3.5"', price: 2500 },
  
  // Accesorios de Cocina
  { code: 'PR0008', name: 'Tabla Grande P/Cortar de Bambú Silicona - Rojo', price: 8200 },
  { code: 'PR0021', name: 'Tabla Pequeña P/Cortar de Bambú Silicona -Verde', price: 6500 },
  { code: 'SP1850', name: 'Destapador', price: 2500 },
  { code: 'SP1851', name: 'Rallador', price: 2700 },
  { code: 'SP1852', name: 'Espátula', price: 3300 },
  { code: 'SP1853', name: 'Batidor de Globo', price: 3300 },
  { code: 'SP1854', name: 'Pelador', price: 2700 },
  { code: 'SP1856', name: 'Cortador de Pizza', price: 3300 },
  { code: 'SP1857', name: 'Machacador redondo con Hoyos', price: 3300 },
  { code: 'SP1861', name: 'Jgo. De 2 Espátulas de Silicona', price: 4500 },
  
  // Filtros de Ducha
  { code: 'PR0003', name: 'Filtro de Ducha', price: 25000 },
  { code: 'WF0080', name: 'SEIS (6) CARTUCHOS- FILTRO P/ DUCHA', price: 24000 },
  { code: 'WF0075', name: 'DOS (2) CARTUCHOS- FILTRO P/ DUCHA', price: 9000 },
  { code: 'WF0075-COV', name: 'Kit Reemplazo Cubierta de Ducha', price: 6700 },
  
  // Purificadores de Aire
  { code: 'AP2101', name: 'Purificador de Aire C/Cable', price: 90000 },
  { code: 'AP2004', name: 'Cartuchos de Reemplazo', price: 21000 },
  
  // Piezas de Reemplazo
  { code: 'RP4800', name: 'Agarradera Mediana Para Tapa', price: 1500 },
  { code: 'RP4801', name: 'Agarradera Grande Para Tapa', price: 1600 },
  { code: 'RP4802', name: 'Válvula', price: 1000 },
  { code: 'RP4810', name: 'Asa Lateral Desmontable', price: 1000 },
  { code: 'RP4811', name: 'Asa Larga Desmontable', price: 2800 }
]

// Formatear moneda
function formatCurrency(amount) {
  if (typeof amount !== 'number') amount = parseFloat(amount) || 0
  const formatted = amount.toLocaleString('es-DO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return 'RD$ ' + formatted.toString()
}

export default function Calculator({ storageKey = 'masterCalculadora', extraProducts }) {
  // Productos personalizados del cliente (los define el Super Admin). Si la
  // página pública ya los trae en `extraProducts` no se vuelven a pedir.
  const [customProducts, setCustomProducts] = useState(extraProducts || [])
  const [selectedProducts, setSelectedProducts] = useState({})
  const [searchTerm, setSearchTerm] = useState('')
  const [clientName, setClientName] = useState('')
  const [clientPhone, setClientPhone] = useState('')
  const [initialPayment, setInitialPayment] = useState('')
  const [interestRate, setInterestRate] = useState('18')
  const [term, setTerm] = useState('12')
  const [paymentType, setPaymentType] = useState('amount')
  const [termType, setTermType] = useState('months')
  const [paymentFrequency, setPaymentFrequency] = useState('monthly')
  const [discount, setDiscount] = useState('')
  const [discountType, setDiscountType] = useState('amount')
  const [discountEnabled, setDiscountEnabled] = useState(false)
  // Precios personalizados por código de producto. Si no hay valor, se usa el precio de lista.
  const [customPrices, setCustomPrices] = useState({})
  const [hydrated, setHydrated] = useState(false)

  // Cargar productos personalizados: del prop (página pública) o del API (panel).
  useEffect(() => {
    if (extraProducts !== undefined) {
      setCustomProducts(extraProducts || [])
      return
    }
    let cancelled = false
    getCalculatorProducts()
      .then((data) => { if (!cancelled) setCustomProducts(Array.isArray(data) ? data : []) })
      .catch(() => { /* sin sesión (público) o función apagada: solo lista base */ })
    return () => { cancelled = true }
  }, [extraProducts])

  // Catálogo completo: productos base + personalizados del cliente.
  const allProducts = useMemo(
    () => [...products, ...customProducts],
    [customProducts]
  )

  // Cargar desde localStorage (clave distinta por enlace/cliente)
  useEffect(() => {
    const saved = localStorage.getItem(storageKey)
    if (saved) {
      const data = JSON.parse(saved)
      setSelectedProducts(data.selectedProducts || {})
      setClientName(data.clientName || '')
      setClientPhone(data.clientPhone || '')
      setInitialPayment(data.initialPayment || '')
      setInterestRate(data.interestRate || '18')
      setTerm(data.term || '12')
      setPaymentType(data.paymentType || 'amount')
      setTermType(data.termType || 'months')
      setPaymentFrequency(data.paymentFrequency || 'monthly')
      setDiscount(data.discount || '')
      setDiscountType(data.discountType || 'amount')
      setDiscountEnabled(
        data.discountEnabled ?? (parseFloat(data.discount || 0) > 0)
      )
      setCustomPrices(data.customPrices || {})
    }
    setHydrated(true)
  }, [storageKey])

  // Guardar en localStorage
  useEffect(() => {
    const data = {
      selectedProducts,
      clientName,
      clientPhone,
      initialPayment,
      interestRate,
      term,
      paymentType,
      termType,
      paymentFrequency,
      discount,
      discountType,
      discountEnabled,
      customPrices
    }
    localStorage.setItem(storageKey, JSON.stringify(data))
  }, [storageKey, selectedProducts, clientName, clientPhone, initialPayment, interestRate, term, paymentType, termType, paymentFrequency, discount, discountType, discountEnabled, customPrices])

  // Descartar precios personalizados de productos que ya no están seleccionados.
  useEffect(() => {
    if (!hydrated) return
    setCustomPrices(prev => {
      const next = Object.fromEntries(
        Object.entries(prev).filter(([code]) => (selectedProducts[code] || 0) > 0)
      )
      return Object.keys(next).length === Object.keys(prev).length ? prev : next
    })
  }, [selectedProducts, hydrated])

  // Filtrar productos
  const filteredProducts = allProducts.filter(p =>
    p.code.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.name.toLowerCase().includes(searchTerm.toLowerCase())
  )

  // Precio unitario efectivo: precio personalizado o precio de lista.
  function unitPrice(code) {
    const product = allProducts.find(p => p.code === code)
    const custom = customPrices[code]
    if (custom !== undefined && custom !== null && String(custom).trim() !== '') {
      const value = parseFloat(custom)
      if (Number.isFinite(value) && value >= 0) return value
    }
    return product ? product.price : 0
  }

  // Actualizar cantidad
  function updateQuantity(code, change) {
    setSelectedProducts(prev => {
      const newQty = Math.max(0, (prev[code] || 0) + change)
      if (newQty === 0) {
        const { [code]: _, ...rest } = prev
        return rest
      }
      return { ...prev, [code]: newQty }
    })
  }

  // Quitar un producto seleccionado por completo.
  function removeProduct(code) {
    setSelectedProducts(prev => {
      const { [code]: _, ...rest } = prev
      return rest
    })
    setCustomPrices(prev => {
      const { [code]: _, ...rest } = prev
      return rest
    })
  }

  // Modificar el precio unitario de un producto seleccionado.
  function updateProductPrice(code, value) {
    setCustomPrices(prev => ({ ...prev, [code]: value }))
  }

  // Al salir del campo, normalizar el precio (vacío o inválido vuelve al de lista).
  function normalizeProductPrice(code) {
    const raw = customPrices[code]
    if (raw === undefined) return
    if (String(raw).trim() === '' || !Number.isFinite(parseFloat(raw))) {
      setCustomPrices(prev => {
        const { [code]: _, ...rest } = prev
        return rest
      })
      return
    }
    const value = Math.max(0, parseFloat(raw))
    setCustomPrices(prev => ({ ...prev, [code]: String(value) }))
  }

  // Restaurar el precio de lista del producto.
  function resetProductPrice(code) {
    setCustomPrices(prev => {
      const { [code]: _, ...rest } = prev
      return rest
    })
  }

  // Calcular totales
  const totalProducts = Object.entries(selectedProducts).reduce((sum, [code, qty]) => {
    return sum + (unitPrice(code) * qty)
  }, 0)

  const purchasePrice = totalProducts / 1.18
  const itbis = purchasePrice * 0.18
  const totalPrice = totalProducts

  // Descuento (solo se aplica si la casilla está marcada)
  let discountAmount = 0
  if (discountEnabled) {
    if (discountType === 'percentage') {
      discountAmount = (totalPrice * parseFloat(discount || 0)) / 100
    } else {
      discountAmount = parseFloat(discount) || 0
    }
  }
  const priceAfterDiscount = Math.max(0, totalPrice - discountAmount)

  // Pago inicial
  let initialPaymentAmount = parseFloat(initialPayment) || 0
  if (paymentType === 'percentage') {
    initialPaymentAmount = (priceAfterDiscount * initialPaymentAmount) / 100
  }

  const depositDelivered = initialPaymentAmount
  const balanceToFinance = Math.max(0, priceAfterDiscount - depositDelivered)

  // Tasa y plazo
  const annualRate = parseFloat(interestRate) || 0
  let termMonths = parseFloat(term) || 0
  if (termType === 'years') {
    termMonths = termMonths * 12
  }

  // Frecuencia
  let periodsPerYear = 12
  let frequencyName = 'Mensual'
  if (paymentFrequency === 'weekly') {
    periodsPerYear = 52
    frequencyName = 'Semanal'
  } else if (paymentFrequency === 'biweekly') {
    periodsPerYear = 24
    frequencyName = 'Quincenal'
  }

  const numPayments = termMonths * (periodsPerYear / 12)
  const periodRate = annualRate / periodsPerYear / 100

  // Calcular cuota (PMT)
  let monthlyPayment = 0
  if (balanceToFinance > 0 && periodRate > 0 && numPayments > 0) {
    monthlyPayment = (balanceToFinance * periodRate) / (1 - Math.pow(1 + periodRate, -numPayments))
  } else if (balanceToFinance > 0 && numPayments > 0) {
    monthlyPayment = balanceToFinance / numPayments
  }

  // Calcular cuotas en 12, 24 y 36 meses
  const monthlyRate = annualRate / 12 / 100
  
  function calculateInstallment(months) {
    if (balanceToFinance <= 0 || months <= 0) return 0
    if (monthlyRate > 0) {
      return (balanceToFinance * monthlyRate) / (1 - Math.pow(1 + monthlyRate, -months))
    }
    return balanceToFinance / months
  }

  const installment12 = calculateInstallment(12)
  const installment24 = calculateInstallment(24)
  const installment36 = calculateInstallment(36)

  // Compartir por WhatsApp
  function shareWhatsApp() {
    const name = clientName || 'Cliente'
    
    let message = `*Cotización Master Calculadora*\n\n`
    message += `Cliente: ${name}\n\n`
    message += `*Productos:*\n`
    
    Object.entries(selectedProducts).forEach(([code, qty]) => {
      if (qty > 0) {
        const product = allProducts.find(p => p.code === code)
        const subtotal = unitPrice(code) * qty
        message += `• ${product.name} (${qty}x ${formatCurrency(unitPrice(code))}): ${formatCurrency(subtotal)}\n`
      }
    })
    
    message += `\n*Resumen:*\n`
    message += `Precio Total: ${formatCurrency(totalPrice)}\n`
    if (discountEnabled) {
      message += `Descuento: ${formatCurrency(discountAmount)}\n`
      message += `Precio con Descuento: ${formatCurrency(priceAfterDiscount)}\n`
    }
    message += `Depósito: ${formatCurrency(depositDelivered)}\n`
    message += `Saldo a Financiar: ${formatCurrency(balanceToFinance)}\n`
    message += `Cuotas: ${Math.round(numPayments)}\n`
    message += `Pago por cuota: ${formatCurrency(monthlyPayment)}`

    const encodedMessage = encodeURIComponent(message)
    // Si hay teléfono del cliente, el mensaje va directo a su chat de WhatsApp.
    // Formato wa.me: solo dígitos con código de país (10 dígitos 8xx → +1).
    let digits = (clientPhone || '').replace(/\D/g, '')
    if (digits.length === 10 && digits.startsWith('8')) digits = `1${digits}`
    const url = digits
      ? `https://wa.me/${digits}?text=${encodedMessage}`
      : `https://wa.me/?text=${encodedMessage}`
    window.open(url, '_blank')
  }

  // Limpiar todo
  function clearAll() {
    if (window.confirm('¿Está seguro de que desea limpiar todos los datos?')) {
      setSelectedProducts({})
      setClientName('')
      setClientPhone('')
      setInitialPayment('')
      setInterestRate('18')
      setTerm('12')
      setPaymentType('amount')
      setTermType('months')
      setPaymentFrequency('monthly')
      setDiscount('')
      setDiscountType('amount')
      setDiscountEnabled(false)
      setCustomPrices({})
      toast.success('Datos limpiados')
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="rounded-xl bg-slate-800 p-6 shadow-lg">
        <h1 className="mb-6 text-2xl font-bold text-white">Master Calculadora</h1>
        
        {/* Datos del Cliente */}
        <div className="mb-6 grid gap-4 md:grid-cols-2">
          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-300">Nombre (Opcional)</label>
            <input
              type="text"
              value={clientName}
              onChange={(e) => setClientName(e.target.value)}
              className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
              placeholder="Nombre del cliente"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-300">Teléfono para WhatsApp (opcional)</label>
            <input
              type="tel"
              value={clientPhone}
              onChange={(e) => setClientPhone(e.target.value)}
              className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
              placeholder="Teléfono"
            />
          </div>
        </div>

        {/* Selección de Productos */}
        <div className="mb-6">
          <h2 className="mb-4 text-lg font-semibold text-white">Seleccionar Productos</h2>
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="mb-4 w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
            placeholder="Buscar por código o nombre..."
          />
          
          <div className="max-h-96 overflow-y-auto rounded-lg border border-slate-600 bg-slate-700">
            {filteredProducts.length === 0 ? (
              <div className="p-8 text-center text-slate-400">
                <div className="mb-2 text-4xl">🔍</div>
                <p>No se encontraron productos</p>
              </div>
            ) : (
              filteredProducts.map(product => {
                const qty = selectedProducts[product.code] || 0
                return (
                  <div key={product.code} className="flex items-center justify-between border-b border-slate-600 p-4 last:border-0">
                    <div className="flex-1">
                      <div className="font-semibold text-blue-400">{product.code}</div>
                      <div className="text-slate-200">{product.name}</div>
                      <div className="font-bold text-white">
                        {formatCurrency(unitPrice(product.code))}
                        {customPrices[product.code] !== undefined && (
                          <span className="ml-2 text-xs font-normal text-amber-400">precio modificado</span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => updateQuantity(product.code, -1)}
                        className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-lg font-bold text-white transition hover:bg-blue-700"
                      >
                        -
                      </button>
                      <span className="w-10 text-center font-semibold text-white">{qty}</span>
                      <button
                        onClick={() => updateQuantity(product.code, 1)}
                        className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-lg font-bold text-white transition hover:bg-blue-700"
                      >
                        +
                      </button>
                    </div>
                  </div>
                )
              })
            )}
          </div>

          {/* Productos Seleccionados */}
          {Object.keys(selectedProducts).length > 0 && (
            <div className="mt-4 rounded-lg bg-slate-600 p-4">
              <div className="mb-3">
                <h3 className="font-semibold text-white">Productos Seleccionados</h3>
                <p className="text-xs text-slate-400">
                  Puedes ajustar la cantidad, cambiar el precio o quitar el producto aquí mismo.
                </p>
              </div>
              {Object.entries(selectedProducts).map(([code, qty]) => {
                if (qty === 0) return null
                const product = allProducts.find(p => p.code === code)
                const hasCustomPrice = customPrices[code] !== undefined
                const subtotal = unitPrice(code) * qty
                return (
                  <div key={code} className="mb-2 rounded bg-slate-700 p-3 last:mb-0">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0 flex-1">
                        <div className="font-semibold text-white">{product.name}</div>
                        <div className="text-xs text-slate-400">{product.code}</div>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => updateQuantity(code, -1)}
                            title="Reducir cantidad"
                            className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-lg font-bold text-white transition hover:bg-blue-700"
                          >
                            -
                          </button>
                          <span className="w-8 text-center font-semibold text-white">{qty}</span>
                          <button
                            type="button"
                            onClick={() => updateQuantity(code, 1)}
                            title="Aumentar cantidad"
                            className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-lg font-bold text-white transition hover:bg-blue-700"
                          >
                            +
                          </button>
                        </div>

                        <label className="flex items-center gap-1 text-xs text-slate-300">
                          <span>Precio</span>
                          <input
                            type="number"
                            value={customPrices[code] ?? String(product.price)}
                            onChange={(e) => updateProductPrice(code, e.target.value)}
                            onBlur={() => normalizeProductPrice(code)}
                            min="0"
                            step="0.01"
                            title="Precio unitario"
                            className="w-24 rounded-lg border border-slate-500 bg-slate-800 px-2 py-1 text-right text-white focus:border-blue-500 focus:outline-none"
                          />
                        </label>

                        {hasCustomPrice && (
                          <button
                            type="button"
                            onClick={() => resetProductPrice(code)}
                            title="Restaurar precio de lista"
                            className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-500 text-white transition hover:bg-slate-400"
                          >
                            ↺
                          </button>
                        )}

                        <button
                          type="button"
                          onClick={() => removeProduct(code)}
                          title="Quitar producto"
                          className="flex h-8 items-center justify-center rounded-lg bg-red-600 px-3 text-sm font-semibold text-white transition hover:bg-red-700"
                        >
                          Quitar
                        </button>
                      </div>
                    </div>

                    <div className="mt-2 flex items-center justify-between text-sm">
                      <span className="text-slate-300">
                        {qty} x {formatCurrency(unitPrice(code))}
                      </span>
                      <span className="font-bold text-blue-400">{formatCurrency(subtotal)}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Configuración de Pago */}
        <div className="mb-6">
          <h2 className="mb-4 text-lg font-semibold text-white">Configuración de Pago</h2>
          
          <div className="mb-4">
            <label className="mb-2 block text-sm font-semibold text-slate-300">Total Productos</label>
            <input
              type="text"
              value={formatCurrency(totalPrice)}
              readOnly
              className="w-full rounded-lg border border-slate-600 bg-slate-600 px-4 py-2 text-white"
            />
          </div>

          <div className="mb-4">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <span className="block text-sm font-semibold text-slate-300">Descuento</span>
              <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={discountEnabled}
                  onChange={(e) => setDiscountEnabled(e.target.checked)}
                  className="h-4 w-4 accent-blue-500"
                />
                Aplicar descuento
              </label>
            </div>
            <div className={discountEnabled ? '' : 'pointer-events-none opacity-40'}>
              <div className="mb-2 flex gap-4">
                <label className="flex items-center gap-2 cursor-pointer text-slate-300">
                  <input
                    type="radio"
                    name="discountType"
                    value="amount"
                    checked={discountType === 'amount'}
                    onChange={(e) => setDiscountType(e.target.value)}
                    disabled={!discountEnabled}
                    className="accent-blue-500"
                  />
                  Monto Fijo (RD$)
                </label>
                <label className="flex items-center gap-2 cursor-pointer text-slate-300">
                  <input
                    type="radio"
                    name="discountType"
                    value="percentage"
                    checked={discountType === 'percentage'}
                    onChange={(e) => setDiscountType(e.target.value)}
                    disabled={!discountEnabled}
                    className="accent-blue-500"
                  />
                  Porcentaje (%)
                </label>
              </div>
              <input
                type="number"
                value={discount}
                onChange={(e) => setDiscount(e.target.value)}
                disabled={!discountEnabled}
                className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-white focus:border-blue-500 focus:outline-none disabled:cursor-not-allowed"
                placeholder="0.00"
                min="0"
                step="0.01"
              />
            </div>
            {!discountEnabled && (
              <p className="mt-1 text-xs text-slate-400">
                Marca la casilla para aplicar un descuento.
              </p>
            )}
          </div>

          <div className="mb-4">
            <label className="mb-2 block text-sm font-semibold text-slate-300">Pago Inicial</label>
            <div className="mb-2 flex gap-4">
              <label className="flex items-center gap-2 cursor-pointer text-slate-300">
                <input
                  type="radio"
                  name="paymentType"
                  value="amount"
                  checked={paymentType === 'amount'}
                  onChange={(e) => setPaymentType(e.target.value)}
                  className="accent-blue-500"
                />
                Monto Fijo (RD$)
              </label>
              <label className="flex items-center gap-2 cursor-pointer text-slate-300">
                <input
                  type="radio"
                  name="paymentType"
                  value="percentage"
                  checked={paymentType === 'percentage'}
                  onChange={(e) => setPaymentType(e.target.value)}
                  className="accent-blue-500"
                />
                Porcentaje (%)
              </label>
            </div>
            <input
              type="number"
              value={initialPayment}
              onChange={(e) => setInitialPayment(e.target.value)}
              className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
              placeholder="0.00"
              min="0"
              step="0.01"
            />
            {initialPaymentAmount > priceAfterDiscount && priceAfterDiscount > 0 && (
              <p className="mt-1 text-sm text-red-400">El pago inicial no puede exceder el total con descuento</p>
            )}
          </div>

          <div className="mb-4 grid gap-4 md:grid-cols-2">
            <div>
              <label className="mb-2 block text-sm font-semibold text-slate-300">Tasa de Interés Anual (%)</label>
              <input
                type="number"
                value={interestRate}
                onChange={(e) => setInterestRate(e.target.value)}
                className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
                placeholder="Ej: 18"
                min="0"
                step="0.1"
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-semibold text-slate-300">Plazo</label>
              <div className="mb-2 flex gap-4">
                <label className="flex items-center gap-2 cursor-pointer text-slate-300">
                  <input
                    type="radio"
                    name="termType"
                    value="months"
                    checked={termType === 'months'}
                    onChange={(e) => setTermType(e.target.value)}
                    className="accent-blue-500"
                  />
                  Meses
                </label>
                <label className="flex items-center gap-2 cursor-pointer text-slate-300">
                  <input
                    type="radio"
                    name="termType"
                    value="years"
                    checked={termType === 'years'}
                    onChange={(e) => setTermType(e.target.value)}
                    className="accent-blue-500"
                  />
                  Años
                </label>
              </div>
              <input
                type="number"
                value={term}
                onChange={(e) => setTerm(e.target.value)}
                className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
                placeholder="Ej: 12"
                min="1"
                step="1"
              />
            </div>
          </div>

          <div className="mb-4">
            <label className="mb-2 block text-sm font-semibold text-slate-300">Frecuencia de Pago</label>
            <select
              value={paymentFrequency}
              onChange={(e) => setPaymentFrequency(e.target.value)}
              className="w-full rounded-lg border border-slate-600 bg-slate-700 px-4 py-2 text-white focus:border-blue-500 focus:outline-none"
            >
              <option value="monthly">Mensual</option>
              <option value="biweekly">Quincenal</option>
              <option value="weekly">Semanal</option>
            </select>
          </div>
        </div>

        {/* Tabla de Cuotas */}
        <div className="mb-6">
          <h2 className="mb-4 text-lg font-semibold text-white">Opciones de Financiamiento</h2>
          <div className="overflow-hidden rounded-lg border border-slate-600 bg-slate-700">
            <div className="flex items-center justify-between border-b border-slate-600 p-4 last:border-0">
              <div>
                <div className="font-semibold text-white">12 Meses</div>
                <div className="text-sm text-slate-400">12 cuotas mensuales</div>
              </div>
              <div className="text-xl font-bold text-blue-400">{formatCurrency(installment12)}</div>
            </div>
            <div className="flex items-center justify-between border-b border-slate-600 p-4 last:border-0">
              <div>
                <div className="font-semibold text-white">24 Meses</div>
                <div className="text-sm text-slate-400">24 cuotas mensuales</div>
              </div>
              <div className="text-xl font-bold text-blue-400">{formatCurrency(installment24)}</div>
            </div>
            <div className="flex items-center justify-between p-4">
              <div>
                <div className="font-semibold text-white">36 Meses</div>
                <div className="text-sm text-slate-400">36 cuotas mensuales</div>
              </div>
              <div className="text-xl font-bold text-blue-400">{formatCurrency(installment36)}</div>
            </div>
          </div>
        </div>

        {/* Resumen de Cálculos */}
        <div className="mb-6">
          <h2 className="mb-4 text-lg font-semibold text-white">Resumen de Cotización</h2>
          <div className="rounded-lg bg-gradient-to-br from-slate-800 to-slate-900 p-4">
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded bg-white/5 p-3">
                <div className="text-xs text-slate-400">Precio Total</div>
                <div className="font-semibold text-white">{formatCurrency(totalPrice)}</div>
              </div>
              <div className="rounded bg-white/5 p-3">
                <div className="text-xs text-slate-400">ITBIS 18%</div>
                <div className="font-semibold text-white">{formatCurrency(itbis)}</div>
              </div>
              {discountEnabled && (
                <div className="rounded bg-white/5 p-3">
                  <div className="text-xs text-slate-400">Descuento</div>
                  <div className="font-semibold text-white">{formatCurrency(discountAmount)}</div>
                </div>
              )}
              <div className="rounded bg-white/5 p-3">
                <div className="text-xs text-slate-400">Precio Compra (s/ITBIS)</div>
                <div className="font-semibold text-white">{formatCurrency(purchasePrice)}</div>
              </div>
              <div className="rounded bg-white/5 p-3">
                <div className="text-xs text-slate-400">Depósito</div>
                <div className="font-semibold text-white">{formatCurrency(depositDelivered)}</div>
              </div>
              <div className="rounded bg-white/5 p-3">
                <div className="text-xs text-slate-400">Saldo a Financiar</div>
                <div className="text-xl font-bold text-blue-400">{formatCurrency(balanceToFinance)}</div>
              </div>
              <div className="rounded bg-white/5 p-3">
                <div className="text-xs text-slate-400">Tasa Anual</div>
                <div className="font-semibold text-white">26%</div>
              </div>
              <div className="rounded bg-white/5 p-3">
                <div className="text-xs text-slate-400">Plazo</div>
                <div className="font-semibold text-white">{termMonths} meses</div>
              </div>
              <div className="rounded bg-white/5 p-3">
                <div className="text-xs text-slate-400">Frecuencia</div>
                <div className="font-semibold text-white">{frequencyName}</div>
              </div>
              <div className="rounded bg-white/5 p-3">
                <div className="text-xs text-slate-400">Cuotas</div>
                <div className="font-semibold text-white">{Math.round(numPayments)}</div>
              </div>
              <div className="rounded bg-white/5 p-3 md:col-span-2">
                <div className="text-xs text-slate-400">Pago por Cuota</div>
                <div className="text-2xl font-bold text-blue-400">{formatCurrency(monthlyPayment)}</div>
              </div>
            </div>
          </div>
        </div>

        {/* Botones de Acción */}
        <div className="flex gap-4">
          <button
            onClick={shareWhatsApp}
            className="flex-1 rounded-lg bg-green-600 px-4 py-3 font-semibold text-white transition hover:bg-green-700"
          >
            Compartir por WhatsApp
          </button>
          <button
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
