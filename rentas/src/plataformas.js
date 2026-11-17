/* Portales: nombre, dominios y cómo abrir su búsqueda ya filtrada.
   Formatos tomados de URLs reales de resultados que aparecen en buscadores (17-nov-2026).
   Lo que un portal no deja filtrar en la liga se dice en la nota para ajustarlo allá,
   y cada fila ofrece además la misma búsqueda en Google limitada a ese portal. */
const FUENTES = {
  inmuebles24: {n: 'Inmuebles24', d: ['inmuebles24.com'], c: '#f2611d', l: 'i24'},
  vivanuncios: {n: 'Vivanuncios', d: ['vivanuncios.com.mx'], c: '#2a9d4b', l: 'viv'},
  lamudi: {n: 'Lamudi', d: ['lamudi.com.mx'], c: '#0d3b66', l: 'Lam'},
  propiedades: {n: 'Propiedades.com', d: ['propiedades.com'], c: '#0089c7', l: 'P'},
  mercadolibre: {n: 'Mercado Libre', d: ['mercadolibre.com.mx'], c: '#d9b600', l: 'ML'},
  pincali: {n: 'Pincali', d: ['pincali.com'], c: '#1f8f83', l: 'Pin'},
  trovit: {n: 'Trovit', d: ['trovit.com.mx'], c: '#33568f', l: 'T'},
  mitula: {n: 'Mitula', d: ['mitula.mx'], c: '#d8453a', l: 'M'},
  easybroker: {n: 'EasyBroker', d: ['easybroker.com'], c: '#2f6fe0', l: 'EB'},
  facebook: {n: 'Facebook Marketplace', d: ['facebook.com', 'fb.com', 'fb.me'], c: '#1877f2', l: 'f'},
  icasas: {n: 'icasas', d: ['icasas.mx'], c: '#d8352a', l: 'ic'},
  homie: {n: 'Homie', d: ['homie.mx'], c: '#5b3df5', l: 'H'},
  casasyterrenos: {n: 'Casas y Terrenos', d: ['casasyterrenos.com'], c: '#d96a00', l: 'CyT'},
  metroscubicos: {n: 'Metros Cúbicos', d: ['metroscubicos.com'], c: '#e3500e', l: 'm³'},
  century21: {n: 'Century 21', d: ['century21mexico.com'], c: '#7d6b3d', l: 'C21'},
  remax: {n: 'RE/MAX', d: ['remax.com.mx'], c: '#c8102e', l: 'RE'},
  segundamano: {n: 'Segundamano', d: ['segundamano.mx'], c: '#3d8b37', l: '2m'},
  dadaroom: {n: 'Dada Room', d: ['dadaroom.com'], c: '#ef5b5b', l: 'DR'},
  compartodepa: {n: 'CompartoDepa', d: ['compartodepa.com.mx'], c: '#2b7de9', l: 'CD'},
  roomgo: {n: 'Roomgo', d: ['roomgo.com.mx'], c: '#0aa5a5', l: 'Rg'},
};
const TIPO_TXT = {departamento: 'departamento', casa: 'casa', cuarto: 'cuarto', loft: 'loft', estudio: 'estudio', otro: ''};
function palabras(f, z){
  const t = f.tipos.length === 1 ? TIPO_TXT[f.tipos[0]] : f.tipos.length ? f.tipos.map(x => TIPO_TXT[x]).filter(Boolean).join(' OR ') : 'departamento OR casa';
  return [t, 'renta', z ? '"' + z + '"' : 'CDMX', f.mascotas === 'si' ? 'mascotas' : '', f.rec ? f.rec + ' recámaras' : ''].filter(Boolean).join(' ');
}
const google = (dominio, f, z) => 'https://www.google.com/search?q=' + encodeURIComponent('site:' + dominio + ' ' + palabras(f, z));
const tipoUno = f => f.tipos.length === 1 ? f.tipos[0] : null;
const esCasa = f => tipoUno(f) === 'casa', esCuarto = f => tipoUno(f) === 'cuarto';
/* el tipo solo cuenta como aplicado si el portal tiene esa categoría */
const T = (f, ok) => ok.includes(tipoUno(f)) ? ['tipo'] : [];
/* qué se aplicó en la liga y qué hay que ajustar allá */
function nota(f, z, hechos){
  const si = [], no = [];
  if (z) (hechos.includes('zona') ? si : no).push(z);
  if (f.tipos.length) (hechos.includes('tipo') && f.tipos.length === 1 ? si : no).push(f.tipos.length === 1 ? TIPOS[f.tipos[0]][0].toLowerCase() : 'tipo');
  if (f.min || f.max) (hechos.includes('precio') && f.max ? si : no).push('precio');
  if (f.mascotas === 'si') (hechos.includes('mascotas') ? si : no).push('mascotas');
  if (f.rec) (hechos.includes('rec') ? si : no).push('recámaras');
  return (si.length ? 'Abre con ' + si.join(', ') + '. ' : '') + (no.length ? 'Ajusta allá: ' + no.join(', ') + '.' : si.length ? '' : 'Rentas en la CDMX.');
}
const I24_ALC = {'Gustavo A. Madero': 'gustavo-a.-madero', 'Cuauhtémoc': 'cuauhtemoc-ciudad-de-cuauhtemoc'};
const VIV_ID = {'Benito Juárez': ['benito-juarez', 10267], 'Coyoacán': ['coyoacan', 10268], 'Cuauhtémoc': ['cuauhtemoc-df', 10270], 'Iztacalco': ['iztacalco', 10272]};
const PROP_ALC = {'Benito Juárez': 'benito-juarez-df', 'Coyoacán': 'coyoacan', 'Xochimilco': 'xochimilco', 'Iztapalapa': 'iztapalapa'};
const IC_ALC = {'Álvaro Obregón': [264, 'alvaro-obregon'], 'Azcapotzalco': [265, 'azcapotzalco'], 'Benito Juárez': [266, 'benito-juarez'], 'Coyoacán': [267, 'coyoacan'], 'Cuajimalpa': [268, 'cuajimalpa-morelos'], 'Cuauhtémoc': [269, 'cuauhtemoc'], 'Gustavo A. Madero': [270, 'gustavo-a-madero'], 'Iztacalco': [271, 'iztacalco'], 'Iztapalapa': [272, 'iztapalapa'], 'Magdalena Contreras': [273, 'magdalena-contreras'], 'Miguel Hidalgo': [274, 'miguel-hidalgo'], 'Milpa Alta': [275, 'milpa-alta'], 'Tláhuac': [276, 'tlahuac'], 'Tlalpan': [277, 'tlalpan'], 'Venustiano Carranza': [278, 'venustiano-carranza'], 'Xochimilco': [279, 'xochimilco']};
const PLATAFORMAS = [
  {...FUENTES.icasas, g: 'icasas.mx',
    url: (f, z) => { const [t, n] = esCasa(f) ? ['casas', 5] : ['departamentos', 3], a = z && IC_ALC[z]; return a ? `https://www.icasas.mx/renta/habitacionales-${t}-distrito-federal-${a[1]}-2_${n}_1_0_${a[0]}_0` : `https://www.icasas.mx/renta/habitacionales-${t}-2_${n}_0_0_0_0`; },
    nota: (f, z) => 'Anuncios vigentes de inmobiliarias. ' + nota(f, z && IC_ALC[z] ? z : null, ['zona', ...T(f, ['casa', 'departamento'])]) + (z ? '' : ' Elige Distrito Federal allá.')},
  {...FUENTES.homie, g: 'homie.mx',
    url: (f, z) => z ? `https://homie.mx/inmuebles-en-renta-en-${slug(z)}-cdmx` : `https://homie.mx/${esCasa(f) ? 'casas' : 'departamentos'}-en-renta-en-ciudad-de-mexico-cdmx`,
    nota: (f, z) => 'Rentas en línea; muchas aceptan mascotas. ' + nota(f, z, ['zona', ...(z ? [] : T(f, ['casa', 'departamento'])), ...(f.mascotas === 'si' ? ['mascotas'] : [])])},
  {...FUENTES.inmuebles24, g: 'inmuebles24.com',
    url: (f, z) => { const t = esCasa(f) ? 'casas' : esCuarto(f) ? 'departamento-compartido' : tipoUno(f) ? 'departamentos' : 'inmuebles';
      const lugar = z ? (I24_ALC[z] || slug(z)) : 'ciudad-de-mexico';
      const p = f.max ? (f.min ? `-de-${f.min}-a-${f.max}-pesos` : `-hasta-${f.max}-pesos`) : '';
      return `https://www.inmuebles24.com/${t}-en-renta-en-${lugar}${f.mascotas === 'si' ? '-con-permite-mascotas' : ''}${p}.html`; },
    nota: (f, z) => nota(f, z, ['zona', 'precio', 'mascotas', ...T(f, ['casa', 'departamento', 'cuarto'])])},
  {...FUENTES.mercadolibre, g: 'inmuebles.mercadolibre.com.mx',
    url: (f, z) => { const t = esCasa(f) ? 'casas' : esCuarto(f) ? 'cuartos' : 'departamentos'; return `https://inmuebles.mercadolibre.com.mx/${t}/renta/distrito-federal/${z ? slug(z) + '/' : ''}${f.max ? `_PriceRange_${f.min || 0}-${f.max}` : ''}`; },
    nota: (f, z) => nota(f, z, ['zona', 'precio', ...T(f, ['casa', 'departamento', 'cuarto'])])},
  {...FUENTES.propiedades, g: 'propiedades.com',
    url: (f, z) => { const t = esCasa(f) ? 'casas-renta' : esCuarto(f) ? 'cuartos-renta' : tipoUno(f) ? 'departamentos-renta' : 'renta'; const lugar = z && PROP_ALC[z] ? PROP_ALC[z] : 'df'; return `https://propiedades.com/${lugar}/${t}${f.mascotas === 'si' ? '/mascotas' : ''}`; },
    nota: (f, z) => nota(f, z && PROP_ALC[z] ? z : null, ['zona', 'mascotas', ...T(f, ['casa', 'departamento', 'cuarto'])]) + (z && !PROP_ALC[z] ? ' Elige ' + z + ' allá.' : '')},
  {...FUENTES.vivanuncios, g: 'vivanuncios.com.mx',
    url: (f, z) => { const [s, l] = z && VIV_ID[z] ? VIV_ID[z] : ['distrito-federal', 1008]; const [cs, c] = esCasa(f) ? ['s-casas-en-renta', 1299] : tipoUno(f) && !esCuarto(f) ? ['s-departamentos-en-renta', 1300] : ['s-renta-inmuebles', 1098];
      return `https://www.vivanuncios.com.mx/${cs}/${s}/${f.mascotas === 'si' ? 'mascotas/' : ''}v1c${c}l${l}${f.mascotas === 'si' ? 'q0' : ''}p1`; },
    nota: (f, z) => nota(f, z && VIV_ID[z] ? z : null, ['zona', 'mascotas', ...T(f, ['casa', 'departamento'])]) + (z && !VIV_ID[z] ? ' Elige ' + z + ' allá.' : '')},
  {...FUENTES.lamudi, g: 'lamudi.com.mx',
    url: (f, z) => { const t = esCasa(f) ? 'casa' : 'departamento', a = z ? (z === 'Cuauhtémoc' ? 'cuauhtemoc-2' : slug(z)) + '/' : ''; return `https://www.lamudi.com.mx/distrito-federal/${a}${t}/for-rent/${f.max ? `price:${f.min || 0}-${f.max}/` : ''}`; },
    nota: (f, z) => nota(f, z, ['zona', 'precio', ...T(f, ['casa', 'departamento'])])},
  {...FUENTES.pincali, g: 'pincali.com',
    url: (f, z) => z ? `https://www.pincali.com/inmuebles/${tipoUno(f) === 'departamento' ? 'departamentos' : 'propiedades'}-en-renta-en-${slug(z)}-ciudad-de-mexico` : 'https://www.pincali.com/',
    nota: (f, z) => z ? nota(f, z, ['zona', ...T(f, ['departamento'])]) : 'Busca "renta" y tu zona allá.'},
  {...FUENTES.facebook, g: null,
    url: (f) => { const cat = esCasa(f) ? (f.rec === 3 ? '3-bedroom-houses' : 'houses-for-rent') : f.rec === 1 ? '1-bedroom-apartments' : f.rec === 2 ? '2-bedroom-apartments' : 'propertyrentals';
      const q = new URLSearchParams(); if (f.min) q.set('minPrice', f.min); if (f.max) q.set('maxPrice', f.max); return `https://www.facebook.com/marketplace/mexicocity/${cat}/` + (q.toString() ? '?' + q : ''); },
    nota: (f, z) => 'Rentas de particulares en la CDMX; pide iniciar sesión. ' + nota(f, z, esCasa(f) ? ['tipo', ...(f.rec === 3 ? ['rec'] : [])] : tipoUno(f) === 'departamento' && (f.rec === 1 || f.rec === 2) ? ['tipo', 'rec'] : []).replace('Rentas en la CDMX.', '')},
  {...FUENTES.trovit, g: 'trovit.com.mx',
    url: (f, z) => `https://casas.trovit.com.mx/renta-${esCasa(f) ? 'casa' : esCuarto(f) ? 'cuartos' : 'departamento'}-${z ? slug(z) : 'ciudad-mexico'}${f.mascotas === 'si' ? '-aceptan-mascotas' : ''}`,
    nota: (f, z) => 'Junta anuncios de varios portales. ' + nota(f, z, ['zona', 'mascotas', ...T(f, ['casa', 'departamento', 'cuarto'])])},
  {...FUENTES.mitula, g: 'mitula.mx',
    url: (f, z) => `https://casas.mitula.mx/casas/renta-${esCasa(f) ? 'casas' : 'departamentos'}-${f.mascotas === 'si' ? 'aceptan-mascotas-' : ''}${z ? (z === 'Gustavo A. Madero' ? 'gustavo-madero' : slug(z)) : 'ciudad-de-mexico'}`,
    nota: (f, z) => 'Junta anuncios de varios portales. ' + nota(f, z, ['zona', 'mascotas', ...T(f, ['casa', 'departamento'])])},
];
