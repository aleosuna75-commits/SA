/* Portales: nombre, dominios y cómo abrir su búsqueda con los filtros elegidos.
   Los portales bloquean la lectura automática, así que no se pudieron comprobar todos sus parámetros:
   cada fila abre la página de rentas del portal con lo que sí se sabe que acepta, y además ofrece
   la misma búsqueda en Google limitada a ese portal, que siempre funciona. */
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
};
const TIPO_TXT = {departamento: 'departamento', casa: 'casa', cuarto: 'cuarto', loft: 'loft', estudio: 'estudio', otro: ''};
function palabras(f, z){
  const t = f.tipos.length === 1 ? TIPO_TXT[f.tipos[0]] : f.tipos.length ? f.tipos.map(x => TIPO_TXT[x]).filter(Boolean).join(' OR ') : 'departamento OR casa';
  return [t, 'renta', z ? '"' + z + '"' : 'CDMX', f.mascotas === 'si' ? 'mascotas' : '', f.rec ? f.rec + ' recámaras' : ''].filter(Boolean).join(' ');
}
const google = (dominio, f, z) => 'https://www.google.com/search?q=' + encodeURIComponent('site:' + dominio + ' ' + palabras(f, z));
const tipoUno = f => f.tipos.length === 1 ? f.tipos[0] : null;
const filtrosTexto = (f, hechos) => { const faltan = []; if ((f.min || f.max) && !hechos.includes('precio')) faltan.push('precio'); if (f.mascotas === 'si' && !hechos.includes('mascotas')) faltan.push('mascotas'); if (f.rec && !hechos.includes('rec')) faltan.push('recámaras'); return faltan.length ? 'Ajusta allá: ' + faltan.join(', ') + '.' : 'Abre con tus filtros.'; };
const PLATAFORMAS = [
  {...FUENTES.facebook, url: (f) => { const q = new URLSearchParams(); if (f.min) q.set('minPrice', f.min); if (f.max) q.set('maxPrice', f.max); if (f.rec) q.set('minBedrooms', f.rec); return 'https://www.facebook.com/marketplace/mexicocity/propertyrentals' + (q.toString() ? '?' + q : ''); },
    nota: (f) => 'Rentas de particulares en la CDMX. ' + filtrosTexto(f, ['precio', 'rec']) + ' Pide iniciar sesión.', g: null},
  {...FUENTES.inmuebles24, url: (f, z) => { const t = tipoUno(f) === 'casa' ? 'casas' : tipoUno(f) === 'cuarto' ? 'cuartos' : 'departamentos'; return `https://www.inmuebles24.com/${t}-en-renta-en-distrito-federal${f.mascotas === 'si' ? '-con-permite-mascotas' : ''}.html`; },
    nota: (f, z) => 'Toda la CDMX' + (z ? '; elige ' + z + ' allá' : '') + '. ' + filtrosTexto(f, ['mascotas']), g: 'inmuebles24.com'},
  {...FUENTES.mercadolibre, url: (f, z) => { const t = tipoUno(f) === 'casa' ? 'casas' : tipoUno(f) === 'cuarto' ? 'cuartos' : 'departamentos'; return `https://inmuebles.mercadolibre.com.mx/${t}/renta/distrito-federal/${z ? slug(z) + '/' : ''}`; },
    nota: (f, z) => (z ? z : 'Toda la CDMX') + '. ' + filtrosTexto(f, []), g: 'inmuebles.mercadolibre.com.mx'},
  {...FUENTES.vivanuncios, url: () => 'https://www.vivanuncios.com.mx/', nota: (f, z) => 'Elige "Renta" y la CDMX allá. ' + filtrosTexto(f, []), g: 'vivanuncios.com.mx'},
  {...FUENTES.propiedades, url: (f) => { const t = tipoUno(f) === 'casa' ? 'casas' : 'departamentos'; return `https://propiedades.com/df/${t}-renta${f.mascotas === 'si' ? '/mascotas' : ''}`; },
    nota: (f, z) => 'Toda la CDMX' + (z ? '; elige ' + z + ' allá' : '') + '. ' + filtrosTexto(f, ['mascotas']), g: 'propiedades.com'},
  {...FUENTES.lamudi, url: (f, z) => { const t = tipoUno(f) === 'casa' ? 'casa' : 'departamento'; return `https://www.lamudi.com.mx/distrito-federal/${z ? slug(z) + '/' : ''}${t}/for-rent/`; },
    nota: (f, z) => (z ? z : 'Toda la CDMX') + '. ' + filtrosTexto(f, []), g: 'lamudi.com.mx'},
  {...FUENTES.pincali, url: () => 'https://www.pincali.com/', nota: (f) => 'Busca "renta" y tu zona allá. ' + filtrosTexto(f, []), g: 'pincali.com'},
  {...FUENTES.trovit, url: (f, z) => 'https://casas.trovit.com.mx/renta-' + (tipoUno(f) === 'casa' ? 'casa' : 'departamento') + '-ciudad-m%C3%A9xico' + (z ? '-' + slug(z) : ''), nota: (f, z) => 'Junta anuncios de varios portales. ' + filtrosTexto(f, []), g: 'trovit.com.mx'},
  {...FUENTES.mitula, url: (f, z) => 'https://casas.mitula.mx/casas/renta-' + (z ? slug(z) : 'ciudad-de-mexico'), nota: (f) => 'Junta anuncios de varios portales. ' + filtrosTexto(f, []), g: 'mitula.mx'},
];
